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
  // False for a paper opened from search but not saved to the library.
  in_library: boolean
  saved_at: string | null
  has_pdf: boolean
  page_count: number | null
  // null = not attempted yet
  full_text_status: 'ok' | 'unavailable' | 'error' | null
  full_text_error: string | null
}

export type ContextKind = 'full_text' | 'abstract'

// A paper with its stored summary (returned by GET /api/papers/{id}).
export interface PaperDetail extends Paper {
  summary: string | null
  summary_model: string | null
  summary_context: ContextKind | null
  summary_created_at: string | null
}

export type SummaryFields = Pick<
  PaperDetail,
  'summary' | 'summary_model' | 'summary_context' | 'summary_created_at'
>

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  model: string | null
  context: ContextKind | null
  created_at: string
}

export interface ModelOption {
  id: string
  label: string
}

export interface AppConfig {
  llm_provider: 'claude-code' | 'api'
  llm_model: string // human-readable label, e.g. "Claude Code (opus)"
  llm_ready: boolean // whether summaries and Q&A can run
  llm_hint: string | null // how to fix it when not ready
  llm_models: ModelOption[] // what the model menu offers
  llm_default_model: string
  cached_paper_days: number // unsaved papers are deleted after this many days unopened
}

export interface OutlineSection {
  level: number
  title: string
  page: number | null // 1-based
  top: number | null // position on the page: 0 = top, 1 = bottom
  summary: string | null
}

export interface Outline {
  available: boolean
  reason: string | null
  sections: OutlineSection[]
  summarized: boolean
  model: string | null
  summarized_at: string | null
}

// Events streamed (as newline-delimited JSON) by the summary and chat endpoints.
export type StreamEvent =
  | { type: 'meta'; context: ContextKind; truncated: boolean }
  | { type: 'text'; text: string }
  | { type: 'reset' }
  | { type: 'error'; message: string }
  | { type: 'done'; paper?: PaperDetail; messages?: ChatMessage[] }

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
