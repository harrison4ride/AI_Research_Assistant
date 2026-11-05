# P2: Evaluation of the initial suite (`hw2-initial`, commit 31076dc)

All measurements were taken on 2026-11-04 in a clean git worktree at the tag (no
`.env`, dependencies installed from the lock files), with the `claude` CLI replaced
by a stub that fails and logs. Raw data: `eval/metrics.json`, `eval/mutation.json`,
`eval/logs/`, `review/`, `code-review.md`, `bugs.md`.

## 1. What the agent generated

- **Prompt:** `prompt-sent.md`. **Agent:** a fresh-context Claude Code subagent; 181 tool
  calls, about 514k tokens, 52 minutes. Its report: `agent-report.md`.
- **Size:** 49 files, 7,872 added lines; application code unchanged.
- **Tests:** 522 in three layers.

| Layer | Framework | Tests | Files |
|-------|-----------|-------|-------|
| Backend unit/API | pytest (+ pytest-asyncio) | 360 (257 functions; parametrize expands the rest) | 11 test files + 7 support modules |
| Frontend unit/component | Vitest + React Testing Library + jsdom | 148 (140 test blocks) | 14 test files + 3 helpers |
| End-to-end | Playwright (Chromium) | 14 | 3 spec files + launcher |

- **Infrastructure the agent built unprompted:** a `conftest.py` that pins every setting
  and never reads `.env`, gives each test an empty temporary database, fakes all HTTP
  (failing any request no test registered) and DNS, and fakes both LLM providers
  (a fake model and a fake `claude` executable); an end-to-end launcher that runs the
  real app on its own port with fake search APIs and refuses to reuse a running server.
- **Self-check the agent ran unprompted:** it injected 21 bugs of its own into scratch
  copies and confirmed that each was caught.

## 2. Execution results (clean checkout)

| Suite | Passed | Failed | Time |
|-------|--------|--------|------|
| Backend (pytest) | 360 / 360 | 0 | 17.4 s |
| Frontend (Vitest) | 148 / 148 | 0 | 6.5 s |
| End-to-end (Playwright), run 1 | 13 / 14 | 1 | 31 s |
| End-to-end, runs 2–4 | 14 / 14 each | 0 | 16–20 s |

The end-to-end failure in run 1 ("summarize the sections and jump to one") was not a
regression: the same commit passed in the next three full runs and in 12 targeted
runs (CPU throttled ×1 and ×6). It is classified as a flaky test (see §4).

## 3. Code coverage

| Suite | Line | Branch | Notes |
|-------|------|--------|-------|
| Backend (coverage.py) | **94.4%** | **87.5%** | 1,850 statements |
| Frontend (V8) | **81.2%** | **78.5%** | functions 90%+ except the PDF viewer |

Lowest-covered files: `PdfViewer.tsx` 0% (only exercised by the end-to-end tests;
mocked in all unit tests), `main.py` 77% (production-mode static serving),
`http.py` 67%, `db.py` 87% (database upgrade path), `ErrorBoundary.tsx` 67%.

Important behavior that no test exercises (from coverage and the five reviews):
- **Database upgrade** for an older library (`init_db` adding columns, back-filling
  `in_library`): untested, and needed for "saved papers survive a restart" (F2).
- **arXiv politeness rules:** the 3-second spacing is switched off in every test;
  cooldown limits (60–600 s) and expiry are untested.
- **Search cache:** expiry, size limit, and `per_page` in the key are untested.
- **Full-text download safety:** a host with one private address among several, TLS
  server name with a pinned IP, per-redirect pinning, and malformed links are untested.
- **Concurrency:** one download per paper, deletion during a download or during
  section summaries, cancellation of a streamed answer.
- **Frontend:** back navigation, out-of-order responses, the PDF viewer (zoom,
  "Open PDF", load failure), and stream cancellation.
- **Production mode** (`/`, `/assets`, JSON 404/405 for `/api`) is never loaded by a
  backend test.

## 4. Test correctness

Every test was classified by one of five independent fresh-context reviewers against
the intended behavior (rubric: `tools/review-rubric.md`; reports in `review/`). The
reviewers checked each non-OK call by injecting the matching bug in memory.

| Layer | Tests | OK | WEAK | BRITTLE | REDUNDANT | FLAKY | WRONG |
|-------|-------|----|------|---------|-----------|-------|-------|
| Backend | 257 | 225 (87.5%) | 23 | 4 | 5 | 0 | 0 |
| Frontend unit | 140 | 122 (87.1%) | 11 | 4 | 0 | 2 | 1 |
| End-to-end | 14 | 7 (50%) | 6 | 0 | 0 | 1 | 0 |
| **Total** | **411** | **354 (86.1%)** | **40** | **8** | **5** | **3** | **1** |

Representative problems:
- **Vacuous assertions (WEAK):** `test_upload_asks_the_llm_with_the_text_of_the_first_pages`
  asserts `len(first_pages) <= 15000` on a sample whose whole text is 1,317
  characters, so it cannot fail; `test_deleting_a_paper_deletes_its_conversation`
  counts all chat rows in a database that has only one paper's chat, so a delete that
  wiped every conversation passes.
