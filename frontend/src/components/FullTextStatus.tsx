import { useEffect, useRef, useState } from 'react'
import { attachPdf, errorMessage, fetchFullText } from '../api'
import { fullTextFields, type FullTextFields, type Paper } from '../types'

interface Props {
  // Render nothing once the full text is available (the reader shows the PDF instead).
  quietWhenOk?: boolean
  paper: Paper
  // Receives only the full-text fields, so a slow download can't overwrite
  // metadata the user edited while it was running.
  onChange: (fields: FullTextFields) => void
}

// Shows whether the assistant can read the whole paper, fetching the PDF on first view.
export default function FullTextStatus({ paper, onChange, quietWhenOk = false }: Props) {
  // Start busy when a fetch is about to run, so the first frame isn't an empty error box.
  const [busy, setBusy] = useState<string | null>(
    paper.full_text_status === null ? 'Downloading and reading the PDF…' : null,
  )
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  async function run(label: string, request: () => Promise<Paper>) {
    setBusy(label)
    setError(null)
    try {
      onChange(fullTextFields(await request()))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const fetchText = (retry: boolean) =>
    run('Downloading and reading the PDF…', () => fetchFullText(paper.id, retry))

  const attach = (file: File) => run('Uploading and reading the PDF…', () => attachPdf(paper.id, file))

  const status = paper.full_text_status
  useEffect(() => {
    if (status === null) fetchText(false)
    // Only on first view of a paper that was never fetched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paper.id])

  const attachButton = (
    <>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) attach(file)
        }}
      />
      <button className="btn small" onClick={() => fileInput.current?.click()}>
        Attach PDF
      </button>
    </>
  )

  if (busy) {
    return <div className="status-box info">{busy}</div>
  }
  // Checked before `status === null`: a failed first request leaves status null.
  if (error || status === null) {
    return (
      <div className="status-box error">
        {error}{' '}
        <button className="link-button" onClick={() => fetchText(true)}>
          Retry
        </button>
      </div>
    )
  }
  if (status === 'ok') {
    if (quietWhenOk) return null
    return (
      <div className="status-box ok">
        ✓ Full text available{paper.page_count ? ` (${paper.page_count} pages)` : ''}. The assistant
        reads the whole paper.
      </div>
    )
  }
  return (
    <div className="status-box warn">
      <p>
        <strong>Only the abstract is available.</strong> {paper.full_text_error} Summaries and
        answers will be based on the abstract alone. If you have the PDF, attach it so the assistant
        can read the full paper.
      </p>
      <div className="status-actions">
        {attachButton}
        {status === 'error' && (
          <button className="btn small" onClick={() => fetchText(true)}>
            Retry download
          </button>
        )}
      </div>
    </div>
  )
}
