// Fake timers that React Testing Library and user-event can work with.
//
// Testing Library recognizes fake timers only through a global `jest`: without it, its
// async helpers wait for a real setTimeout(0) that a fake clock never fires, and hang.
// The stub lets them advance Vitest's clock instead. setup.ts restores real timers after
// every test, also one that timed out.
import { vi } from 'vitest'

export function useFakeTimers() {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
  vi.stubGlobal('jest', { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) })
}
