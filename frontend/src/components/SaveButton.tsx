import { useState } from 'react'
import { errorMessage, savePaper } from '../api'
import type { PaperMeta } from '../types'

interface Props {
  paper: PaperMeta
  savedId: number | undefined
  onSaved: (id: number) => void
}

export default function SaveButton({ paper, savedId, onSaved }: Props) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (savedId !== undefined) {
    return (
      <span className="saved">
        <span className="saved-label">✓ Saved</span>
        <a className="btn small" href={`#/paper/${savedId}`}>
          Open
        </a>
      </span>
    )
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await savePaper(paper)
      onSaved(saved.id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <span className="save-wrap">
      <button className="btn small" onClick={save} disabled={saving}>
        {saving ? 'Saving…' : 'Save to library'}
      </button>
      {error && (
        <span className="save-error" role="alert">
          {error}
        </span>
      )}
    </span>
  )
}
