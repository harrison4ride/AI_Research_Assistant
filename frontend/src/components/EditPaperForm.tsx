import { useState, type FormEvent } from 'react'
import { errorMessage, updatePaper } from '../api'
import type { Paper } from '../types'

interface Props {
  paper: Paper
  onSaved: (paper: Paper) => void
  onCancel: () => void
}

// Lets the user correct metadata that was extracted from a PDF.
export default function EditPaperForm({ paper, onSaved, onCancel }: Props) {
  const [title, setTitle] = useState(paper.title)
  const [authors, setAuthors] = useState(paper.authors.join('\n'))
  const [year, setYear] = useState(paper.year?.toString() ?? '')
  const [abstract, setAbstract] = useState(paper.abstract ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const updated = await updatePaper(paper.id, {
        title: title.trim(),
        authors: authors.split('\n').map((a) => a.trim()).filter(Boolean),
        year: year.trim() ? Number(year) : null,
        abstract: abstract.trim() || null,
      })
      onSaved(updated)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card edit-form" onSubmit={submit}>
      <label>
        Title
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={500} />
      </label>
      <label>
        Authors <span className="muted">(one per line)</span>
        <textarea className="input" rows={4} value={authors} onChange={(e) => setAuthors(e.target.value)} />
      </label>
      <label>
        Year
        <input
          className="input year-input"
          type="number"
          min={1000}
          max={2100}
          value={year}
          onChange={(e) => setYear(e.target.value)}
        />
      </label>
      <label>
        Abstract
        <textarea className="input" rows={8} value={abstract} onChange={(e) => setAbstract(e.target.value)} />
      </label>
      {error && <div className="alert error">{error}</div>}
      <div className="form-actions">
        <button className="btn primary" type="submit" disabled={saving || !title.trim()}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        <button className="btn" type="button" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  )
}
