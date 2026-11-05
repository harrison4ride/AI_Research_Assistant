# Evaluation of `hw2-round2` (379d0cb)

## Execution

| Suite | Total | Passed | Failed | Skipped | xfail | Seconds |
|-------|-------|--------|--------|---------|-------|---------|
| Backend (pytest) | 558 | 553 | 0 | 0 | 5 | 24.3 |
| Frontend (Vitest) | 190 | 190 | 0 | 0 | 0 | 10.4 |
| End-to-end (Playwright) | 15 | runs: 15/15, 15/15, 15/15, 15/15 | | | | |

## Coverage

| Suite | Line % | Branch % |
|-------|--------|----------|
| Backend | 98.6 | 95.7 |
| Frontend | 94.78 | 86.09 |

## Stability (5 shuffled runs per suite)

- backend: 0 unstable test(s)
- frontend: 0 unstable test(s)

## Hermeticity

- backend tests that fail only without network: 0

## Assertions

- backend: 361 test functions in 12 files, 2.59 assertions per test; 0 without assertions; 3 that check only the status code
- frontend: 166 tests in 16 files, 2.59 expect() per test; 2 without expect()

## Notes

- suite does not declare @vitest/coverage-v8; harness installed 5.1.0 for measurement only
