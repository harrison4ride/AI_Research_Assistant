import { useEffect, useState } from 'react'
import { ApiError, deletePaper, errorMessage, getConfig, getPaper, localPdfUrl } from '../api'
import ChatPanel from '../components/ChatPanel'
import EditPaperForm from '../components/EditPaperForm'
import FullTextStatus from '../components/FullTextStatus'
import PaperCard from '../components/PaperCard'
import SummaryPanel from '../components/SummaryPanel'
import type { AppConfig, PaperDetail } from '../types'

export default function PaperPage({ id }: { id: number }) {
  const [paper, setPaper] = useState<PaperDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [llm, setLlm] = useState<AppConfig | null>(null)

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
          err instanceof ApiError && err.status === 404
            ? 'This paper is not in your library.'
            : errorMessage(err),
        )
      })
    return () => {
      cancelled = true
    }
  }, [id])

  async function remove() {
    if (!paper || !window.confirm(`Remove “${paper.title}” from your library?`)) return
    try {
      await deletePaper(paper.id)
      window.location.hash = '#/library'
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section>
      <a className="back-link" href="#/library">
        ← Library
      </a>
      {error && <div className="alert error">{error}</div>}
      {!paper && !error && <p className="muted loading">Loading…</p>}
      {paper && (
        <>
          {editing ? (
            <EditPaperForm
              paper={paper}
              onSaved={(p) => {
                setPaper(p)
                setEditing(false)
              }}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <PaperCard
              paper={paper}
              defaultExpanded
              localPdfHref={paper.has_pdf ? localPdfUrl(paper.id) : undefined}
              actions={
                <>
                  <button className="btn small" onClick={() => setEditing(true)}>
                    Edit details
                  </button>
                  <button className="btn small danger" onClick={remove}>
                    Remove
                  </button>
                </>
              }
            />
          )}
          <p className="muted saved-on">Saved {new Date(paper.created_at).toLocaleString()}</p>
          <FullTextStatus
            paper={paper}
            onChange={(fields) => setPaper((prev) => (prev ? { ...prev, ...fields } : prev))}
          />
          <SummaryPanel
            paper={paper}
            llm={llm}
            onSummary={(fields) => setPaper((prev) => (prev ? { ...prev, ...fields } : prev))}
          />
          <ChatPanel paperId={paper.id} llm={llm} />
        </>
      )}
    </section>
  )
}
