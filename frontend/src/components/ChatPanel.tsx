import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { clearChat, errorMessage, getChat, streamAnswer } from '../api'
import { useLlmStream } from '../useLlmStream'
import type { AppConfig, ChatMessage } from '../types'
import LlmNotice from './LlmNotice'
import Markdown from './Markdown'
import RichText from './RichText'

// Example questions from the assignment; one click asks them.
const SUGGESTIONS = [
  'What problem does this paper address?',
  'What is the main idea of the proposed approach?',
  'What datasets are used?',
  'What are the major limitations?',
  'How does this method compare with the baselines?',
]

interface Props {
  paperId: number
  llm: AppConfig | null
}

export default function ChatPanel({ paperId, llm }: Props) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const stream = useLlmStream()
  const log = useRef<HTMLDivElement>(null)
  // Follow new text only while the user is at the bottom; scrolling up to
  // reread an earlier answer stops the auto-scroll.
  const stickToBottom = useRef(true)

  useEffect(() => {
    let cancelled = false
    getChat(paperId)
      .then((m) => !cancelled && setMessages(m))
      .catch((err) => !cancelled && setLoadError(errorMessage(err)))
    return () => {
      cancelled = true
    }
  }, [paperId])

  useLayoutEffect(() => {
    if (log.current && stickToBottom.current) log.current.scrollTop = log.current.scrollHeight
  }, [messages, stream.text, pending])

  function onScroll() {
    const el = log.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }

  async function ask(question: string) {
    const q = question.trim()
    if (!q || stream.running) return
    stickToBottom.current = true
    setPending(q)
    setInput('')
    const ok = await stream.start(
      (onEvent, signal) => streamAnswer(paperId, q, onEvent, signal),
      (e) => e.messages && setMessages((prev) => [...(prev ?? []), ...e.messages!]),
    )
    setPending(null)
    // On failure, give the question back so the user can retry or edit it.
    if (!ok) setInput((current) => current || q)
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    ask(input)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      ask(input)
    }
  }

  async function clear() {
    if (!window.confirm('Clear this conversation?')) return
    try {
      await clearChat(paperId)
      setMessages([])
    } catch (err) {
      setLoadError(errorMessage(err))
    }
  }

  const disabled = llm?.llm_ready === false
  const hasHistory = (messages?.length ?? 0) > 0
  return (
    <section className="card panel">
      <div className="panel-head">
        <h2>Ask about this paper</h2>
        {hasHistory && (
          <button className="btn small" onClick={clear} disabled={stream.running}>
            Clear conversation
          </button>
        )}
      </div>

      {llm && disabled && <LlmNotice llm={llm} />}
      {loadError && <div className="alert error">{loadError}</div>}

      {(hasHistory || pending) && (
        <div className="chat-log" ref={log} onScroll={onScroll}>
          {messages?.map((m) => (
            <div key={m.id} className={`bubble ${m.role}`}>
              {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : <p>{m.content}</p>}
              {m.role === 'assistant' && m.context === 'abstract' && (
                <p className="muted provenance">Based on the abstract only.</p>
              )}
            </div>
          ))}
          {pending && (
            <>
              <div className="bubble user">
                <p>{pending}</p>
              </div>
              <div className="bubble assistant">
                {stream.text ? (
                  <Markdown>{stream.text}</Markdown>
                ) : (
                  !stream.error && <p className="muted thinking">Reading the paper…</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {stream.error && (
        <div className="alert error">
          <RichText text={stream.error} />
        </div>
      )}

      <div className="chips suggestions">
        {SUGGESTIONS.map((q) => (
          <button key={q} type="button" className="chip" onClick={() => ask(q)} disabled={disabled || stream.running}>
            {q}
          </button>
        ))}
      </div>

      <form className="ask-form" onSubmit={onSubmit}>
        <textarea
          className="input"
          rows={2}
          maxLength={4000}
          placeholder="Ask a question about this paper. Enter to send, Shift+Enter for a new line."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
        />
        <button className="btn primary" type="submit" disabled={disabled || stream.running || !input.trim()}>
          {stream.running ? 'Answering…' : 'Ask'}
        </button>
      </form>
    </section>
  )
}
