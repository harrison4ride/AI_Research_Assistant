import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { bert, paper, pdfFile } from '../test/fixtures'
import { useFakeTimers } from '../test/timers'
import type { Paper } from '../types'
import LibraryPage from './LibraryPage'

const attention = paper({ id: 1 })
const bertPaper = paper({ ...bert, id: 2, has_pdf: true, page_count: 14, full_text_status: 'ok' })

function matching(papers: Paper[], q: string | null) {
  return q ? papers.filter((p) => p.title.toLowerCase().includes(q.toLowerCase())) : papers
}

function setup(papers: Paper[] = [attention, bertPaper]) {
  const api = mockFetch().on('GET', '/api/papers', (call) => jsonResponse(matching(papers, call.query.get('q'))))
  const user = userEvent.setup()
  render(<LibraryPage />)
  return { api, user }
}

function filterBox() {
  return screen.getByPlaceholderText('Filter by title, author, or abstract')
}

function listedTitles() {
  return screen.queryAllByRole('article').map((card) => within(card).getByRole('heading').textContent)
}

// Answer a held-back request and wait until the page has read and handled the answer.
async function answerAndWaitUntilRead(request: ReturnType<typeof deferred>, papers: Paper[]) {
  const answer = jsonResponse(papers)
  request.resolve(answer)
  await waitFor(() => expect(answer.bodyUsed).toBe(true))
  await act(async () => {}) // let the page apply what it read
}

