// Runs before every test file (see vitest.config.ts).
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

beforeEach(() => {
  // jsdom has no layout engine, so these do nothing useful; the reader calls them.
  Element.prototype.scrollIntoView = vi.fn()
  // Each test starts on the search page with empty storage.
  window.history.replaceState(null, '', '/')
  sessionStorage.clear()
  localStorage.clear()
})

afterEach(() => {
  cleanup()
})
