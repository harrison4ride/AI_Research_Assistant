# Evaluation of round 1 (`hw2-round1`, commit 043c901)

Same method as for the initial suite: a clean git worktree at the tag, dependencies
from the lock files, the `claude` CLI replaced by a failing stub. Raw data:
`eval/metrics.json`, `eval/mutation.json` (serial run), `eval/logs/`,
`code-review.md`, `parallel-regression.md`.

## What the agent changed

Prompt: `prompt-sent.md`; feedback: `feedback-round1.md`; report: `agent-report.md`.
Fresh-context subagent, 157 tool calls, about 667k tokens, 85 minutes. 43 test files
changed (2,872 lines added, 531 removed). Application code unchanged (verified with
`git diff`). No new dependencies.

## Results

| Measure | Initial | Round 1 |
|---------|---------|---------|
| Backend tests | 360 passed | 448 passed + 10 strict xfail (458) |
| Frontend tests | 148 passed | 189 passed, of which 5 are `it.fails` |
| End-to-end tests | 14; 3 of 4 full runs passed | 15; 4 of 4 full runs passed |
| Backend line / branch coverage | 94.4% / 87.5% | 97.0% / 91.7% |
| Frontend line / branch coverage | 81.2% / 78.5% | 94.6% / 86.1% |
| Unit tests changing outcome in 5 shuffled runs | 0 | 0 |
| Backend tests failing without network | 0 | 0 |
| Backend with 8 parallel workers (`pytest -n 8`) | 360 passed | **26 failed, 206 errors** |
| Held-out faults detected | 17/18 | 17/18 (F02 still missed) |
| Faults caught by only one test | 8 | 7 (first reported as 6; see `../final/faults-rerun.md`) |
| Mutation score (serial) | 76.1% (identical to its parallel run) | 77.6% |
| Backend assertions per test | 2.39 | 2.69 |
| Frontend `expect()` per test | 2.29 | 2.55 |
| Application bugs the suite flags | 0 of 8 | **8 of 8** (as expected failures) + BUG-9 (first judged a false positive; see below) |

## Bugs detected

All eight bugs from the initial review (`../01-initial/bugs.md`) now have a failing
check, marked as an expected failure so the suite stays green. The feedback stated
the intended behavior for each but never said that the app violated it, so the agent
found the bugs by writing requirement-based tests. It also flagged the library card's
link preference, which the owner first declared intended (round 2's feedback). After the
final review the owner reversed that decision: it is a bug (BUG-9), so round 1 flagged
all nine known bugs and had no false positive.

## Correctness problems introduced by round 1

From `/code-review` on `hw2-initial..hw2-round1` (`code-review.md`) and the parallel run
(`parallel-regression.md`):

1. **Regressions from deleting brittle checks:** whether the abstract expands, the
   drag-over highlight, and subsection indentation are no longer tested; the
   upload metadata test lost its 15,000-character bound.
2. **Expected failures that can pass for the wrong reason:** the new `afterEach`
   guard (fails on `console.error`/unmocked requests) runs before Vitest's `it.fails`
   inversion.
3. **A design choice marked as a bug** (`LibraryPage.test.tsx`), and the test that
   pinned the intended behavior was deleted.
4. **Not process-safe:** the scratch folder's path is stored in an inherited
   environment variable, so parallel processes share one database.
5. Smaller issues: a zoom check that passes before the zoom happens; a fixture whose
   database swap misses modules that imported `SessionLocal` by name; a "no repeated
   download" check that cannot see repeated attempts.

## A measurement problem found and corrected

The first mutation run of round 1 (parallel, 8 children) reported **99.0%**. It was
wrong: `pdf.py` still had 19 unexecuted lines yet "100%" of its mutants were killed.
Running one such mutant alone showed it survives. The cause was problem 4 above:
parallel mutmut children shared the suite's database and failed for unrelated reasons.
Mutation testing is therefore run serially for every phase (`--max-children 1`). The
invalid parallel results are kept in `eval/mutation-parallel-invalid/`.

## Takeaways

- Requirement-based review feedback raised coverage and, above all, bug detection
  (0 → 8 of 8), but barely moved the mutation score (76.1% → 77.6%). Mutation testing
  measures something the review feedback did not target.
- Replacing brittle exact-match checks with piecewise checks made some mutants survive
  (for example 9 → 21 survivors in `llm.build_context`): mutation testing rewards
  exact matching, even where it makes tests brittle.
- Fixes created new defects (four regressions, the parallel-safety bug), which only a
  second review and an execution check found.
