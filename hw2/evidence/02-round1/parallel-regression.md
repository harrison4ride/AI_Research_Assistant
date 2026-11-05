# Round 1 regression: the backend suite is no longer safe to run in parallel

Found on 2026-11-04 while checking why round 1's first (parallel) mutation run
reported 99.0%, inconsistent with `pdf.py` still having 19 unexecuted lines.

## Evidence

| Suite | `pytest -n 8` (pytest-xdist, 8 worker processes) |
|-------|---------------------------------------------------|
| hw2-initial | 360 passed |
| hw2-round1 | 216 passed, **26 failed, 206 errors**, 10 xfailed |

The same 31 mutants of `pdf._join_split_numbers`: serial mutmut → 5 killed, 26
survived; parallel mutmut → 31 "killed". Mutant 25, run alone, survives (all 16
tests that execute the function pass).

## Cause

`backend/tests/conftest.py` (round 1), lines 38–40:

```python
_SCRATCH_VARIABLE = "RA_BACKEND_TESTS_SCRATCH"
SCRATCH = Path(os.environ.get(_SCRATCH_VARIABLE) or tempfile.mkdtemp(prefix="ra-backend-tests-"))
os.environ[_SCRATCH_VARIABLE] = str(SCRATCH)
```

To let the suite run twice in one Python process (feedback item 2.6), the scratch
folder's path is stored in an environment variable. Child processes inherit it, so
every xdist worker (and every mutmut child) uses the **same** temporary folder and
SQLite database, and the first worker to finish deletes the folder
(`pytest_sessionfinish`) while the others are still running.

## Consequences

- Running the tests in parallel (`pytest -n`) fails randomly.
- Parallel mutation testing reports spurious kills; mutation testing for every phase
  is therefore re-run serially (`--max-children 1`).
- An example of an improvement creating a new defect: the fix for one infrastructure
  problem (not re-entrant in one process) introduced another (not process-safe).
