// Sample API data in the shapes the backend returns (see src/types.ts).
import type { AppConfig, ChatMessage, Outline, PaperDetail, PaperMeta, SearchResponse } from '../types'

export function searchResult(overrides: Partial<PaperMeta> = {}): PaperMeta {
  return {
    source: 'openalex',
    external_id: 'W2741809807',
    title: 'Attention Is All You Need',
    authors: ['Ashish Vaswani', 'Noam Shazeer'],
    year: 2017,
    abstract: 'The dominant sequence transduction models are based on complex recurrent networks.',
    url: 'https://arxiv.org/abs/1706.03762',
    pdf_url: 'https://arxiv.org/pdf/1706.03762',
    venue: 'NeurIPS',
    doi: '10.48550/arXiv.1706.03762',
    ...overrides,
  }
}

export const bert = searchResult({
  external_id: 'W2963341956',
  title: 'BERT: Pre-training of Deep Bidirectional Transformers',
  authors: ['Jacob Devlin', 'Ming-Wei Chang'],
  year: 2019,
  abstract: 'We introduce a new language representation model called BERT.',
  url: 'https://aclanthology.org/N19-1423',
  pdf_url: null,
  venue: 'NAACL',
  doi: '10.18653/v1/N19-1423',
})

export function searchResponse(results: PaperMeta[], overrides: Partial<SearchResponse> = {}): SearchResponse {
  return { query: 'attention', source: 'openalex', page: 1, per_page: 10, total: results.length, results, ...overrides }
}

export function paper(overrides: Partial<PaperDetail> = {}): PaperDetail {
  return {
    ...searchResult(),
    id: 1,
    created_at: '2026-10-01T12:00:00Z',
    in_library: true,
    saved_at: '2026-10-01T12:00:00Z',
    has_pdf: false,
    page_count: null,
    full_text_status: 'unavailable',
    full_text_error: 'No open-access PDF link is known for this paper.',
    summary: null,
    summary_model: null,
    summary_context: null,
    summary_created_at: null,
    ...overrides,
  }
}

export function config(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    llm_provider: 'claude-code',
    llm_model: 'Claude Code (opus)',
    llm_ready: true,
    llm_hint: null,
    llm_models: [
      { id: 'opus', label: 'Opus' },
      { id: 'sonnet', label: 'Sonnet' },
    ],
    llm_default_model: 'opus',
    cached_paper_days: 7,
    ...overrides,
  }
}

export function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 1,
    role: 'user',
    content: 'What problem does this paper address?',
    model: null,
    context: null,
    created_at: '2026-10-01T12:00:00Z',
    ...overrides,
  }
}

export function outline(overrides: Partial<Outline> = {}): Outline {
  return {
    available: true,
    reason: null,
    sections: [
      { level: 1, title: '1 Introduction', page: 1, top: 0.3, summary: null },
      { level: 1, title: '2 Method', page: 2, top: 0.1, summary: null },
      { level: 2, title: '2.1 Retriever', page: 2, top: 0.5, summary: null },
    ],
    summarized: false,
    model: null,
    summarized_at: null,
    ...overrides,
  }
}

export function pdfFile(name = 'paper.pdf'): File {
  return new File(['%PDF-1.7 test'], name, { type: 'application/pdf' })
}
