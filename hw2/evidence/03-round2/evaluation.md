# Evaluation of round 2 (`hw2-round2`, commit 379d0cb): the final suite

Same method as for the earlier phases: a clean git worktree at the tag, dependencies
from the lock files, the `claude` CLI replaced by a failing stub. Raw data:
`eval/metrics.json`, `eval/summary.md`, `eval/mutation.json` (serial run), `eval/logs/`.
Reviews and checks: `review/G1-G5`, `code-review-raw.md`, `verification.md`,
`equivalence-sample.md`.

## What the agent changed

Prompt: `prompt-sent.md`; feedback: `feedback-round2.md` (with the 619 surviving mutants in
`mutation-survivors.md`); report: `agent-report.md`; interruption: `run-notes.md`.
Fresh-context subagent, 187 tool calls, about 907k tokens, 66 minutes, one network
interruption after about 20 minutes (resumed in the same context). 28 test files changed
or added (1,491 lines added, 215 removed). Application code unchanged (`git diff
hw2-round1 hw2-round2` lists only test files and `frontend/vitest.config.ts`). No new
dependencies.

## Results

| Measure | Initial | Round 1 | Round 2 |
|---------|---------|---------|---------|
| Backend tests | 360 passed | 448 passed + 10 strict xfail (458) | 553 passed + 5 strict xfail (558) |
| Frontend tests | 148 passed | 189, of which 5 are `it.fails` | 190, of which 4 are expected failures |
| End-to-end tests | 14; 3 of 4 full runs passed | 15; 4 of 4 full runs passed | 15; 4 of 4 full runs passed |
| Backend line / branch coverage | 94.4% / 87.5% | 97.0% / 91.7% | 98.6% / 95.7% |
| Frontend line / branch coverage | 81.2% / 78.5% | 94.6% / 86.1% | 94.8% / 86.1% |
| Unit tests changing outcome in 5 shuffled runs | 0 | 0 | 0 |
| Backend tests failing without network | 0 | 0 | 0 |
| Backend with 8 parallel workers (`pytest -n 8`) | 360 passed | 26 failed, 206 errors | 553 passed + 5 xfail (same as serial) |
| Held-out faults detected | 17/18 | 17/18 | 17/18 (F02 still missed) |
| Faults caught by only one test | 8 | 7 | 6 |
| Mutation score (serial) | 76.1% | 77.6% | 89.4% (2,492 killed, 289 survived, 6 timeouts) |
| Backend assertions per test | 2.39 | 2.69 | 2.59 |
| Frontend `expect()` per test | 2.29 | 2.55 | 2.59 |
| Confirmed application bugs the suite flags | 0 of 8 | 8 of 8 | 8 of 8 |

No known-bug test (backend `@known_bug`, frontend `itFailsUntilFixed`) appears among the
detectors of any held-out fault, so the expected failures cause no false detections.

## Claims of the agent's report, checked

| Claim | Check | Result |
|-------|-------|--------|
| 553 + 5 xfail, 186 + 4 expected failures, e2e 15/15 in 4 of 4 runs | clean-checkout run | confirmed |
| `pytest -n 8` gives the serial result | clean-checkout run | confirmed |
| one expected failure per confirmed bug | read the 5 `@known_bug` and 4 `itFailsUntilFixed` tests | confirmed (bugs 1-5 backend; 6, 7, 8 and 10 frontend, in the numbering of `feedback-round2.md`) |
| bug 9 is a normal test of both cases | read the diff of `LibraryPage.test.tsx` and `PaperCard.test.tsx` | confirmed |
| each expected failure flips when its bug is fixed | experiments V2 and V5 (`verification.md`) fixed bugs 3 and 2 in a scratch copy | true only for the exact fix: fixing one of bug 3's two links, or fixing bug 2 with a message without the word "http", leaves the test in XFAIL |
| an unrelated breakage fails the bug tests normally | experiment V1 | false for the empty-answer test: an unrelated `LlmError` counts as the bug, even when the bug is fixed |
| mutation 77.6% → 89.5% (2,493 killed, 5 timeouts) | serial mutmut run, timeouts rerun on an idle machine | 89.4%: one mutant (`fulltext._download` 59, which corrupts multi-chunk downloads) hangs a test in this harness instead of failing it |
| 331 of the 619 survivors killed; the rest are 232 equivalent, 56 untested on purpose, and 1 lost kill (`_check_public` 10) | set comparison of the survivor lists | exact: the 289 survivors are those 232 + 56 + 1, and `_check_public` 10 is the only new survivor |
| 232 survivors are equivalent | random sample of 20 (`equivalence-sample.md`) | 14 equivalent, 5 change only the prompt's wording (defensible to leave), 1 not equivalent (`_page_lines` mutant 21, shown by experiment V7) |

