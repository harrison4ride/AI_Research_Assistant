import { useEffect, useRef, useState, type FormEvent } from 'react'
import { searchPapers } from '../api'
import PaperCard from '../components/PaperCard'
import { paperKey, SOURCE_LABEL, type PaperMeta, type SearchSource } from '../types'

const PER_PAGE = 10
const MAX_PAGE = 100 // backend limit on the `page` parameter
const STORAGE_KEY = 'search-state'
const EXAMPLES = [
  'retrieval augmented generation',
  'graph neural networks drug discovery',
  'attention is all you need',
]

interface SearchState {
  query: string
  source: SearchSource
  results: PaperMeta[]
  page: number
  total: number | null
  searched: boolean
  // Set when a page adds nothing new, so "Load more" stops offering dead clicks.
  exhausted: boolean
}

const EMPTY: SearchState = {
  query: '',
  source: 'arxiv',
  results: [],
  page: 0,
  total: null,
  searched: false,
  exhausted: false,
}

// Keep the last search across tab switches and page refreshes.
function loadState(): SearchState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return { ...EMPTY, ...JSON.parse(raw) }
  } catch {
    // Storage unavailable or corrupt; start fresh.
  }
  return EMPTY
}

// Rankings can shift between page requests, so a paper may appear on two pages.
function appendUnique(existing: PaperMeta[], next: PaperMeta[]): PaperMeta[] {
  const seen = new Set(existing.map(paperKey))
  return [...existing, ...next.filter((p) => !seen.has(paperKey(p)))]
}

export default function SearchPage() {
  const [state, setState] = useState<SearchState>(loadState)
  const [input, setInput] = useState(state.query)
  const [source, setSource] = useState<SearchSource>(state.source)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Only the most recent request may update the page; older responses are dropped.
  const requestId = useRef(0)

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Ignore quota / privacy-mode errors.
    }
  }, [state])

  async function run(query: string, src: SearchSource, page: number) {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const res = await searchPapers(query, src, page, PER_PAGE)
      if (id !== requestId.current) return
      setState((prev) => {
        const results = appendUnique(page === 1 ? [] : prev.results, res.results)
        const prevCount = page === 1 ? 0 : prev.results.length
        return {
          query: res.query,
          source: res.source,
          page: res.page,
          total: res.total,
          searched: true,
          results,
          exhausted: results.length === prevCount,
        }
      })
    } catch (err) {
      if (id !== requestId.current) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const q = input.trim()
    if (q) run(q, source, 1)
  }

  function tryExample(q: string) {
    setInput(q)
    run(q, source, 1)
  }

  const hasMore =
    !state.exhausted &&
    state.page < MAX_PAGE &&
    state.total !== null &&
    state.results.length < state.total

  return (
    <section>
      <h1>Search papers</h1>
      <form className="search-form" onSubmit={onSubmit}>
        <input
          className="input search-input"
          type="search"
          placeholder="Keywords or a research topic, e.g. retrieval augmented generation"
          value={input}
          maxLength={300}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
        />
        <select
          className="input"
          value={source}
          onChange={(e) => setSource(e.target.value as SearchSource)}
          aria-label="Search source"
        >
          <option value="arxiv">{SOURCE_LABEL.arxiv}</option>
          <option value="openalex">{SOURCE_LABEL.openalex}</option>
        </select>
        <button className="btn primary" type="submit" disabled={loading || !input.trim()}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>
      <p className="hint muted">
        arXiv results always include a PDF, so the assistant can read the full paper. OpenAlex covers
        all publishers, but full text is only available for open-access papers.
      </p>

      {error && <div className="alert error">{error}</div>}

      {!state.searched && !loading && (
        <div className="empty">
          <p>Try one of these:</p>
          <div className="chips">
            {EXAMPLES.map((q) => (
              <button key={q} type="button" className="chip" onClick={() => tryExample(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {state.searched && (
        <p className="result-count muted">
          {state.total === 0
            ? `No results for “${state.query}”.`
            : `Showing ${state.results.length}${
                state.total !== null ? ` of ${state.total.toLocaleString()}` : ''
              } results for “${state.query}” from ${SOURCE_LABEL[state.source]}`}
        </p>
      )}

      <div className="paper-list">
        {state.results.map((paper) => (
          <PaperCard key={paperKey(paper)} paper={paper} />
        ))}
      </div>

      {loading && <p className="muted loading">Searching…</p>}

      {hasMore && !loading && (
        <div className="load-more">
          <button className="btn" onClick={() => run(state.query, state.source, state.page + 1)}>
            Load more
          </button>
        </div>
      )}
    </section>
  )
}
