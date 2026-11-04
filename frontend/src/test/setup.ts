// Runs before every test file (see vitest.config.ts).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import { stopWatchingConsoleErrors, watchConsoleErrors } from './console'
import { takeUnansweredRequests } from './fetchMock'

beforeEach(() => {
  // jsdom has no layout engine, so these do nothing useful; the reader calls them.
  Element.prototype.scrollIntoView = vi.fn()
  // Each test starts on the search page with empty storage.
  window.history.replaceState(null, '', '/')
  sessionStorage.clear()
  localStorage.clear()
  watchConsoleErrors()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  const errors = stopWatchingConsoleErrors()
  const requests = takeUnansweredRequests()
  const problems = [
    ...requests.map((r) => `The app sent a request that the test did not mock: ${r}`),
    ...errors.map((e) => `Unexpected console.error: ${e}`),
  ]
  if (problems.length) throw new Error(problems.join('\n\n'))
})
