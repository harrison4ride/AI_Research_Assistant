import type { AppConfig } from '../types'
import RichText from './RichText'

// Explains why summaries and Q&A are unavailable, with the fix from the backend.
export default function LlmNotice({ llm }: { llm: AppConfig }) {
  return (
    <div className="status-box warn">
      <p>
        <strong>Summaries and Q&amp;A are unavailable.</strong> <RichText text={llm.llm_hint ?? ''} />
      </p>
    </div>
  )
}
