import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, deletePaper, errorMessage, getConfig, getPaper, localPdfUrl, saveToLibrary } from '../api'
import ChatPanel from '../components/ChatPanel'
import EditPaperForm from '../components/EditPaperForm'
import ErrorBoundary from '../components/ErrorBoundary'
import FullTextStatus from '../components/FullTextStatus'
import ModelSelect from '../components/ModelSelect'
import PaperCard, { Authors } from '../components/PaperCard'
import type { PdfViewerHandle } from '../components/PdfViewer'
import SectionsPanel from '../components/SectionsPanel'
import SummaryPanel from '../components/SummaryPanel'
import { canGoBack } from '../router'
import { SOURCE_LABEL, type AppConfig, type PaperDetail } from '../types'
import { useModelChoice } from '../useModelChoice'

// PDF.js is large; load it only when a paper is opened.
const PdfViewer = lazy(() => import('../components/PdfViewer'))

type Tab = 'sections' | 'summary' | 'details'

// The reader: sections on the left, the PDF in the middle, Q&A on the right.
// Used for every paper, whether it is in the library or only opened from search.
interface Props {
  id: number
  // Tells the app whether this paper is in the library (for the top navigation).
  onLibraryState?: (inLibrary: boolean) => void
}

export default function PaperPage({ id, onLibraryState }: Props) {
  const [paper, setPaper] = useState<PaperDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [llm, setLlm] = useState<AppConfig | null>(null)
  const [model, setModel] = useModelChoice(llm)
  const [tab, setTab] = useState<Tab>('sections')
  const [position, setPosition] = useState(1)
  const [saving, setSaving] = useState(false)
  const viewer = useRef<PdfViewerHandle>(null)
  const center = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (paper) onLibraryState?.(paper.in_library)
  }, [paper, onLibraryState])

  useEffect(() => {
    let latest = 0
    let lastLoad = 0
    let ready = true
    const load = () => {
      const id = ++latest
      lastLoad = Date.now()
      getConfig()
        .then((config) => {
          if (id !== latest) return // a newer check already answered
          ready = config.llm_ready
          setLlm(config)
        })
        .catch(() => {
          // Unknown: let the LLM requests themselves report problems.
        })
    }
    // While the LLM is unavailable, recheck when the user returns to the tab
    // (e.g. after `claude auth login`), at most once every 5 seconds.
    const onFocus = () => {
      if (!ready && Date.now() - lastLoad > 5000) load()
    }
    load()
    window.addEventListener('focus', onFocus)
    return () => {
      latest = -1 // ignore responses that arrive after unmount
      window.removeEventListener('focus', onFocus)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getPaper(id)
      .then((p) => !cancelled && setPaper(p))
      .catch((err) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.status === 404 ? 'This paper is no longer available.' : errorMessage(err),
        )
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const update = useCallback((fields: Partial<PaperDetail>) => {
    setPaper((prev) => (prev ? { ...prev, ...fields } : prev))
  }, [])

  async function save() {
    if (!paper) return
    setSaving(true)
    try {
      update({ in_library: (await saveToLibrary(paper.id)).in_library })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!paper || !window.confirm(`Remove “${paper.title}” from your library? The app also deletes its summaries, conversation, and stored PDF.`)) return
    try {
      await deletePaper(paper.id)
      window.location.hash = '#/library'
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  function back() {
    if (canGoBack()) window.history.back()
    else window.location.hash = '#/library'
  }

  function jumpTo(page: number, top: number | null) {
    viewer.current?.scrollTo(page, top)
    // In the stacked (narrow) layout the PDF can be off-screen: bring it into view.
    const rect = center.current?.getBoundingClientRect()
    if (rect && (rect.bottom < 80 || rect.top > window.innerHeight - 80)) {
      center.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  if (!paper) {
    return (
      <section className="reader">
        <button type="button" className="link-button back-link" onClick={back}>
          ← Back
        </button>
        {error ? <div className="alert error">{error}</div> : <p className="muted loading">Opening the paper…</p>}
      </section>
    )
  }

  return (
    <section className="reader">
      <header className="reader-head">
        <div className="reader-title">
          <button type="button" className="link-button back-link" onClick={back}>
            ← Back
          </button>
          <h1>{paper.title}</h1>
          <div className="paper-meta">
            <Authors authors={paper.authors} />
            <span className="dot">·</span>
            <span>{paper.year ?? 'Year unknown'}</span>
            {paper.venue && (
              <>
                <span className="dot">·</span>
                <span className="venue">{paper.venue}</span>
              </>
            )}
          </div>
        </div>
        <div className="reader-actions">
          <ModelSelect llm={llm} value={model} onChange={setModel} />
          {paper.in_library ? (
            <span className="saved-label">✓ In library</span>
          ) : (
            <button className="btn small primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save to library'}
            </button>
          )}
          {paper.url && (
            <a className="btn small" href={paper.url} target="_blank" rel="noreferrer">
              {paper.source === 'upload' ? 'Source' : SOURCE_LABEL[paper.source]} ↗
            </a>
          )}
          {paper.in_library && (
            <button className="btn small danger" onClick={remove}>
              Remove
            </button>
          )}
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="reader-body">
        <aside className="reader-col reader-left">
          <div className="panel-tabs" role="tablist">
            {(['sections', 'summary', 'details'] as Tab[]).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={tab === t ? 'tab active' : 'tab'}
                onClick={() => setTab(t)}
              >
                {t === 'sections' ? 'Sections' : t === 'summary' ? 'Summary' : 'Details'}
              </button>
            ))}
          </div>
          {tab === 'sections' && (
            <SectionsPanel
              paper={paper}
              llm={llm}
              model={model}
              position={position}
              onJump={jumpTo}
            />
          )}
          {tab === 'summary' && <SummaryPanel paper={paper} llm={llm} model={model} onSummary={update} />}
          {tab === 'details' &&
            (editing ? (
              <EditPaperForm
                paper={paper}
                onSaved={(p) => {
                  setPaper(p)
                  setEditing(false)
                }}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <>
                <PaperCard
                  paper={paper}
                  defaultExpanded
                  localPdfHref={paper.has_pdf ? localPdfUrl(paper.id) : undefined}
                  actions={
                    <button className="btn small" onClick={() => setEditing(true)}>
                      Edit details
                    </button>
                  }
                />
                <p className="muted saved-on">
                  {paper.in_library ? 'Saved' : 'First opened'}{' '}
                  {new Date((paper.in_library && paper.saved_at) || paper.created_at).toLocaleString()}
                  {!paper.in_library &&
                    ` · not in your library yet; save it to keep it (unsaved papers are deleted after ${
                      llm ? `${llm.cached_paper_days} day${llm.cached_paper_days === 1 ? '' : 's'}` : 'a while'
                    } without being opened)`}
                </p>
              </>
            ))}
        </aside>

        <div className="reader-col reader-center" ref={center}>
          <FullTextStatus paper={paper} onChange={update} quietWhenOk />
          {paper.has_pdf ? (
            <ErrorBoundary
              fallback={
                <div className="alert error">
                  The PDF viewer could not be loaded.{' '}
                  <a href={localPdfUrl(paper.id)} target="_blank" rel="noreferrer">
                    Open the PDF
                  </a>{' '}
                  instead, or reload the page.
                </div>
              }
            >
              <Suspense fallback={<p className="muted pdf-message">Loading the PDF viewer…</p>}>
                <PdfViewer ref={viewer} url={localPdfUrl(paper.id)} onPositionChange={setPosition} />
              </Suspense>
            </ErrorBoundary>
          ) : (
            <div className="no-pdf card">
              <h2>Abstract</h2>
              <p className="abstract">{paper.abstract ?? 'No abstract available.'}</p>
            </div>
          )}
        </div>

        <aside className="reader-col reader-right">
          <ChatPanel paperId={paper.id} llm={llm} model={model} />
        </aside>
      </div>
    </section>
  )
}
