import { useEffect, useState } from 'react'
import { errorMessage, getOutline, summarizeOutline } from '../api'
import type { AppConfig, Outline, OutlineSection, PaperDetail } from '../types'
import RichText from './RichText'

interface Props {
  paper: PaperDetail
  llm: AppConfig | null
  model: string | null
  position: number // reading position in the PDF: page + fraction of that page
  onJump: (page: number, top: number | null) => void
}

// The paper's sections (from its PDF); one-sentence summaries are generated on request.
export default function SectionsPanel({ paper, llm, model, position, onJump }: Props) {
  const [outline, setOutline] = useState<Outline | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [summarizing, setSummarizing] = useState(false)

  // Reload when the paper gains a PDF (download finished or one was attached).
  useEffect(() => {
    let cancelled = false
    getOutline(paper.id)
      .then((o) => {
        if (cancelled) return
        setOutline(o)
        setError(null)
      })
      .catch((err) => !cancelled && setError(errorMessage(err)))
    return () => {
      cancelled = true
    }
  }, [paper.id, paper.has_pdf])

  async function summarize() {
    setSummarizing(true)
    setError(null)
    try {
      setOutline(await summarizeOutline(paper.id, model))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSummarizing(false)
    }
  }

  if (!outline) {
    return error ? <div className="alert error">{error}</div> : <p className="muted thinking">Reading the paper's structure…</p>
  }
  if (!outline.available) {
    return <p className="muted">{outline.reason ?? 'No outline is available for this paper.'}</p>
  }

  // The section being read: the one starting furthest down, but at or above the
  // reading position (two-column papers list headings out of page order).
  // Infinity means the view is at the end of the document: the last section.
  let active: OutlineSection | undefined
  for (const s of outline.sections) {
    if (s.page === null) continue
    const start = s.page + (s.top ?? 0)
    // The viewer measures a little below a jumped-to heading, so no slack is
    // needed here; slack would let a subsection just below count as reached.
    if (start <= position + 0.002 && (!active || start >= (active.page ?? 0) + (active.top ?? 0))) active = s
  }
  const llmOff = llm?.llm_ready === false

  return (
    <div className="sections">
      <div className="sections-actions">
        <button className={outline.summarized ? 'btn small' : 'btn small primary'} onClick={summarize} disabled={summarizing || llmOff}>
          {summarizing ? 'Summarizing…' : outline.summarized ? 'Regenerate summaries' : 'Summarize sections'}
        </button>
        {outline.summarized && outline.model && <span className="muted provenance">by {outline.model}</span>}
      </div>
      {summarizing && (
        <p className="muted thinking">Writing one sentence per section. This reads the whole paper and can take up to a minute…</p>
      )}
      {error && (
        <div className="alert error">
          <RichText text={error} />
        </div>
      )}
      {outline.sections.length === 0 ? (
        <p className="muted">
          No section headings were found in this PDF. “Summarize sections” asks the model to identify them.
        </p>
      ) : (
        <ol className="section-list">
          {outline.sections.map((s, i) => (
            <li key={i} className={`section-item level-${s.level}${s === active ? ' active' : ''}`}>
              <button
                type="button"
                className="section-link"
                onClick={() => s.page !== null && onJump(s.page, s.top)}
                disabled={s.page === null}
                title={s.page !== null ? `Go to page ${s.page}` : 'Not found in the PDF'}
              >
                <span className="section-title">{s.title}</span>
                {s.page !== null && <span className="section-page">p. {s.page}</span>}
              </button>
              {s.summary && <p className="section-summary">{s.summary}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
