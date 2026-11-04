import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PdfViewer from './PdfViewer'

// PDF.js needs a real browser (canvas, workers), so react-pdf is replaced by a stand-in that
// "loads" a document of `pdf.pages` pages, or fails to. The end-to-end tests run the real viewer,
// including scrolling and keeping the reading position while zooming, which need a layout engine.
const pdf = vi.hoisted(() => ({ fails: false, pages: 3 }))
vi.mock('react-pdf', async () => {
  const { useEffect } = await import('react')
  return {
    pdfjs: { GlobalWorkerOptions: {} },
    Document: ({ onLoadSuccess, onLoadError, children }: {
      onLoadSuccess: (doc: unknown) => void
      onLoadError: (error: Error) => void
      children: React.ReactNode
    }) => {
      useEffect(() => {
        if (pdf.fails) onLoadError(new Error('Invalid PDF structure.'))
        else onLoadSuccess({ numPages: pdf.pages, getPage: async () => ({ getViewport: () => ({ width: 612, height: 792 }) }) })
      }, [onLoadError, onLoadSuccess])
      return <div>{children}</div>
    },
    Page: ({ pageNumber, width }: { pageNumber: number; width: number }) => (
      <p>{`Page ${pageNumber} drawn ${width} px wide`}</p>
    ),
  }
})

beforeEach(() => {
  pdf.fails = false
  // jsdom has no layout, so these observers never report anything.
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
})

describe('PdfViewer', () => {
  it('shows the pages, a page counter, and a link to open the PDF itself', async () => {
    render(<PdfViewer url="/api/papers/4/pdf" />)

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument()
    // Only pages near the view are drawn; the viewer starts at the top.
    expect(screen.getByText('Page 1 drawn 600 px wide')).toBeInTheDocument()
    expect(screen.queryByText(/^Page 3 drawn/)).not.toBeInTheDocument()
    const open = screen.getByRole('link', { name: 'Open PDF ↗' })
    expect(open).toHaveAttribute('href', '/api/papers/4/pdf')
    expect(open).toHaveAttribute('target', '_blank')
    expect(open).toHaveAttribute('rel', 'noreferrer')
  })

  it('zooms in and out in steps, and Fit width goes back to the panel width', async () => {
    const user = userEvent.setup()
    render(<PdfViewer url="/api/papers/4/pdf" />)
    await screen.findByText('Page 1 of 3')
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fit width' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(screen.getByText('125%')).toBeInTheDocument()
    expect(screen.getByText('Page 1 drawn 750 px wide')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Fit width' }))
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('Page 1 drawn 600 px wide')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fit width' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Zoom out' }))
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('Page 1 drawn 450 px wide')).toBeInTheDocument()
  })

  it('stops zooming at 50% and 300%', async () => {
    const user = userEvent.setup()
    render(<PdfViewer url="/api/papers/4/pdf" />)
    await screen.findByText('Page 1 of 3')

    for (let i = 0; i < 2; i++) await user.click(screen.getByRole('button', { name: 'Zoom out' }))
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeDisabled()

    for (let i = 0; i < 7; i++) await user.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(screen.getByText('300%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled()
  })

  it('says so when the PDF cannot be displayed, and still links to it', async () => {
    pdf.fails = true
    render(<PdfViewer url="/api/papers/4/pdf" />)

    expect(await screen.findByText('The PDF could not be displayed.')).toBeInTheDocument()
    expect(screen.queryByText(/^Page \d+ of/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open PDF ↗' })).toHaveAttribute('href', '/api/papers/4/pdf')
  })
})
