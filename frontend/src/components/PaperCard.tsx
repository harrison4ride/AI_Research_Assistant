import { useState, type ReactNode } from 'react'
import { SOURCE_LABEL, type PaperMeta } from '../types'

const MAX_AUTHORS = 6

export function Authors({ authors }: { authors: string[] }) {
  const [expanded, setExpanded] = useState(false)
  if (authors.length === 0) return <span className="muted">Unknown authors</span>
  const shown = expanded ? authors : authors.slice(0, MAX_AUTHORS)
  const hidden = authors.length - shown.length
  return (
    <span>
      {shown.join(', ')}
      {hidden > 0 && (
        <>
          {', '}
          <button type="button" className="link-button" onClick={() => setExpanded(true)}>
            +{hidden} more
          </button>
        </>
      )}
    </span>
  )
}

interface Props {
  paper: PaperMeta
  // Optional title link target (e.g. the library detail page); falls back to the external URL.
  href?: string
  // If set, clicking the title calls this instead (e.g. open the paper in the reader).
  onOpen?: () => void
  actions?: ReactNode
  // Show the whole abstract without the "show more" toggle (detail page).
  defaultExpanded?: boolean
  // Link to a locally stored copy of the PDF, when the library has one.
  localPdfHref?: string
}

export default function PaperCard({
  paper,
  href,
  actions,
  defaultExpanded = false,
  localPdfHref,
  onOpen,
}: Props) {
  const pdfHref = paper.pdf_url ?? localPdfHref
  const [showFull, setShowFull] = useState(defaultExpanded)
  const titleHref = href ?? paper.url ?? undefined
  const external = !href

  return (
    <article className="card paper-card">
      <div className="paper-card-head">
        <h2 className="paper-title">
          {onOpen ? (
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault()
                onOpen()
              }}
            >
              {paper.title}
            </a>
          ) : titleHref ? (
            <a href={titleHref} {...(external && { target: '_blank', rel: 'noreferrer' })}>
              {paper.title}
            </a>
          ) : (
            paper.title
          )}
        </h2>
        {actions && <div className="paper-actions">{actions}</div>}
      </div>

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

      {paper.abstract ? (
        <div className="abstract-wrap">
          <p className={showFull ? 'abstract' : 'abstract clamped'}>{paper.abstract}</p>
          {!defaultExpanded && (
            <button type="button" className="link-button" onClick={() => setShowFull(!showFull)}>
              {showFull ? 'Show less' : 'Show full abstract'}
            </button>
          )}
        </div>
      ) : (
        <p className="abstract muted">No abstract available.</p>
      )}

      <div className="paper-links">
        <span className={`badge badge-${paper.source}`}>{SOURCE_LABEL[paper.source]}</span>
        {paper.url && (
          <a href={paper.url} target="_blank" rel="noreferrer">
            View paper ↗
          </a>
        )}
        {pdfHref && (
          <a href={pdfHref} target="_blank" rel="noreferrer">
            PDF ↗
          </a>
        )}
        {paper.doi && <span className="muted">DOI: {paper.doi}</span>}
      </div>
    </article>
  )
}
