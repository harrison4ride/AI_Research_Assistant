import { useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'
import type { ContextKind, StreamEvent } from './types'

type DoneEvent = Extract<StreamEvent, { type: 'done' }>
type Open = (onEvent: (e: StreamEvent) => void, signal: AbortSignal) => Promise<void>

// Runs one streamed LLM request at a time and exposes its live state.
// The request is aborted when the component unmounts.
export function useLlmStream() {
  const [text, setText] = useState('')
  const [context, setContext] = useState<{ kind: ContextKind; truncated: boolean } | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  // Resolves to true when the answer completed and was saved.
  async function start(open: Open, onDone: (e: DoneEvent) => void): Promise<boolean> {
    controller.current?.abort()
    const ctrl = new AbortController()
    controller.current = ctrl
    setText('')
    setContext(null)
    setError(null)
    setRunning(true)
    let finished = false
    let failed = false
    try {
      await open((e) => {
        if (ctrl.signal.aborted) return
        switch (e.type) {
          case 'meta':
            setContext({ kind: e.context, truncated: e.truncated })
            break
          case 'text':
            setText((t) => t + e.text)
            break
          case 'reset':
            setText('')
            break
          case 'error':
            failed = true
            setError(e.message)
            break
          case 'done':
            finished = true
            onDone(e)
            break
        }
      }, ctrl.signal)
      if (!finished && !failed && !ctrl.signal.aborted) {
        setError('The response ended unexpectedly. Please try again.')
      }
    } catch (err) {
      if (!ctrl.signal.aborted) setError(errorMessage(err))
    } finally {
      if (controller.current === ctrl) setRunning(false)
    }
    return finished
  }

  return { text, context, running, error, start }
}
