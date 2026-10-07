// Thin wrapper around fetch for the backend's JSON API.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
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
