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
export function paperKey(p: PaperMeta): string {
  return `${p.source}:${p.external_id ?? p.url ?? p.doi ?? p.title}`
}
