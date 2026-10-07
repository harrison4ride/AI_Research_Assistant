export default function LlmKeyNotice() {
  return (
    <div className="status-box warn">
      <p>
        No Anthropic API key is configured. Add <code>ANTHROPIC_API_KEY=…</code> to the{' '}
        <code>.env</code> file in the project root and restart the backend.
      </p>
    </div>
  )
}
