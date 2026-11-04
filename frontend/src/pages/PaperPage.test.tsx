import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { forwardRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { errorResponse, jsonResponse, mockFetch, ndjson } from '../test/fetchMock'
import { config, outline, paper } from '../test/fixtures'
import type { AppConfig, PaperDetail } from '../types'
import PaperPage from './PaperPage'

// PDF.js needs a real browser (canvas, workers); the end-to-end tests cover the viewer.
vi.mock('../components/PdfViewer', () => ({
  default: forwardRef<unknown, { url: string }>(function FakePdfViewer({ url }, _ref) {
    return <div data-testid="pdf-viewer">{url}</div>
  }),
}))

function setup(current: PaperDetail, llm: AppConfig = config()) {
  const api = mockFetch()
    .on('GET', '/api/config', llm)
    .on('GET', `/api/papers/${current.id}`, current)
    .on('GET', `/api/papers/${current.id}/chat`, [])
    .on('GET', `/api/papers/${current.id}/outline`, outline())
  const onLibraryState = vi.fn()
  const user = userEvent.setup()
  render(<PaperPage id={current.id} onLibraryState={onLibraryState} />)
  return { api, user, onLibraryState }
}

const libraryPaper = paper({ id: 4, venue: 'NeurIPS' })

describe('PaperPage', () => {
  it('shows the paper with its metadata', async () => {
    setup(libraryPaper)

    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need' })).toBeInTheDocument()
    const header = screen.getByRole('heading', { level: 1 }).closest('header')!
    expect(within(header).getByText('Ashish Vaswani, Noam Shazeer')).toBeInTheDocument()
    expect(within(header).getByText('2017')).toBeInTheDocument()
    expect(within(header).getByText('NeurIPS')).toBeInTheDocument()
    expect(within(header).getByText('✓ In library')).toBeInTheDocument()
    expect(within(header).getByRole('link', { name: 'OpenAlex ↗' })).toHaveAttribute('href', libraryPaper.url)
  })

  it('shows the abstract when there is no PDF', async () => {
    setup(libraryPaper)

    expect(await screen.findByRole('heading', { name: 'Abstract' })).toBeInTheDocument()
    expect(screen.getByText(/The dominant sequence transduction models/)).toBeInTheDocument()
    expect(screen.queryByTestId('pdf-viewer')).not.toBeInTheDocument()
  })

  it('shows the stored PDF when there is one', async () => {
    setup(paper({ id: 4, has_pdf: true, full_text_status: 'ok', page_count: 11 }))

    expect(await screen.findByTestId('pdf-viewer')).toHaveTextContent('/api/papers/4/pdf')
  })

  it('reports a paper that no longer exists', async () => {
    mockFetch()
      .on('GET', '/api/config', config())
      .on('GET', '/api/papers/99', errorResponse(404, 'Paper not found.'))
    render(<PaperPage id={99} />)

    expect(await screen.findByText('This paper is no longer available.')).toBeInTheDocument()
  })

  it('saves a paper that was only opened from search', async () => {
    const opened = paper({ id: 4, in_library: false, saved_at: null })
    const { api, user, onLibraryState } = setup(opened)
    api.on('POST', '/api/papers/4/save', paper({ id: 4, in_library: true }))
    await waitFor(() => expect(onLibraryState).toHaveBeenLastCalledWith(false))

    await user.click(await screen.findByRole('button', { name: 'Save to library' }))

    expect(await screen.findByText('✓ In library')).toBeInTheDocument()
    expect(onLibraryState).toHaveBeenLastCalledWith(true)
    expect(api.callsTo('POST', '/api/papers/4/save')).toHaveLength(1)
  })

  it('removes a library paper and returns to the library', async () => {
    const { api, user } = setup(libraryPaper)
    api.on('DELETE', '/api/papers/4', new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    await user.click(await screen.findByRole('button', { name: 'Remove' }))

    await waitFor(() => expect(window.location.hash).toBe('#/library'))
    expect(api.callsTo('DELETE', '/api/papers/4')).toHaveLength(1)
  })

  it('goes back to the library when there is no earlier page', async () => {
    const { user } = setup(libraryPaper)
    await screen.findByRole('heading', { level: 1 })

    await user.click(screen.getByRole('button', { name: '← Back' }))

    expect(window.location.hash).toBe('#/library')
  })

  it('switches between sections, summary, and details', async () => {
    const { user } = setup(libraryPaper)

    expect(await screen.findByRole('button', { name: /1 Introduction/ })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Summary' }))
    expect(screen.getByRole('button', { name: 'Generate summary' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Details' }))
    expect(screen.getByRole('button', { name: 'Edit details' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
  })

  it('corrects the metadata from the details tab', async () => {
    const { api, user } = setup(libraryPaper)
    api.on('PATCH', '/api/papers/4', (call) => jsonResponse({ ...libraryPaper, ...(call.body as object) }))
    await user.click(await screen.findByRole('tab', { name: 'Details' }))
    await user.click(screen.getByRole('button', { name: 'Edit details' }))

    const title = screen.getByRole('textbox', { name: 'Title' })
    await user.clear(title)
    await user.type(title, 'Attention Is All You Need (corrected)')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Attention Is All You Need (corrected)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })

  it('says how long an unsaved paper is kept', async () => {
    const { user } = setup(paper({ id: 4, in_library: false, saved_at: null }), config({ cached_paper_days: 7 }))

    await user.click(await screen.findByRole('tab', { name: 'Details' }))

    expect(
      await screen.findByText(/not in your library yet; save it to keep it \(unsaved papers are deleted after 7 days without being opened\)/),
    ).toBeInTheDocument()
  })

  it('remembers the model chosen in the menu and uses it', async () => {
    const { api, user } = setup(paper({ id: 4, full_text_status: 'ok', has_pdf: true }))
    api.on('POST', '/api/papers/4/summary', ndjson([{ type: 'error', message: 'stop here' }]))

    await user.selectOptions(await screen.findByRole('combobox'), 'sonnet')
    await user.click(screen.getByRole('tab', { name: 'Summary' }))
    await user.click(screen.getByRole('button', { name: 'Generate summary' }))

    await waitFor(() => expect(api.callsTo('POST', '/api/papers/4/summary')).toHaveLength(1))
    expect(api.callsTo('POST', '/api/papers/4/summary')[0].query.get('model')).toBe('sonnet')
    expect(localStorage.getItem('llm-model')).toBe('sonnet')
  })

  it('starts with the remembered model if it is still offered', async () => {
    localStorage.setItem('llm-model', 'sonnet')
    setup(libraryPaper)

    expect(await screen.findByRole('combobox')).toHaveValue('sonnet')
  })

  it('falls back to the default model when the remembered one is gone', async () => {
    localStorage.setItem('llm-model', 'retired-model')
    setup(libraryPaper)

    expect(await screen.findByRole('combobox')).toHaveValue('opus')
  })

  it('fetches the full text on the first visit of a search result', async () => {
    const fresh = paper({ id: 4, full_text_status: null, full_text_error: null })
    const { api } = setup(fresh)
    api.on('POST', '/api/papers/4/fulltext', paper({ id: 4, full_text_status: 'ok', has_pdf: true, page_count: 9 }))

    expect(await screen.findByTestId('pdf-viewer')).toBeInTheDocument()
    expect(api.callsTo('POST', '/api/papers/4/fulltext')).toHaveLength(1)
  })
})
