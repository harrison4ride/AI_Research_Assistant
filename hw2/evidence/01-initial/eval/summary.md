# Evaluation of `hw2-initial` (31076dc)

## Execution

| Suite | Total | Passed | Failed | Skipped | xfail | Seconds |
|-------|-------|--------|--------|---------|-------|---------|
| Backend (pytest) | 360 | 360 | 0 | 0 | 0 | 17.4 |
| Frontend (Vitest) | 148 | 148 | 0 | 0 | 0 | 6.5 |
| End-to-end (Playwright) | 14 | runs: 13/14, 14/14, 14/14, 14/14 | | | | |

End-to-end tests that failed in at least one run: e2e/upload-summary-chat.spec.ts > summarize the sections and jump to one

## Coverage

| Suite | Line % | Branch % |
|-------|--------|----------|
| Backend | 94.4 | 87.5 |
| Frontend | 81.2 | 78.47 |

## Stability (5 shuffled runs per suite)

- backend: 0 unstable test(s)
- frontend: 0 unstable test(s)

## Hermeticity

- backend tests that fail only without network: 0

## Assertions

- backend: 257 test functions in 11 files, 2.39 assertions per test; 0 without assertions; 4 that check only the status code
- frontend: 140 tests in 14 files, 2.29 expect() per test; 0 without expect()

## Notes

- suite does not declare @vitest/coverage-v8; harness installed 5.1.0 for measurement only