## Correctness review of the final suite

Same five reviewer prompts as for the initial suite (`review/prompts/`; the changes are the
new test files and helpers in each group, plus one sentence on how to judge expected
failures), each to a fresh-context subagent.

| Group | Initial: tests | OK | Final: tests | OK |
|-------|----------------|----|--------------|----|
| G1 backend library, upload, app (+ isolation) | 78 | 65 (83.3%) | 108 | 96 (88.9%) |
| G2 backend search, full text, outline, PDF | 81 | 73 (90.1%) | 140 | 129 (92.1%) |
| G3 backend summaries, chat, LLM, Claude Code | 98 | 87 (88.8%) | 113 | 104 (92.0%) |
| G4 frontend API, router, app, pages (+ useLlmStream) | 70 | 61 (87.1%) | 86 | 75 (87.2%); 74 after the BUG-9 decision |
| G5 frontend components (+ PdfViewer) | 70 | 61 (87.1%) | 84 | 80 (95.2%) |
| G5 end-to-end | 14 | 7 (50.0%) | 15 | 14 (93.3%) |
| **Total** | **411** | **354 (86.1%)** | **546** | **498 (91.2%) as rated; 497 (91.0%) after the BUG-9 decision** |

| Rating | Initial | Final | Final, on tests last changed in round 2 |
|--------|---------|-------|----------------------------------------|
| WEAK | 40 | 24 | 4 |
| BRITTLE | 8 | 12 | 6 |
| REDUNDANT | 5 | 9 | 1 |
| FLAKY | 3 | 1 | 0 |
| WRONG | 1 | 3 (2 as rated) | 3 |

"Last changed" comes from `git blame` over each test's lines at `hw2-round2`: of the 540
tests the trace found, 294 were last changed in the initial suite, 142 in round 1, and 104
in round 2, with 22, 13, and 14 non-OK ratings (7.5%, 9.2%, 13.5%), counting the
LibraryPage link test as WRONG. Round 2's 14 are mostly BRITTLE or WRONG (9 of 14).

Notes:
- The two WRONG ratings: the stuttering arXiv message (a new app bug, also found by the
  code review) and the library card's link preference in `PaperCard.test.tsx`. The second
  contradicted the owner decision in `feedback-round2.md`, and G4 rated the equivalent
  `LibraryPage.test.tsx` test OK, so the reviewers disagreed. After the final review the
  owner reversed the decision: the link preference is a bug (BUG-9). Both link tests
  therefore assert a defect, and the corrected totals are 497 OK (91.0%) and 3 WRONG.
- Every reviewer rated the 9 expected-failure tests OK except G3, which rated the 300-page
  one BRITTLE (it needs the words "cut off"). The code review and experiments V1, V2, and V5
  found problems in three of the ones rated OK, so 4 of the 5 backend expected failures can
  hide a correct fix.
- G3's load test (16 busy processes, 21:43 to 21:54) overlapped the mutation run. Rerunning
  the 6 timed-out mutants on an idle machine gave the same result (`eval/mutation.json`,
  `timeouts_rerun`).

## Problems in round 2's own changes

`/code-review high` on `hw2-round1..hw2-round2` reported 10 findings, all in lines round 2
wrote (`git blame`). The experiments in `verification.md` confirmed every one that needed
an experiment.

