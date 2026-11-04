import { describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiFetch,
  attachPdf,
  deletePaper,
  fetchFullText,
  listPapers,
  savePaper,
  searchPapers,
  streamAnswer,
  streamSummary,
  updatePaper,
  uploadPdf,
} from './api'
import { errorResponse, jsonResponse, mockFetch, ndjson, ndjsonChunks } from './test/fetchMock'
import { pdfFile, searchResult } from './test/fixtures'
import type { StreamEvent } from './types'

describe('apiFetch', () => {
  it('returns the parsed JSON body', async () => {
    mockFetch().on('GET', '/api/health', { status: 'ok' })

    await expect(apiFetch('/api/health')).resolves.toEqual({ status: 'ok' })
  })

  it('uses the error detail from the backend as the message', async () => {
    mockFetch().on('GET', '/api/papers/9', errorResponse(404, 'Paper not found.'))

    const error = await apiFetch('/api/papers/9').catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'Paper not found.' })
  })

  it('names the field of each validation error', async () => {
    mockFetch().on(
      'GET',
      '/api/search',
      errorResponse(422, [
        { loc: ['query', 'q'], msg: 'String should have at most 300 characters' },
        { loc: ['query', 'page'], msg: 'Input should be greater than or equal to 1' },
      ]),
    )

    await expect(apiFetch('/api/search')).rejects.toThrow(
      'q: String should have at most 300 characters; page: Input should be greater than or equal to 1',
    )
  })

  it('falls back to the HTTP status when the error body is not JSON', async () => {
    mockFetch().on('GET', '/api/x', new Response('<html>Bad gateway</html>', { status: 502, statusText: 'Bad Gateway' }))

    await expect(apiFetch('/api/x')).rejects.toMatchObject({ status: 502, message: '502 Bad Gateway' })
  })

  it('reports an unreachable backend in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(apiFetch('/api/health')).rejects.toMatchObject({
      status: 0,
      message: 'Network error: cannot reach the backend.',
    })
  })

  it('returns nothing for 204 No Content', async () => {
    mockFetch().on('DELETE', '/api/papers/3', new Response(null, { status: 204 }))

    await expect(deletePaper(3)).resolves.toBeUndefined()
  })

  it('rejects a successful answer that is not JSON (e.g. the dev server HTML page)', async () => {
    mockFetch().on('GET', '/api/papers', new Response('<!doctype html>', { headers: { 'Content-Type': 'text/html' } }))

    await expect(listPapers()).rejects.toThrow('Unexpected non-JSON response from /api/papers')
  })
})

describe('requests', () => {
  it('searches with the query, source, and page', async () => {
    const api = mockFetch().on('GET', '/api/search', { results: [] })

    await searchPapers('graph neural networks', 'arxiv', 2, 10)

    const [call] = api.calls
    expect(Object.fromEntries(call.query)).toEqual({
      q: 'graph neural networks',
      source: 'arxiv',
      page: '2',
      per_page: '10',
    })
  })

  it('filters the library only when a filter is given', async () => {
    const api = mockFetch().on('GET', '/api/papers', [])

    await listPapers()
    await listPapers('müller')

    expect(api.calls.map((c) => c.query.get('q'))).toEqual([null, 'müller'])
  })

  it('saves a search result as JSON', async () => {
    const api = mockFetch().on('POST', '/api/papers', jsonResponse({ id: 5 }, 201))
    const meta = searchResult()

    await expect(savePaper(meta)).resolves.toEqual({ id: 5 })

    expect(api.calls[0].body).toEqual(meta)
    expect(api.calls[0].init?.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it.each([
    ['uploads', '/api/papers/upload', (file: File) => uploadPdf(file)],
    ['attaches', '/api/papers/4/pdf', (file: File) => attachPdf(4, file)],
  ])('%s a PDF as multipart form data', async (_, path, send) => {
    const api = mockFetch().on('POST', path, jsonResponse({ id: 8 }, 201))
    const file = pdfFile('my paper.pdf')

    await send(file)

    const [call] = api.calls
    const form = call.body as FormData
    expect(form).toBeInstanceOf(FormData)
    expect(form.get('file')).toBe(file)
    // The browser must write the Content-Type itself: only it knows the multipart boundary.
    expect(new Headers(call.init?.headers).has('Content-Type')).toBe(false)
  })

  it('edits metadata with PATCH', async () => {
    const api = mockFetch().on('PATCH', '/api/papers/4', { id: 4 })

    await updatePaper(4, { title: 'New title', year: null })

    expect(api.calls[0].body).toEqual({ title: 'New title', year: null })
  })

  it('asks for a retry of the full-text download only when requested', async () => {
    const api = mockFetch().on('POST', '/api/papers/4/fulltext', { id: 4 })

    await fetchFullText(4)
    await fetchFullText(4, true)

    expect(api.calls.map((c) => c.query.get('retry'))).toEqual([null, 'true'])
  })
})

describe('streamed answers', () => {
  const signal = () => new AbortController().signal

  it('delivers every event, also when one is split across network chunks', async () => {
    mockFetch().on(
      'POST',
      '/api/papers/7/summary',
      ndjsonChunks([
        '{"type":"meta","context":"full_text","truncated":false}\n{"type":"te',
        'xt","text":"Hel"}\n',
        '{"type":"text","text":"lo"}\n\n{"type":"done"}', // last event without a newline
      ]),
    )
    const events: StreamEvent[] = []

    await streamSummary(7, null, (e) => events.push(e), signal())

    expect(events).toEqual([
      { type: 'meta', context: 'full_text', truncated: false },
      { type: 'text', text: 'Hel' },
      { type: 'text', text: 'lo' },
      { type: 'done' },
    ])
  })

  it('sends the chosen model with a summary request', async () => {
    const api = mockFetch().on('POST', '/api/papers/7/summary', ndjsonChunks([]))

    await streamSummary(7, 'sonnet', () => {}, signal())
    await streamSummary(7, null, () => {}, signal())

    expect(api.calls.map((c) => c.query.get('model'))).toEqual(['sonnet', null])
    expect(api.calls[0].body).toBeUndefined()
  })

  it('posts a question with the chosen model', async () => {
    const api = mockFetch().on('POST', '/api/papers/7/chat', ndjsonChunks([]))

    await streamAnswer(7, 'What datasets are used?', 'opus', () => {}, signal())

    expect(api.calls[0].body).toEqual({ question: 'What datasets are used?', model: 'opus' })
  })

  it('reports an error answer before the stream starts', async () => {
    mockFetch().on('POST', '/api/papers/7/chat', errorResponse(422, 'Unknown model “gpt-4o”.'))

    await expect(streamAnswer(7, 'Why?', 'gpt-4o', () => {}, signal())).rejects.toMatchObject({
      status: 422,
      message: 'Unknown model “gpt-4o”.',
    })
  })

  it('passes a cancellation through instead of calling it a network error', async () => {
    // Like a browser, this fetch rejects only when the request's own signal is aborted.
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((resolve, reject) => {
            const signal = init?.signal
            if (!signal) return resolve(ndjson([{ type: 'done' }]))
            signal.addEventListener('abort', () => reject(signal.reason))
          }),
      ),
    )
    const controller = new AbortController()

    const answer = streamSummary(7, null, () => {}, controller.signal)
    controller.abort()

    await expect(answer).rejects.toMatchObject({ name: 'AbortError' })
    await expect(answer).rejects.not.toBeInstanceOf(ApiError)
  })

  it('reports an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(streamSummary(7, null, () => {}, signal())).rejects.toThrow('Network error: cannot reach the backend.')
  })
})
