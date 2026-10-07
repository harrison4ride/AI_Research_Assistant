import { useRef, useState, type DragEvent } from 'react'
import { errorMessage, uploadPdf } from '../api'
import type { Paper } from '../types'

export default function UploadBox({ onUploaded }: { onUploaded: (paper: Paper) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function upload(file: File) {
    setError(null)
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setError('Please choose a PDF file.')
      return
    }
    setBusy(file.name)
    try {
      onUploaded(await uploadPdf(file))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
      if (input.current) input.current.value = ''
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && !busy) upload(file)
  }

  return (
    <div
      className={`upload-box${dragging ? ' dragging' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
      />
      {busy ? (
        <p>
          Uploading and reading <strong>{busy}</strong>…
        </p>
      ) : (
        <p>
          <button className="btn primary" onClick={() => input.current?.click()}>
            Upload PDF
          </button>{' '}
          <span className="muted">or drop a paper here. Title, authors, year, and abstract are extracted automatically.</span>
        </p>
      )}
      {error && <div className="alert error">{error}</div>}
    </div>
  )
}
