// Runs before every test file (see vitest.config.ts).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeEach, vi } from 'vitest'
import { stopWatchingConsoleErrors, watchConsoleErrors } from './console'
import { takeLateRequests, takeUnansweredRequests } from './fetchMock'
import { noteProblem, takeProblems } from './knownBugs'

beforeEach(() => {
  // jsdom has no layout engine, so these do nothing useful; the reader calls them.
  Element.prototype.scrollIntoView = vi.fn()
  // Each test starts on the search page with empty storage.
  window.history.replaceState(null, '', '/')
  sessionStorage.clear()
  localStorage.clear()
  watchConsoleErrors()
})

afterEach(({ task }) => {
  cleanup()
  vi.useRealTimers()
  const errors = stopWatchingConsoleErrors()
  const requests = takeUnansweredRequests()
  const problems = [
    ...requests.map((r) => `The app sent a request that the test did not mock: ${r}`),
    ...errors.map((e) => `Unexpected console.error: ${e}`),
  ]
  if (!problems.length) return
  // Thrown in an expected failure (it.fails), the error would count as the expected one and
  // hide the problem, so it is reported after the file instead (see knownBugs.ts).
  if (task.fails) noteProblem(task.name, problems.join('\n'))
  else throw new Error(problems.join('\n\n'))
})

afterAll(() => {
  const problems = [
    ...takeProblems().map((p) => `An expected-failure test does not fail for the bug it names: ${p}`),
    ...takeLateRequests().map((r) => `The app sent a request that no test mocked: ${r}`),
  ]
  if (problems.length) throw new Error(problems.join('\n\n'))
})
