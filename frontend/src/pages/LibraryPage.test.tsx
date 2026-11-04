import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { bert, paper, pdfFile } from '../test/fixtures'
import LibraryPage from './LibraryPage'

const attention = paper({ id: 1 })
const bertPaper = paper({ ...bert, id: 2, has_pdf: true, page_count: 14, full_text_status: 'ok' })

function setup(papers = [attention, bertPaper]) {
  const api = mockFetch().on('GET', '/api/papers', (call) => {
    const q = call.query.get('q')?.toLowerCase()
    return jsonResponse(q ? papers.filter((p) => p.title.toLowerCase().includes(q)) : papers)
  })
  const user = userEvent.setup()
  render(<LibraryPage />)
  return { api, user }
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

  it('links to the stored PDF of a paper that has one', async () => {
    setup()

    const card = (await screen.findAllByRole('article'))[1]

    expect(within(card).getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', '/api/papers/2/pdf')
  })

  it('explains an empty library', async () => {
    setup([])

    expect(await screen.findByText(/Your library is empty/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Search for papers' })).toHaveAttribute('href', '#/search')
    expect(screen.getByText('0 papers')).toBeInTheDocument()
  })

  it('filters on the server as the user types', async () => {
    const { api, user } = setup()
    await screen.findByText('2 papers')

    await user.type(screen.getByPlaceholderText('Filter by title, author, or abstract'), 'bert')

    expect(await screen.findByText('1 paper matching')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(1)
    // Debounced: one request for the whole word, not one per keystroke.
    expect(api.callsTo('GET', '/api/papers').map((c) => c.query.get('q'))).toEqual([null, 'bert'])
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

  it('shows why a removal failed', async () => {
    const { api, user } = setup()
    api.on('DELETE', '/api/papers/1', errorResponse(404, 'Paper not found.'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const card = (await screen.findAllByRole('article'))[0]

    await user.click(within(card).getByRole('button', { name: 'Remove' }))

    expect(await screen.findByText('Paper not found.')).toBeInTheDocument()
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
  })
})
