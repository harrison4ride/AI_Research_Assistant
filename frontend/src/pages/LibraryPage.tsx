import { useEffect, useRef, useState } from 'react'
import { deletePaper, errorMessage, listPapers, localPdfUrl } from '../api'
import PaperCard from '../components/PaperCard'
import UploadBox from '../components/UploadBox'
import type { Paper } from '../types'

export default function LibraryPage() {
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  // A list request that was in flight during a delete must not bring the paper back.
  const deletedIds = useRef(new Set<number>())

  // Debounced server-side filter; a newer keystroke cancels the older request.
  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(() => {
      listPapers(filter.trim() || undefined)
        .then((rows) => {
          if (cancelled) return
          setPapers(rows.filter((p) => !deletedIds.current.has(p.id)))
          setError(null)
        })
        .catch((err) => !cancelled && setError(errorMessage(err)))
    }, 200)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [filter])

  async function remove(paper: Paper) {
    if (!window.confirm(`Remove “${paper.title}” from your library? The app also deletes its summaries, conversation, and stored PDF.`)) return
    try {
      await deletePaper(paper.id)
      deletedIds.current.add(paper.id)
      setPapers((prev) => prev?.filter((p) => p.id !== paper.id) ?? null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>Library</h1>
        {papers && (
          <span className="muted">
            {papers.length} {papers.length === 1 ? 'paper' : 'papers'}
            {filter.trim() && ' matching'}
          </span>
        )}
      </div>

      <UploadBox onUploaded={(paper) => (window.location.hash = `#/paper/${paper.id}`)} />

      <input
        className="input filter-input"
        type="search"
        placeholder="Filter by title, author, or abstract"
        maxLength={200}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {error && <div className="alert error">{error}</div>}

      {papers === null && !error && <p className="muted loading">Loading…</p>}

      {papers?.length === 0 && (
        <div className="empty">
          {filter.trim() ? (
            <p>No saved papers match “{filter.trim()}”.</p>
          ) : (
            <p>
              Your library is empty. <a href="#/search">Search for papers</a>, then save the ones you
              want to keep.
            </p>
          )}
        </div>
      )}

      <div className="paper-list">
        {papers?.map((paper) => (
          <PaperCard
            key={paper.id}
            paper={paper}
            href={`#/paper/${paper.id}`}
            localPdfHref={paper.has_pdf ? localPdfUrl(paper.id) : undefined}
            actions={
              <>
                <a className="btn small primary" href={`#/paper/${paper.id}`}>
                  Open
                </a>
                <button className="btn small danger" onClick={() => remove(paper)}>
                  Remove
                </button>
              </>
            }
          />
        ))}
      </div>
    </section>
  )
}
