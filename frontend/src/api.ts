// Thin wrapper around fetch for the backend's JSON API.

import type {
  AppConfig,
  ChatMessage,
  Paper,
  PaperDetail,
  PaperMeta,
  PaperUpdate,
  SavedKey,
  SearchResponse,
  SearchSource,
  StreamEvent,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// FastAPI returns `detail` as a string for HTTPException and as a list of
// {loc, msg} objects for request-validation (422) errors.
function describeDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d?.msg !== 'string') return null
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .filter(Boolean)
    if (msgs.length) return msgs.join('; ')
  }
  return null
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    message = describeDetail(body?.detail) ?? message
  } catch {
    // Non-JSON error body; keep the status text.
  }
  return new ApiError(res.status, message)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Network error: cannot reach the backend.')
  }
  if (!res.ok) throw await errorFrom(res)
  if (res.status === 204) return undefined as T
  if (!res.headers.get('content-type')?.includes('application/json')) {
    throw new ApiError(res.status, `Unexpected non-JSON response from ${path}`)
  }
  return res.json() as Promise<T>
}

export function getHealth() {
  return apiFetch<{ status: string }>('/api/health')
}

export function searchPapers(q: string, source: SearchSource, page: number, perPage: number) {
  const params = new URLSearchParams({ q, source, page: String(page), per_page: String(perPage) })
  return apiFetch<SearchResponse>(`/api/search?${params}`)
}

export function listPapers(q?: string) {
  const params = q ? `?${new URLSearchParams({ q })}` : ''
  return apiFetch<Paper[]>(`/api/papers${params}`)
}

export function getSavedKeys() {
  return apiFetch<SavedKey[]>('/api/papers/keys')
}

export function getPaper(id: number) {
  return apiFetch<PaperDetail>(`/api/papers/${id}`)
}

export function savePaper(meta: PaperMeta) {
  return apiFetch<Paper>('/api/papers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(meta),
  })
}

export function deletePaper(id: number) {
  return apiFetch<void>(`/api/papers/${id}`, { method: 'DELETE' })
}

function pdfForm(file: File) {
  const form = new FormData()
  form.append('file', file)
  return form
}

export function uploadPdf(file: File) {
  return apiFetch<Paper>('/api/papers/upload', { method: 'POST', body: pdfForm(file) })
}

// Attach a PDF to an existing library entry (e.g. one with no open-access PDF).
export function attachPdf(id: number, file: File) {
  return apiFetch<Paper>(`/api/papers/${id}/pdf`, { method: 'POST', body: pdfForm(file) })
}

export function updatePaper(id: number, patch: PaperUpdate) {
  return apiFetch<PaperDetail>(`/api/papers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function fetchFullText(id: number, retry = false) {
  return apiFetch<Paper>(`/api/papers/${id}/fulltext${retry ? '?retry=true' : ''}`, { method: 'POST' })
}

export function localPdfUrl(id: number) {
  return `/api/papers/${id}/pdf`
}

export function getConfig() {
  return apiFetch<AppConfig>('/api/config')
}

// POST and read a newline-delimited JSON event stream, calling onEvent per event.
async function streamEvents(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (signal.aborted) throw err
    throw new ApiError(0, 'Network error: cannot reach the backend.')
  }
  if (!res.ok) throw await errorFrom(res)
  if (!res.body) throw new ApiError(res.status, 'The response has no body.')

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as StreamEvent)
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as StreamEvent)
}

export function streamSummary(id: number, onEvent: (e: StreamEvent) => void, signal: AbortSignal) {
  return streamEvents(`/api/papers/${id}/summary`, undefined, onEvent, signal)
}

export function streamAnswer(
  id: number,
  question: string,
  onEvent: (e: StreamEvent) => void,
  signal: AbortSignal,
) {
  return streamEvents(`/api/papers/${id}/chat`, { question }, onEvent, signal)
}

export function getChat(id: number) {
  return apiFetch<ChatMessage[]>(`/api/papers/${id}/chat`)
}

export function clearChat(id: number) {
  return apiFetch<void>(`/api/papers/${id}/chat`, { method: 'DELETE' })
}
