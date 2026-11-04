import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { searchResult } from '../test/fixtures'
import PaperCard from './PaperCard'

describe('PaperCard', () => {
  it('shortens long author lists and expands them on request', async () => {
    const authors = Array.from({ length: 8 }, (_, i) => `Author ${i + 1}`)
    render(<PaperCard paper={searchResult({ authors })} />)

    expect(screen.getByText(/Author 1, .*Author 6,/)).toBeInTheDocument()
    expect(screen.queryByText(/Author 7/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '+2 more' }))

    expect(screen.getByText(authors.join(', '))).toBeInTheDocument()
  })

  it('fills in missing metadata', () => {
    render(<PaperCard paper={searchResult({ authors: [], year: null, abstract: null, venue: null, doi: null, url: null, pdf_url: null })} />)

    expect(screen.getByText('Unknown authors')).toBeInTheDocument()
    expect(screen.getByText('Year unknown')).toBeInTheDocument()
    expect(screen.getByText('No abstract available.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByText(/DOI:/)).not.toBeInTheDocument()
  })

  it('shows the source of the paper', () => {
    render(<PaperCard paper={searchResult({ source: 'upload' })} />)
    expect(screen.getByText('Uploaded PDF')).toBeInTheDocument()
  })

  it('toggles the full abstract', async () => {
    render(<PaperCard paper={searchResult()} />)
    expect(screen.getByText(searchResult().abstract!)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show full abstract' }))
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show full abstract' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show less' }))
    expect(screen.getByRole('button', { name: 'Show full abstract' })).toBeInTheDocument()
  })

  it('shows the whole abstract without a toggle in the reader', () => {
    render(<PaperCard paper={searchResult()} defaultExpanded />)

    expect(screen.getByText(searchResult().abstract!)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show/ })).not.toBeInTheDocument()
  })

  it('links the title to the paper page in a new tab by default', () => {
    render(<PaperCard paper={searchResult()} />)

    const title = screen.getByRole('link', { name: 'Attention Is All You Need' })
    expect(title).toHaveAttribute('href', 'https://arxiv.org/abs/1706.03762')
    expect(title).toHaveAttribute('target', '_blank')
  })

  it('links the title inside the app when given a route', () => {
    render(<PaperCard paper={searchResult()} href="#/paper/3" />)

    const title = screen.getByRole('link', { name: 'Attention Is All You Need' })
    expect(title).toHaveAttribute('href', '#/paper/3')
    expect(title).not.toHaveAttribute('target')
  })

  it('calls back instead of navigating when the title opens the reader', () => {
    const onOpen = vi.fn()
    render(<PaperCard paper={searchResult()} onOpen={onOpen} />)
    const title = screen.getByRole('link', { name: 'Attention Is All You Need' })
    const click = createEvent.click(title)

    fireEvent(title, click)

    expect(onOpen).toHaveBeenCalledOnce()
    expect(click.defaultPrevented).toBe(true) // the browser does not follow the link
  })

  it('links the PDF: the open-access copy of a search result, or the stored copy', () => {
    const { rerender } = render(<PaperCard paper={searchResult()} />)
    expect(screen.getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', 'https://arxiv.org/pdf/1706.03762')

    // (Which link wins when there are both: see LibraryPage.test.tsx.)
    rerender(<PaperCard paper={searchResult({ pdf_url: null })} localPdfHref="/api/papers/1/pdf" />)
    expect(screen.getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', '/api/papers/1/pdf')
  })
})
