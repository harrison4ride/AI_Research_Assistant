// Thin wrapper around fetch for the backend's JSON API.

import type { Paper, PaperMeta, SavedKey, SearchResponse, SearchSource } from './types'

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
  return apiFetch<Paper>(`/api/papers/${id}`)
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
