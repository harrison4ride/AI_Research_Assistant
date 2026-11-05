# Evaluation of `hw2-initial` (31076dc)

## Execution

| Suite | Total | Passed | Failed | Skipped | xfail | Seconds |
|-------|-------|--------|--------|---------|-------|---------|
| Backend (pytest) | 360 | 360 | 0 | 0 | 0 | 17.4 |
| Frontend (Vitest) | 148 | 148 | 0 | 0 | 0 | 6.5 |

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

## Held-out seeded faults

Detected 17/18 (backend 12/12, frontend 5/6; HW1-history faults 7/8).

| Fault | Detected | Detecting tests |
|-------|----------|-----------------|
| B01 | yes | 1 |
| B02 | yes | 2 |
| B03 | yes | 1 |
| B04 | yes | 3 |
| B05 | yes | 1 |
| B06 | yes | 2 |
| B07 | yes | 72 |
| B08 | yes | 3 |
| B09 | yes | 16 |
| B10 | yes | 1 |
| B11 | yes | 1 |
| B12 | yes | 2 |
| F01 | yes | 1 |
| F02 | no | 0 |
| F03 | yes | 3 |
| F04 | yes | 1 |
| F05 | yes | 1 |
| F06 | yes | 3 |

## Assertions

- backend: 257 test functions in 11 files, 2.39 assertions per test; 0 without assertions; 4 that check only the status code
- frontend: 140 tests in 14 files, 2.29 expect() per test; 0 without expect()

## Notes

- suite does not declare @vitest/coverage-v8; harness installed 5.1.0 for measurement only
