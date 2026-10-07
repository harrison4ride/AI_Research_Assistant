import { useEffect, useState } from 'react'
import { ApiError, deletePaper, errorMessage, getPaper } from '../api'
import PaperCard from '../components/PaperCard'
import type { Paper } from '../types'

export default function PaperPage({ id }: { id: number }) {
  const [paper, setPaper] = useState<Paper | null>(null)
  const [error, setError] = useState<string | null>(null)

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
          <PaperCard
            paper={paper}
            defaultExpanded
            actions={
              <button className="btn small danger" onClick={remove}>
                Remove
              </button>
            }
          />
          <p className="muted saved-on">
            Saved {new Date(paper.created_at).toLocaleString()}
          </p>
        </>
      )}
    </section>
  )
}
