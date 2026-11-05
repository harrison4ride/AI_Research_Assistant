// Confirmed app bugs that are not fixed yet. Each has exactly one test, an expected failure
// (Vitest's it.fails) of the correct behavior, written like this:
//
//   itFailsUntilFixed('runs the query that failed on OpenAlex …', async () => {
//     … the steps up to where the bug shows: these must all work …
//     return () => expect(…).toBe(…) // the one check that the bug breaks
//   })
//
// A plain it.fails counts any failure as the expected one: a renamed button, a console error,
// or a request no test mocked (setup.ts checks those after each test) would pass as expected
// and hide a fix. Here only the returned check may fail, and only with an assertion error.
// Anything else fails the test file, which says at its end what happened: a step before the
// check failed, the check failed on something other than an assertion, or the check passed
// (in these cases the test itself fails too, with "Expect test to fail"); or the app logged
// an error or sent an unmocked request. When the check passes, the bug is fixed: turn the
// test into a normal one.
import { it } from 'vitest'

const problems: string[] = []

// Records why an expected-failure test does not fail for its bug (setup.ts throws them after the file).
export function noteProblem(test: string, problem: string) {
  problems.push(`“${test}”: ${problem}`)
}

export function takeProblems(): string[] {
  return problems.splice(0)
}

function firstLine(error: unknown): string {
  return (error instanceof Error ? error.message : String(error)).split('\n')[0]
}

// expect() throws AssertionError; jest-dom's matchers (added with expect.extend) throw JestExtendError.
function isAssertionError(error: unknown): boolean {
  return error instanceof Error && (error.name === 'AssertionError' || error.constructor.name === 'JestExtendError')
}

export function itFailsUntilFixed(name: string, steps: () => Promise<() => unknown>) {
  it.fails(name, async () => {
    let check: () => unknown
    try {
      check = await steps()
    } catch (error) {
      noteProblem(name, `a step before the check of the bug failed: ${firstLine(error)}`)
      return
    }
    try {
      await check()
    } catch (error) {
      if (isAssertionError(error)) throw error // the bug is still there: the expected failure
      noteProblem(name, `the check of the bug failed, but not on an assertion: ${firstLine(error)}`)
      return
    }
    noteProblem(name, 'the check of the bug passes, so the bug seems fixed: make this a normal test')
  })
}
