// A stand-in for the backend: tests register answers per method and path, and every
// request the app makes is recorded. Nothing reaches a real server.
import { vi } from 'vitest'

export interface Call {
  method: string
  path: string
  query: URLSearchParams
  // Parsed JSON for JSON bodies, the FormData for uploads, undefined otherwise.
  body: unknown
  init?: RequestInit
}

type Reply = Response | ((call: Call) => Response | Promise<Response>) | object

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// FastAPI's error shape.
export function errorResponse(status: number, detail: unknown): Response {
  return jsonResponse({ detail }, status)
}

function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

// A finished newline-delimited JSON stream, delivered in the given raw chunks
// (a chunk may end in the middle of an event, as on a real network).
export function ndjsonChunks(chunks: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } })
}

export function ndjson(events: object[]): Response {
  return ndjsonChunks(events.map((e) => `${JSON.stringify(e)}\n`))
}

// A stream that stays open until the test closes it, to check what the UI shows meanwhile.
export function openStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c
    },
  })
  return {
    response: () => new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }),
    send(event: object) {
      controller.enqueue(encode(`${JSON.stringify(event)}\n`))
    },
    close() {
      controller.close()
    },
  }
}

// A reply that stays pending until the test resolves it.
export function deferred() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((r) => {
    resolve = r
  })
  return { reply: () => promise, resolve }
}

function parseBody(body: BodyInit | null | undefined): unknown {
  if (typeof body === 'string') {
    try {
      return JSON.parse(body)
    } catch {
      return body
    }
  }
  return body ?? undefined
}

export function mockFetch() {
  const routes: { method: string; path: string; reply: Reply }[] = []
  const calls: Call[] = []
  const unhandled: string[] = []

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : String(input), 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const call: Call = { method, path: url.pathname, query: url.searchParams, body: parseBody(init?.body), init }
    calls.push(call)
    const route = [...routes].reverse().find((r) => r.method === method && r.path === url.pathname)
    if (!route) {
      unhandled.push(`${method} ${url.pathname}${url.search}`)
      return errorResponse(501, `No mock for ${method} ${url.pathname}`)
    }
    const { reply } = route
    if (typeof reply === 'function') return reply(call)
    if (reply instanceof Response) return reply.clone()
    return jsonResponse(reply)
  })
  vi.stubGlobal('fetch', fetchMock)

  return {
    // Answer `method path` (query string ignored). Later registrations win.
    on(method: string, path: string, reply: Reply) {
      routes.push({ method: method.toUpperCase(), path, reply })
      return this
    },
    calls,
    unhandled,
    callsTo(method: string, path: string): Call[] {
      return calls.filter((c) => c.method === method.toUpperCase() && c.path === path)
    },
  }
}

export type FetchMock = ReturnType<typeof mockFetch>
