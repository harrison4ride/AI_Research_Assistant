import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { deferred, errorResponse, jsonResponse, mockFetch } from '../test/fetchMock'
import { bert, paper, searchResponse, searchResult } from '../test/fixtures'
import { itFailsUntilFixed } from '../test/knownBugs'
import type { SavedKey } from '../types'
import SearchPage from './SearchPage'

function setup(savedKeys: SavedKey[] = []) {
  const api = mockFetch().on('GET', '/api/papers/keys', savedKeys)
  const user = userEvent.setup()
  const view = render(<SearchPage />)
  return { api, user, view }
}

async function search(user: ReturnType<typeof userEvent.setup>, query: string) {
  await user.clear(screen.getByRole('searchbox'))
  await user.type(screen.getByRole('searchbox'), query)
  await user.click(screen.getByRole('button', { name: 'Search' }))
}

describe('SearchPage', () => {
  it('offers example searches before the first search', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))

    await user.click(screen.getByRole('button', { name: 'attention is all you need' }))

    expect(await screen.findByText('Attention Is All You Need')).toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('attention is all you need')
    expect(api.callsTo('GET', '/api/search')[0].query.get('q')).toBe('attention is all you need')
    expect(screen.queryByText('Try one of these:')).not.toBeInTheDocument()
  })

  it('shows each result with title, authors, year, venue, abstract, and links', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult(), bert], { query: 'transformers', total: 1234 }))

    await search(user, 'transformers')

    // The total is formatted for the user's locale (1,234 in English, 1.234 in German).
    const total = (1234).toLocaleString()
    expect(await screen.findByText(`Showing 2 of ${total} results for “transformers” from OpenAlex`)).toBeInTheDocument()
    const [first] = screen.getAllByRole('article')
    const card = within(first)
    expect(card.getByRole('link', { name: 'Attention Is All You Need' })).toBeInTheDocument()
    expect(card.getByText('Ashish Vaswani, Noam Shazeer')).toBeInTheDocument()
    expect(card.getByText('2017')).toBeInTheDocument()
    expect(card.getByText('NeurIPS')).toBeInTheDocument()
    expect(card.getByText(/The dominant sequence transduction models/)).toBeInTheDocument()
    expect(card.getByRole('link', { name: 'View paper ↗' })).toHaveAttribute('href', 'https://arxiv.org/abs/1706.03762')
    expect(card.getByRole('link', { name: 'PDF ↗' })).toHaveAttribute('href', 'https://arxiv.org/pdf/1706.03762')
    expect(card.getByText('DOI: 10.48550/arXiv.1706.03762')).toBeInTheDocument()
  })

  it('sends the query with the chosen source and first page', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([], { source: 'arxiv' }))

    await user.selectOptions(screen.getByRole('combobox', { name: 'Search source' }), 'arxiv')
    await search(user, '  retrieval augmented generation  ')

    await waitFor(() => expect(api.callsTo('GET', '/api/search')).toHaveLength(1))
    expect(Object.fromEntries(api.callsTo('GET', '/api/search')[0].query)).toEqual({
      q: 'retrieval augmented generation',
      source: 'arxiv',
      page: '1',
      per_page: '10',
    })
  })

  it('cannot search for an empty query', async () => {
    const { api, user } = setup()

    await user.type(screen.getByRole('searchbox'), '   ')

    expect(screen.getByRole('button', { name: 'Search' })).toBeDisabled()
    await user.type(screen.getByRole('searchbox'), '{Enter}')
    expect(api.callsTo('GET', '/api/search')).toHaveLength(0)
  })

  it('shows that a search is running', async () => {
    const { api, user } = setup()
    const pending = deferred()
    api.on('GET', '/api/search', pending.reply)

    await search(user, 'diffusion')

    expect(screen.getByRole('button', { name: 'Searching…' })).toBeDisabled()
    pending.resolve(jsonResponse(searchResponse([searchResult()])))
    expect(await screen.findByRole('button', { name: 'Search' })).toBeEnabled()
  })

  it('says so when nothing was found', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([], { query: 'qwertyuiop', total: 0 }))

    await search(user, 'qwertyuiop')

    expect(await screen.findByText('No results for “qwertyuiop”.')).toBeInTheDocument()
  })

  it('shows the error from the backend', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', errorResponse(504, 'OpenAlex timed out, please try again.'))

    await search(user, 'rag')

    expect(await screen.findByText('OpenAlex timed out, please try again.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Search OpenAlex instead' })).not.toBeInTheDocument()
  })

  it('offers OpenAlex when arXiv fails', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', (call) =>
      call.query.get('source') === 'arxiv'
        ? errorResponse(429, 'arXiv is limiting requests right now, so it is paused for about 60 s.')
        : jsonResponse(searchResponse([searchResult()], { query: 'rag' })),
    )
    await user.selectOptions(screen.getByRole('combobox', { name: 'Search source' }), 'arxiv')
    await search(user, 'rag')
    expect(await screen.findByText(/arXiv is limiting requests/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Search OpenAlex instead' }))

    expect(await screen.findByText('Attention Is All You Need')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Search source' })).toHaveValue('openalex')
    expect(screen.queryByText(/arXiv is limiting requests/)).not.toBeInTheDocument()
    // README: it "runs the same query on OpenAlex".
    const [failed, retried] = api.callsTo('GET', '/api/search')
    expect(Object.fromEntries(failed.query)).toEqual({ q: 'rag', source: 'arxiv', page: '1', per_page: '10' })
    expect(Object.fromEntries(retried.query)).toEqual({ q: 'rag', source: 'openalex', page: '1', per_page: '10' })
  })

  // Confirmed app bug: the button reads the search box when clicked, not the query that failed.
  // README: "If an arXiv search fails, “Search OpenAlex instead” runs the same query on OpenAlex."
  itFailsUntilFixed('runs the query that failed on OpenAlex even after the search box was edited', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', (call) =>
      call.query.get('source') === 'arxiv'
        ? errorResponse(504, 'arXiv did not answer in time.')
        : jsonResponse(searchResponse([searchResult()], { query: 'rag' })),
    )
    await user.selectOptions(screen.getByRole('combobox', { name: 'Search source' }), 'arxiv')
    await search(user, 'rag')
    expect(await screen.findByText('arXiv did not answer in time.')).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox'), ' evaluation') // not searched yet

    await user.click(screen.getByRole('button', { name: 'Search OpenAlex instead' }))

    await waitFor(() => expect(api.callsTo('GET', '/api/search')).toHaveLength(2))
    expect(await screen.findByText('Attention Is All You Need')).toBeInTheDocument()
    return () => expect(api.callsTo('GET', '/api/search')[1].query.get('q')).toBe('rag')
  })

  // Confirmed app bug: the button appears whenever an error is shown while arXiv is selected in
  // the menu, so a failed OpenAlex search offers to "Search OpenAlex instead" once the menu is
  // switched to arXiv. README offers it only after an arXiv search fails.
  itFailsUntilFixed('offers OpenAlex only after an arXiv search failed', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', errorResponse(504, 'OpenAlex timed out, please try again.'))
    await search(user, 'rag') // on OpenAlex, the default
    expect(await screen.findByText('OpenAlex timed out, please try again.')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Search source' }), 'arxiv')

    return () => expect(screen.queryByRole('button', { name: 'Search OpenAlex instead' })).not.toBeInTheDocument()
  })

  it('replaces the results with those of a new search', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', (call) =>
      jsonResponse(
        call.query.get('q') === 'bert'
          ? searchResponse([bert], { query: 'bert' })
          : searchResponse([searchResult()], { query: 'attention' }),
      ),
    )
    await search(user, 'attention')
    await screen.findByText('Attention Is All You Need')

    await search(user, 'bert')

    expect(await screen.findByText(bert.title)).toBeInTheDocument()
    expect(screen.queryByText('Attention Is All You Need')).not.toBeInTheDocument()
    expect(screen.getByText('Showing 1 of 1 results for “bert” from OpenAlex')).toBeInTheDocument()
  })

  it('loads more results page by page without duplicates', async () => {
    const { api, user } = setup()
    const page1 = Array.from({ length: 10 }, (_, i) => searchResult({ external_id: `W${i}`, title: `Paper ${i}` }))
    const page2 = [searchResult({ external_id: 'W9', title: 'Paper 9' }), searchResult({ external_id: 'W10', title: 'Paper 10' })]
    api.on('GET', '/api/search', (call) =>
      jsonResponse(
        call.query.get('page') === '1'
          ? searchResponse(page1, { query: 'many', total: 11 })
          : searchResponse(page2, { query: 'many', total: 11, page: 2 }),
      ),
    )

    await search(user, 'many')
    expect(await screen.findByText('Showing 10 of 11 results for “many” from OpenAlex')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Paper 10')).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(11) // "Paper 9" came twice, shown once
    expect(api.callsTo('GET', '/api/search')[1].query.get('page')).toBe('2')
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('stops offering more after page 100, the last page the backend serves', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', (call) => {
      const page = Number(call.query.get('page'))
      const result = searchResult({ external_id: `W${page}`, title: `Paper ${page}` })
      return jsonResponse(searchResponse([result], { query: 'many', total: 100_000, page }))
    })
    await search(user, 'many')
    await screen.findByText('Paper 1')

    // (Text queries: role queries get slow on a list of 100 results.)
    for (let page = 2; page <= 100; page++) {
      fireEvent.click(await screen.findByText('Load more', { selector: 'button' }))
      await screen.findByText(`Paper ${page}`)
    }

    expect(screen.queryByText('Load more')).not.toBeInTheDocument()
    const pages = api.callsTo('GET', '/api/search').map((call) => Number(call.query.get('page')))
    expect(pages).toEqual(Array.from({ length: 100 }, (_, i) => i + 1))
  }, 20_000) // 99 clicks on a growing list

  it('stops offering more when a page adds nothing new', async () => {
    const { api, user } = setup()
    const results = [searchResult({ external_id: 'W1', title: 'Only paper' })]
    api.on('GET', '/api/search', (call) =>
      jsonResponse(searchResponse(results, { query: 'q', total: 50, page: Number(call.query.get('page')) })),
    )

    await search(user, 'q')
    await user.click(await screen.findByRole('button', { name: 'Load more' }))

    await waitFor(() => expect(api.callsTo('GET', '/api/search')).toHaveLength(2))
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('saves a result to the library', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))
    api.on('POST', '/api/papers', jsonResponse(paper({ id: 5 }), 201))
    await search(user, 'attention')

    await user.click(await screen.findByRole('button', { name: 'Save to library' }))

    expect(await screen.findByText('✓ Saved')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '#/paper/5')
    expect(api.callsTo('POST', '/api/papers')[0].body).toEqual(searchResult())
  })

  it('shows why saving failed and lets the user try again', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))
    api.on('POST', '/api/papers', errorResponse(500, 'Internal Server Error'))
    await search(user, 'attention')

    await user.click(await screen.findByRole('button', { name: 'Save to library' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Internal Server Error')
    expect(screen.getByRole('button', { name: 'Save to library' })).toBeEnabled()
  })

  it('marks results that are already in the library', async () => {
    const { api, user } = setup([{ source: 'openalex', external_id: bert.external_id!, id: 42 }])
    api.on('GET', '/api/search', searchResponse([searchResult(), bert]))

    await search(user, 'attention')

    const saved = await screen.findByText('✓ Saved')
    expect(saved.closest('article')).toHaveTextContent(bert.title)
    expect(within(saved.closest('article')!).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '#/paper/42')
    expect(screen.getAllByRole('button', { name: 'Save to library' })).toHaveLength(1)
  })

  it('opens a result in the reader without saving it', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))
    api.on('POST', '/api/papers/open', jsonResponse(paper({ id: 9, in_library: false }), 201))
    await search(user, 'attention')

    await user.click(await screen.findByRole('button', { name: 'Read' }))

    await waitFor(() => expect(window.location.hash).toBe('#/paper/9'))
    expect(api.callsTo('POST', '/api/papers/open')[0].body).toEqual(searchResult())
    expect(api.callsTo('POST', '/api/papers')).toHaveLength(0)
  })

  it('opens a result by clicking its title', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))
    api.on('POST', '/api/papers/open', jsonResponse(paper({ id: 3, in_library: false }), 201))
    await search(user, 'attention')

    await user.click(await screen.findByRole('link', { name: 'Attention Is All You Need' }))

    await waitFor(() => expect(window.location.hash).toBe('#/paper/3'))
  })

  it('reports when a result cannot be opened', async () => {
    const { api, user } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()]))
    api.on('POST', '/api/papers/open', errorResponse(422, 'external_id is required for a search result.'))
    await search(user, 'attention')

    await user.click(await screen.findByRole('button', { name: 'Read' }))

    expect(await screen.findByText('external_id is required for a search result.')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })

  it('keeps the last search when the user comes back to the page', async () => {
    const { api, user, view } = setup()
    api.on('GET', '/api/search', searchResponse([searchResult()], { query: 'attention' }))
    await search(user, 'attention')
    await screen.findByText('Attention Is All You Need')
    view.unmount()

    render(<SearchPage />)

    expect(screen.getByText('Attention Is All You Need')).toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('attention')
    expect(api.callsTo('GET', '/api/search')).toHaveLength(1)
  })
})
