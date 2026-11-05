import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Profiler } from 'react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { allowConsoleErrors } from './test/console'
import { deferred, errorResponse, jsonResponse, mockFetch } from './test/fetchMock'
import { config, outline, paper } from './test/fixtures'
import { itFailsUntilFixed } from './test/knownBugs'

vi.mock('./components/PdfViewer', () => ({ default: () => null }))

// React's report of the render loop that the test 'settles after opening a paper' shows.
// Tests about other behavior of an open paper tolerate it, so they stay deterministic.
const RENDER_LOOP = /Maximum update depth exceeded/

function backend() {
  return mockFetch()
    .on('GET', '/api/health', { status: 'ok' })
    .on('GET', '/api/papers/keys', [])
    .on('GET', '/api/papers', [paper({ id: 4 })])
}

function withPaper(api: ReturnType<typeof backend>, inLibrary = false) {
  return api
    .on('GET', '/api/config', config())
    .on('GET', '/api/papers/4', paper({ id: 4, in_library: inLibrary }))
    .on('GET', '/api/papers/4/chat', [])
    .on('GET', '/api/papers/4/outline', outline())
}

// The app marks the current page's tab only visually (class "active", styled in index.css);
// there is no accessible marker such as aria-current to read instead.
function markedTabs(): string[] {
  return within(screen.getByRole('navigation'))
    .getAllByRole('link')
    .filter((link) => link.classList.contains('active'))
    .map((link) => link.textContent ?? '')
}

describe('App', () => {
  it('starts on the search page', async () => {
    backend()
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Search papers' })).toBeInTheDocument()
    expect(markedTabs()).toEqual(['Search'])
    await waitFor(() => expect(window.location.hash).toBe('#/search'))
  })

  it('switches pages with the tabs', async () => {
    backend()
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('link', { name: 'Library' }))

    expect(await screen.findByRole('heading', { name: 'Library' })).toBeInTheDocument()
    expect(markedTabs()).toEqual(['Library'])
    expect(window.location.hash).toBe('#/library')
  })

  it('opens the page in the address bar, and tidies its address', async () => {
    backend()
    window.location.hash = '#/library/'
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Library' })).toBeInTheDocument()
    expect(window.location.hash).toBe('#/library')
  })

  it.each([
    [false, 'Search'], // an unsaved paper was opened from search; it is not in the library yet
    [true, 'Library'],
  ])('marks the tab an open paper belongs to once it has loaded (in library: %s)', async (inLibrary, tab) => {
    allowConsoleErrors(RENDER_LOOP)
    const loading = deferred()
    withPaper(backend(), inLibrary).on('GET', '/api/papers/4', loading.reply)
    window.location.hash = '#/paper/4'
    render(<App />)

    expect(await screen.findByText('Opening the paper…')).toBeInTheDocument()
    expect(markedTabs()).toEqual([]) // not claimed while the paper loads
    loading.resolve(jsonResponse(paper({ id: 4, in_library: inLibrary })))

    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need' })).toBeInTheDocument()
    await waitFor(() => expect(markedTabs()).toEqual([tab]))
  })

  // Confirmed app bug: App passes PaperPage a new onLibraryState function on every render,
  // PaperPage calls it from an effect that depends on it, and App then stores a new object,
  // so App and PaperPage re-render each other forever while a paper is open (React logs
  // "Maximum update depth exceeded"). The page must settle once the paper has loaded.
  itFailsUntilFixed('settles after opening a paper, without React errors', async () => {
    const renderLoopErrors = allowConsoleErrors(RENDER_LOOP) // the bug's symptom: checked below
    let commits = 0
    withPaper(backend())
    window.location.hash = '#/paper/4'
    render(
      <Profiler id="app" onRender={() => (commits += 1)}>
        <App />
      </Profiler>,
    )
    // Everything the reader loads has arrived: the paper, the model menu, the outline, the chat.
    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need' })).toBeInTheDocument()
    expect(await screen.findByRole('combobox', { name: /Model/ })).toHaveValue('opus')
    expect(await screen.findByRole('button', { name: /1 Introduction/ })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'What datasets are used?' })).toBeEnabled()

    return async () => {
      // Nothing is left to change, so nothing renders any more, and React reports no loop.
      const before = commits
      await new Promise((resolve) => setTimeout(resolve, 200))
      expect(commits - before).toBe(0)
      expect(renderLoopErrors).toEqual([])
    }
  })

  it('goes back to the page the paper was opened from', async () => {
    allowConsoleErrors(RENDER_LOOP)
    withPaper(backend())
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(window.location.hash).toBe('#/search'))

    window.location.hash = '#/paper/4'
    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '← Back' }))

    // Back follows the browser history (without an earlier page it would go to the library).
    await waitFor(() => expect(window.location.hash).toBe('#/search'))
    expect(await screen.findByRole('heading', { name: 'Search papers' })).toBeInTheDocument()
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