describe('LibraryPage', () => {
  it('lists the saved papers', async () => {
    setup()

    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(await screen.findByText('2 papers')).toBeInTheDocument()
    const cards = screen.getAllByRole('article')
    expect(cards.map((c) => within(c).getByRole('heading').textContent)).toEqual([attention.title, bert.title])
  })

  it('links each paper to the reader', async () => {
    setup()

    const card = (await screen.findAllByRole('article'))[0]

    expect(within(card).getByRole('link', { name: attention.title })).toHaveAttribute('href', '#/paper/1')
    expect(within(card).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '#/paper/1')
  })

  it('links to the stored PDF of a paper that has only that one', async () => {
    setup()

    const card = (await screen.findAllByRole('article'))[1]

    expect(within(card).getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', '/api/papers/2/pdf')
  })

  // Suspected app bug: PaperCard documents `localPdfHref` as the "Link to a locally stored copy
  // of the PDF, when the library has one", but uses `paper.pdf_url ?? localPdfHref`, so a stored
  // copy is never linked when the paper also has an open-access link (which may be the very link
  // whose download failed before the user attached the PDF).
  it.fails('links to the stored copy of a paper that also has an open-access link', async () => {
    const both = paper({ id: 3, pdf_url: 'https://publisher.example/paper.pdf', has_pdf: true, full_text_status: 'ok' })
    setup([both])

    const [card] = await screen.findAllByRole('article')

    expect(within(card).getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', '/api/papers/3/pdf')
  })

  it('explains an empty library', async () => {
    setup([])

    expect(await screen.findByText(/Your library is empty/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Search for papers' })).toHaveAttribute('href', '#/search')
    expect(screen.getByText('0 papers')).toBeInTheDocument()
  })

  it('filters on the server once the user stops typing for 200 ms', async () => {
    useFakeTimers()
    const api = mockFetch().on('GET', '/api/papers', (call) =>
      jsonResponse(matching([attention, bertPaper], call.query.get('q'))),
    )
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<LibraryPage />)
    await act(() => vi.advanceTimersByTimeAsync(200))
    expect(screen.getByText('2 papers')).toBeInTheDocument()
    const sentFilters = () => api.callsTo('GET', '/api/papers').map((c) => c.query.get('q'))

    await user.type(filterBox(), 'bert')
    await act(() => vi.advanceTimersByTimeAsync(199))
    expect(sentFilters()).toEqual([null]) // nothing while typing, nor 199 ms after the last key

    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(screen.getByText('1 paper matching')).toBeInTheDocument()
    expect(listedTitles()).toEqual([bert.title])
    expect(sentFilters()).toEqual([null, 'bert']) // one request for the whole word
  })

  it('ignores an older filter answer that arrives after a newer one', async () => {
    const slow = deferred()
    const api = mockFetch().on('GET', '/api/papers', (call) =>
      call.query.get('q') === 'b' ? slow.reply() : jsonResponse(matching([attention, bertPaper], call.query.get('q'))),
    )
    const user = userEvent.setup()
    render(<LibraryPage />)
    await screen.findByText('2 papers')

    await user.type(filterBox(), 'b')
    await waitFor(() => expect(api.callsTo('GET', '/api/papers').map((c) => c.query.get('q'))).toContain('b'))
    await user.type(filterBox(), 'ert')
    expect(await screen.findByText('1 paper matching')).toBeInTheDocument()

    await answerAndWaitUntilRead(slow, [attention, bertPaper]) // the answer for "b" comes last

    expect(listedTitles()).toEqual([bert.title])
    expect(screen.getByText('1 paper matching')).toBeInTheDocument()
  })

  it('does not bring back a removed paper with a list answer that was already on its way', async () => {
    const pending = deferred()
    const api = mockFetch().on('GET', '/api/papers', (call) =>
      call.query.get('q') ? pending.reply() : jsonResponse([attention, bertPaper]),
    )
    api.on('DELETE', '/api/papers/1', new Response(null, { status: 204 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<LibraryPage />)
    await screen.findByText('2 papers')
    await user.type(filterBox(), 'a')
    await waitFor(() => expect(api.callsTo('GET', '/api/papers')).toHaveLength(2)) // the filter request is out

    await user.click(within(screen.getAllByRole('article')[0]).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(listedTitles()).toEqual([bert.title]))

    await answerAndWaitUntilRead(pending, [attention, bertPaper]) // made before the removal

    expect(listedTitles()).toEqual([bert.title])
    expect(screen.getByText('1 paper matching')).toBeInTheDocument()
  })

  it('says when nothing matches the filter', async () => {
    const { user } = setup()
    await screen.findByText('2 papers')

    await user.type(screen.getByPlaceholderText('Filter by title, author, or abstract'), 'zzz')

    expect(await screen.findByText('No saved papers match “zzz”.')).toBeInTheDocument()
  })

  it('removes a paper after confirmation', async () => {
    const { api, user } = setup()
    api.on('DELETE', '/api/papers/1', new Response(null, { status: 204 }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const card = (await screen.findAllByRole('article'))[0]

    await user.click(within(card).getByRole('button', { name: 'Remove' }))

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining(`Remove “${attention.title}” from your library?`))
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1))
    expect(screen.getByText('1 paper')).toBeInTheDocument()
    expect(api.callsTo('DELETE', '/api/papers/1')).toHaveLength(1)
  })

  it('keeps the paper when removal is cancelled', async () => {
    const { api, user } = setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const card = (await screen.findAllByRole('article'))[0]

    await user.click(within(card).getByRole('button', { name: 'Remove' }))

    expect(api.callsTo('DELETE', '/api/papers/1')).toHaveLength(0)
    expect(screen.getAllByRole('article')).toHaveLength(2)
  })

  it('shows why a removal failed and keeps the paper listed', async () => {
    const { api, user } = setup()
    api.on('DELETE', '/api/papers/1', errorResponse(500, 'Internal Server Error'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const card = (await screen.findAllByRole('article'))[0]

    await user.click(within(card).getByRole('button', { name: 'Remove' }))

    expect(await screen.findByText('Internal Server Error')).toBeInTheDocument()
    expect(listedTitles()).toEqual([attention.title, bert.title])
    expect(screen.getByText('2 papers')).toBeInTheDocument()
  })

  it('shows an error when the library cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<LibraryPage />)

    expect(await screen.findByText('Network error: cannot reach the backend.')).toBeInTheDocument()
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
  })

  it('opens an uploaded PDF in the reader', async () => {
    const { api, user } = setup()
    api.on('POST', '/api/papers/upload', jsonResponse(paper({ id: 17, source: 'upload' }), 201))
    await screen.findByText('2 papers')

    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, pdfFile('new-paper.pdf'))

    await waitFor(() => expect(window.location.hash).toBe('#/paper/17'))
    const form = api.callsTo('POST', '/api/papers/upload')[0].body as FormData
    expect((form.get('file') as File).name).toBe('new-paper.pdf')
  })
})
