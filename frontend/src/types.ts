// Shapes returned by the backend API (mirror backend/app/schemas.py).

export type SearchSource = 'arxiv' | 'openalex'
export type PaperSource = SearchSource | 'upload'

export interface PaperMeta {
  source: PaperSource
  external_id: string | null
  title: string
  authors: string[]
  year: number | null
  abstract: string | null
  url: string | null
  pdf_url: string | null
  venue: string | null
  doi: string | null
}

// A paper stored in the local library.
export interface Paper extends PaperMeta {
  id: number
  created_at: string
  has_pdf: boolean
  page_count: number | null
  // null = not attempted yet
  full_text_status: 'ok' | 'unavailable' | 'error' | null
  full_text_error: string | null
}

// The fields that change when a paper's full text is fetched or attached.
export type FullTextFields = Pick<
  Paper,
  'has_pdf' | 'page_count' | 'full_text_status' | 'full_text_error'
>

export function fullTextFields(p: Paper): FullTextFields {
  return {
    has_pdf: p.has_pdf,
    page_count: p.page_count,
    full_text_status: p.full_text_status,
    full_text_error: p.full_text_error,
  }
}

export interface PaperUpdate {
  title?: string
  authors?: string[]
  year?: number | null
  abstract?: string | null
}

export interface SavedKey {
  source: string
  external_id: string
  id: number
}

export interface SearchResponse {
  query: string
  source: SearchSource
  page: number
  per_page: number
  total: number | null
  results: PaperMeta[]
}

export const SOURCE_LABEL: Record<PaperSource, string> = {
  arxiv: 'arXiv',
  openalex: 'OpenAlex',
  upload: 'Uploaded PDF',
}

// Stable identity for a search result (external ids are unique per source).
export function sourceKey(source: string, id: string): string {
  return `${source}:${id}`
}

export function paperKey(p: PaperMeta): string {
  return sourceKey(p.source, p.external_id ?? p.url ?? p.doi ?? p.title)
}
