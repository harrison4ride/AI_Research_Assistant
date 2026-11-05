// Fails a test that logs an error it did not expect (setup.ts checks after each test).
// React reports render loops, act() problems, failed prop types, and caught render errors
// through console.error; a test that passes while React complains is not a passing test.
const original = console.error
let unexpected: string[] = []
let allowed: { pattern: RegExp; seen: string[] }[] = []

// console.error's own formatting: "%s" placeholders (as React uses), then the other arguments.
function format(...args: unknown[]): string {
  const [first, ...rest] = args
  if (typeof first !== 'string') return args.map(String).join(' ')
  let next = 0
  const text = first.replace(/%[sdifoOc%]/g, (token) => {
    if (token === '%%') return '%'
    const value = rest[next++]
    return token === '%c' ? '' : String(value)
  })
  return [text, ...rest.slice(next).map(String)].join(' ')
}

// Let the current test log errors matching these patterns (e.g. an error the test causes on
// purpose). Returns the matching errors as they are logged, for a test that checks them.
export function allowConsoleErrors(...patterns: RegExp[]): string[] {
  const seen: string[] = []
  allowed.push(...patterns.map((pattern) => ({ pattern, seen })))
  return seen
}

export function watchConsoleErrors() {
  unexpected = []
  allowed = []
  console.error = (...args: unknown[]) => {
    const text = format(...args)
    const match = allowed.find(({ pattern }) => pattern.test(text))
    if (match) match.seen.push(text)
    else unexpected.push(text)
  }
}

// Restores console.error and returns what was logged without being allowed.
export function stopWatchingConsoleErrors(): string[] {
  console.error = original
  return unexpected
}
