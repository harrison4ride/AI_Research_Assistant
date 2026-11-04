import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { StreamEvent } from './types'
import { useLlmStream } from './useLlmStream'

// A request whose events and end the test controls.
function controlledRequest() {
  const request = {
    signal: undefined as AbortSignal | undefined,
    send: (_event: StreamEvent) => {},
    finish: () => {},
    open: (onEvent: (e: StreamEvent) => void, signal: AbortSignal) =>
      new Promise<void>((resolve) => {
        request.signal = signal
        request.send = onEvent
        request.finish = resolve
      }),
  }
  return request
}

describe('useLlmStream', () => {
  it('stops a running request when a new one starts, and ignores what the old one still sends', async () => {
    const { result } = renderHook(() => useLlmStream())
    const first = controlledRequest()
    const second = controlledRequest()
    const firstDone = vi.fn()

    act(() => void result.current.start(first.open, firstDone))
    act(() => first.send({ type: 'text', text: 'Old answer' }))
    expect(result.current.text).toBe('Old answer')

    act(() => void result.current.start(second.open, vi.fn()))
    expect(first.signal?.aborted).toBe(true)
    expect(second.signal?.aborted).toBe(false)

    act(() => {
      first.send({ type: 'text', text: ' still arriving' })
      first.send({ type: 'done' })
      second.send({ type: 'text', text: 'New answer' })
    })
    await act(async () => first.finish())

    expect(result.current.text).toBe('New answer')
    expect(firstDone).not.toHaveBeenCalled()
    expect(result.current.running).toBe(true) // the new request is still running
    await act(async () => second.finish())
  })

  it('stops the running request when the component goes away', () => {
    const { result, unmount } = renderHook(() => useLlmStream())
    const request = controlledRequest()
    act(() => void result.current.start(request.open, vi.fn()))

    unmount()

    expect(request.signal?.aborted).toBe(true)
  })
})
