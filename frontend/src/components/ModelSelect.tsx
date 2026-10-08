import type { AppConfig } from '../types'

// Which Claude model writes summaries and answers; remembered in this browser.
export default function ModelSelect({
  llm,
  value,
  onChange,
}: {
  llm: AppConfig | null
  value: string | null
  onChange: (id: string) => void
}) {
  if (!llm || llm.llm_models.length === 0) return null
  return (
    <label className="model-select" title="Model used for section summaries, the summary, and answers">
      <span className="muted">Model</span>
      <select className="input" value={value ?? llm.llm_default_model} onChange={(e) => onChange(e.target.value)}>
        {llm.llm_models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </label>
  )
}
