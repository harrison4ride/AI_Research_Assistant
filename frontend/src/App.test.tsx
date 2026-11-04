import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { errorResponse, mockFetch } from './test/fetchMock'
import { config, outline, paper } from './test/fixtures'

vi.mock('./components/PdfViewer', () => ({ default: () => null }))

function backend() {
  return mockFetch()
    .on('GET', '/api/health', { status: 'ok' })
    .on('GET', '/api/papers/keys', [])
    .on('GET', '/api/papers', [paper({ id: 4 })])
}

describe('App', () => {
  it('starts on the search page', async () => {
    backend()
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Search papers' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Search' })).toHaveClass('active')
  })

  it('switches pages with the tabs', async () => {
    backend()
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('link', { name: 'Library' }))

    expect(await screen.findByRole('heading', { name: 'Library' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Library' })).toHaveClass('active')
    expect(window.location.hash).toBe('#/library')
  })

  it('opens the page in the address bar, and tidies its address', async () => {
    backend()
    window.location.hash = '#/library/'
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Library' })).toBeInTheDocument()
    expect(window.location.hash).toBe('#/library')
  })

  it('opens a paper in the reader and marks the tab it belongs to', async () => {
    backend()
      .on('GET', '/api/config', config())
      .on('GET', '/api/papers/4', paper({ id: 4, in_library: false }))
      .on('GET', '/api/papers/4/chat', [])
      .on('GET', '/api/papers/4/outline', outline())
    window.location.hash = '#/paper/4'
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need' })).toBeInTheDocument()
    // An unsaved paper belongs to Search; it is not in the library yet.
    await waitFor(() => expect(screen.getByRole('link', { name: 'Search' })).toHaveClass('active'))
    expect(screen.getByRole('link', { name: 'Library' })).not.toHaveClass('active')
  })

  it('warns when the backend is not running, and recovers when it starts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const api = backend().on('GET', '/api/health', errorResponse(502, 'Bad Gateway'))
      render(<App />)

      expect(await screen.findByText(/Cannot reach the backend/)).toBeInTheDocument()
      api.on('GET', '/api/health', { status: 'ok' })
      await act(() => vi.advanceTimersByTimeAsync(3000))

      await waitFor(() => expect(screen.queryByText(/Cannot reach the backend/)).not.toBeInTheDocument())
      expect(api.callsTo('GET', '/api/health').length).toBeGreaterThanOrEqual(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