| # | Finding | Kind | Evidence |
|---|---------|------|----------|
| 1 | `test_arxiv_rejection_without_a_reason_is_reported` asserts the stuttering message "arXiv rejected the query: arXiv rejected the query." | Wrong expectation: pins an app defect (new bug) | `arxiv.py:94` + `arxiv.py:161`; reviewer G2 found it independently |
| 2 | The empty-answer known-bug test counts any `LlmError` as the bug | Expected failure can pass for the wrong reason | V1 |
| 3 | Merged cases in one expected failure hide a partial fix (bug 3's two links; also the 4 titles and 2 providers) | Expected failure too coarse | V2; the agent reported this trade-off itself ("one kill was lost") |
| 4 | The download time-limit test passes without `timeout=60.0` (the client's 20 s default is also a number), and httpx limits each read, not the download | Weak | V3 |
| 5 | The library card's link preference is pinned as correct | Asserts a bug (BUG-9; the owner reversed the decision after this review) | reviewer G5 rated the same test WRONG |
| 6 | The late-request check in `fetchMock.ts` almost never runs | Infrastructure fix that does not work | V4 |
| 7 | The ftp known-bug test requires the word "http" in the fixed message | Expected failure tied to one wording | V5 |
| 8 | The concurrent-save test's `in_library` check cannot detect a missing promotion | Weak | V6 (with a correction: it does catch a wrong promotion on open) |
| 9 | The page-text test builds its expected value with the app's own PyMuPDF calls | Self-referential (brittle) | V8 |
| 10 | Size-limit padding logic duplicated in two files | Maintenance | reading |

## New possible application bugs found in the final evaluation

None of these is detected by any version of the suite. The app stays frozen; whether to
fix them after the experiment is the owner's decision.

| # | Possible bug | Found by | Confirmed by |
|---|--------------|----------|--------------|
| 1 | An arXiv rejection without a reason shows "arXiv rejected the query: arXiv rejected the query."; the round 2 suite asserts it | code review #1, G2 | reading `arxiv.py:94` and `:161`; the passing test |
| 2 | Authors with lowercase particles are dropped: `_split_names("Laurens van der Maaten, Geoffrey Hinton")` gives `["Geoffrey Hinton"]` | G2 | ran it in a frozen checkout |
| 3 | arXiv `Retry-After` as an HTTP date is ignored (60 s pause), though README promises the longer pause it asks for | G2 | reading `arxiv.py:122` (digits only) |
| 4 | After "Save to library" in the reader, Details shows the first-opened time as "Saved" until reload | G4 | reading `PaperPage.tsx:98` (copies only `in_library`) and `:233-234` |
| 5 | After a failed "Clear conversation", the error stays on screen | G5 | reading `ChatPanel.tsx` (`setLoadError` only ever sets an error) |
| 6 | Placeholder authors in the PDF properties ("Microsoft Office User", "Administrator") replace the real authors | G2 | reviewer's probe |
| 7 | Malformed OpenAlex JSON (`[]`, `null`, `results: [null]`) gives HTTP 500 instead of 502 | G2 | reviewer's probe |
| 8 | Databases created at milestone M2 reuse deleted paper ids after the upgrade | G1 | reviewer's script |
| 9 | IPv6-literal PDF links send a `Host` header without brackets | G2 | reviewer's probe |
| 10 | The edit form can send a stored abstract or title longer than the backend accepts, so even a title-only edit fails | G1 | reviewer's reading |

New paths to known bugs: bugs 2 and 3 (ftp link, malformed link) are also reachable
through a redirect (G2, probe); "Search OpenAlex instead" also appears after a failed
"Read" (G4); the "Retry" button after a refused attachment retries the download (G5).
Robustness, not a documented requirement: a host that sends one byte every 19 s keeps a
download, and the paper's lock, going indefinitely (V3).

## Takeaways

- Mutation feedback was the only feedback that moved the mutation score (77.6% to 89.4%).
  The agent's accounting of the remaining survivors is exact, but its equivalence calls
  are not always right (1 of 20 sampled is not equivalent).
- Tests written to kill mutants pin current behavior: one asserts a defect, and tests last
  changed in round 2 carry 6 of the 12 BRITTLE and both WRONG ratings.
- My rule of exactly one expected failure per bug made the bug checks coarser: in 4 of the
  5 backend ones, a correct fix can stay hidden or an unrelated error counts as the bug.
- Coverage is at its ceiling (98.6% of backend lines) and the held-out fault score did not
  move in any phase (17/18). The missed fault, F02, is in an area no feedback targeted.
- Fresh reviewers keep finding real bugs: 10 new possible bugs, none detected by any
  version of the suite.
- The evaluator's own feedback produced one brittle test (the 15,000-character bound), and
  a reviewer's load test overlapped the mutation run. Cross-checking caught both.
