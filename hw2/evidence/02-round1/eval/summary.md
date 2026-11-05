# Evaluation of `hw2-round1` (043c901)

## Execution

| Suite | Total | Passed | Failed | Skipped | xfail | Seconds |
|-------|-------|--------|--------|---------|-------|---------|
| Backend (pytest) | 458 | 448 | 0 | 0 | 10 | 22.6 |
| Frontend (Vitest) | 189 | 189 | 0 | 0 | 0 | 11.4 |
| End-to-end (Playwright) | 15 | runs: 15/15, 15/15, 15/15, 15/15 | | | | |

## Coverage

| Suite | Line % | Branch % |
|-------|--------|----------|
| Backend | 97.0 | 91.7 |
| Frontend | 94.62 | 86.09 |

## Stability (5 shuffled runs per suite)

- backend: 0 unstable test(s)
- frontend: 0 unstable test(s)

## Hermeticity

- backend tests that fail only without network: 0

## Held-out seeded faults

Detected 17/18 (backend 12/12, frontend 5/6; HW1-history faults 7/8).

| Fault | Detected | Detecting tests |
|-------|----------|-----------------|
| B01 | yes | 1 |
| B02 | yes | 2 |
| B03 | yes | 1 |
| B04 | yes | 4 |
| B05 | yes | 1 |
| B06 | yes | 2 |
| B07 | yes | 98 |
| B08 | yes | 4 |
| B09 | yes | 19 |
| B10 | yes | 3 |
| B11 | yes | 1 |
| B12 | yes | 2 |
| F01 | yes | 1 |
| F02 | no | 0 |
| F03 | yes | 3 |
| F04 | yes | 1 |
| F05 | yes | 1 |
| F06 | yes | 3 |

## Assertions

- backend: 304 test functions in 12 files, 2.69 assertions per test; 0 without assertions; 3 that check only the status code
- frontend: 169 tests in 16 files, 2.55 expect() per test; 2 without expect()

## Notes

- suite does not declare @vitest/coverage-v8; harness installed 5.1.0 for measurement only