- **Self-referential expectations (WEAK):** `test_redirect_loops_give_up` expects
  `MAX_REDIRECTS + 1` requests from the code's own constant, so raising the limit to 20
  passes although README promises "at most 5"; the Claude Code lock-down test compares
  the command line with the app's own `LOCKDOWN_ARGS`, so removing `--safe-mode`
  passes all 360 backend tests.
- **Wrong (passes for the wrong reason):** "falls back to the default model when the
  remembered one is gone" can never fail, because the default model is also the first
  menu option; `/code-review` found a second case (a 101-character model name is
  rejected by the unknown-model check, not by the length validation the test targets).
- **Flaky:** a result-count test hard-codes "1,234" although the app uses
  `toLocaleString()` (it fails under a German locale); a debounce test depends on real
  timers; one end-to-end test reloads before the answer is saved; and the end-to-end
  reset helper deletes only saved papers, so unsaved papers leak between tests.
- **Brittle:** exact prompt wording and exact `<paper>` block layout; CSS class names
  (`clamped`, `level-2`, `active`, `dragging`).

`/code-review` on the test code (`code-review.md`) independently found 10 issues;
7 overlap with the reviewers' findings, and 3 are about test-infrastructure robustness
(per-module patching, partial state reset, duplicated isolation code).

## 5. Stability and isolation

| Check | Result |
|-------|--------|
| 5 shuffled runs per unit suite | 0 tests changed outcome |
| Backend with network disabled (pytest-socket) | 0 tests failed |
| Calls to the `claude` CLI stub | 0 |
| Wrote to the default data directory | no (the user's real data was byte-identical after generation) |
| End-to-end | 1 failure in 4 full runs (flaky) |
| Re-running pytest twice in one process | fails: `conftest.py` deletes its temp folder at session end while `app.db` stays cached (found when mutmut, which does this, could not start; worked around in the harness) |

## 6. Fault-detection capability

**Existing bugs in the application.** No test fails on the unmodified app, so the
initial suite **detected no bugs**. The review then found **8 real application bugs**
that the suite misses (`bugs.md`), each confirmed by reproduction or code reading:

| Bug | Severity | Summary |
|-----|----------|---------|
| BUG-1 | medium | An empty answer cut off at the length limit is saved as only the cut-off note, overwriting the previous summary |
| BUG-3 | medium | A malformed PDF link (bad port, broken IPv6) makes full text, outline, and summary fail with 500 for that paper, permanently |
| BUG-6 | medium | The reader re-renders continuously while a paper is open (2,661–3,109 React commits per second) |
| BUG-2 | low | An `ftp://` PDF link is reported as "a local or private address" |
| BUG-4 | low | Text beyond page 300 is dropped without being reported as cut off |
| BUG-5 | low | Real titles starting with "Main", "Paper", "Document", or "arXiv" are discarded as placeholders |
| BUG-7 | low | After a refused PDF attachment, the "Attach PDF" button disappears |
| BUG-8 | low | "Search OpenAlex instead" appears for any error and searches the current input |

**Held-out seeded faults:** detected **17 of 18** (backend 12/12, frontend 5/6,
HW1-history faults 7/8). Missed: F02 (validation-error messages from FastAPI's 422
arrays lost when there is only one error). The margin is thin: 8 of the 17 were caught
by exactly one test.

**Mutation testing (mutmut, 9 backend modules listed, of which 8 yield mutants, 2,787 mutants):** **76.1%** killed
(2,120); 661 survived; 6 timed out. (The serial re-run, used for all phases, gave exactly the same 661 survivors.) By module: openalex 93.8%, arxiv 83.8%, cache 81.0%, assistant
80.1%, papers 78.3%, llm 76.3%, fulltext 73.4%, pdf 67.2%. Survivors cluster in section
outline extraction (`pdf._outline_from_headings` 73, `_bookmark_top` 32, `_page_lines`
28, `_join_split_numbers` 26, `locate_headings` 26), section-summary parsing
(`llm.summarize_sections` 47), the Claude Code stream handler (28), PDF download (27),
and the private-address check `_check_public` (17).

## 7. Summary

The initial suite is large, well isolated, and runs from a clean checkout. Its line
coverage (94% backend) and seeded-fault score (17/18) are high, but the deeper checks
show the gap between "executes the code" and "checks the behavior": 14% of tests are
weak, brittle, redundant, flaky, or wrong; a quarter of backend mutants survive; and
the suite misses 8 real bugs, including three of medium severity. These findings are
the input to the improvement rounds:

- **Round 1 (requirements + review + coverage):** fix the 57 non-OK tests and cover the
  untested requirement-level behavior listed in §3.
- **Round 2 (execution feedback):** mutation survivors, the flaky and order-dependent
  tests, and the bug reports, each needing a regression test.
