import { useEffect, useState } from 'react'
import { ApiError, deletePaper, errorMessage, getPaper, localPdfUrl } from '../api'
import EditPaperForm from '../components/EditPaperForm'
import FullTextStatus from '../components/FullTextStatus'
import PaperCard from '../components/PaperCard'
import type { Paper } from '../types'

export default function PaperPage({ id }: { id: number }) {
  const [paper, setPaper] = useState<Paper | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

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
        </>
      )}
    </section>
  )
}
