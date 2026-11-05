# Feedback on the test suite: round 2 (execution results and owner decisions)

Round 1's suite (now committed) was run in a clean checkout and measured: all suites
pass (backend 448 + 10 strict xfail, frontend 189, end-to-end 15/15 in 4 of 4 runs),
5 shuffled runs changed no outcome, and no backend test needs the network. This round's
feedback comes from **executing** the suite: the owner's answers about the suspected
application bugs, a code review of round 1's changes (with its claims checked by
running the tests), and mutation testing of the backend.

## 1. Owner decisions on the suspected application bugs

Each `xfail`/`it.fails` test was run unmarked; every one fails at the point its reason
names. Decisions:

| Round-1 item | Decision |
|--------------|----------|
| 1. Real titles discarded as placeholders (`JUNK_META_TITLE`) | **Confirmed bug.** Keep the strict xfail tests. |
| 2. The 300-page cut is not disclosed | **Confirmed bug.** Keep. |
| 3. Malformed PDF links cause 500 errors | **Confirmed bug.** Keep. |
| 4. `ftp://` links refused for a false reason | **Confirmed bug.** Keep. |
| 5. Empty cut-off answers are saved | **Confirmed bug.** Keep. |
| 6. Endless re-rendering with a paper open | **Confirmed bug.** Keep, but see 2.2: the `it.fails` marker must fail only for this reason. |
| 7. "Search OpenAlex instead" runs the edited text | **Confirmed bug.** Keep. |
| 8. "Search OpenAlex instead" after an OpenAlex failure | **Confirmed bug.** Keep. |
| 9. Library card links the open-access PDF, not the stored copy | **Not a bug: intended.** The card's "PDF ↗" mirrors the search results and links the open-access PDF when the paper has one; the stored copy is used when there is no `pdf_url` (uploads). The reader's "Open PDF" button already opens the stored copy. Turn this into a normal test of that behavior (both cases), replacing the `it.fails` test and the PaperCard test that round 1 deleted. |
| 10. Attach PDF disappears after a refused file | **Confirmed bug.** Keep. |

Every confirmed bug must keep exactly one clear failing check, so the suite tells the
owner when the bug is fixed.

## 2. Code review of round 1's changes

Round 1's diff was reviewed and each claim below was checked by running the tests.

### 2.1 Regressions: behavior that round 1 stopped testing

Removing brittle checks is right, but each one must be replaced by an equivalent check
of the **behavior**, not deleted:

- `frontend/src/components/PaperCard.test.tsx` "toggles the full abstract" now checks
  only the button label. An abstract that never expands passes. Check that the full
  abstract is shown after the toggle and clamped again after "Show less" (for example
  through an accessible attribute or the element's computed state), not only the label.
- `frontend/src/components/UploadBox.test.tsx`: the drag-over highlight and its reset
  after a drop are no longer tested at all.
- `frontend/src/components/SectionsPanel.test.tsx`: nothing tests that subsections are
  indented (shown as children of their section) any more.
- `backend/tests/test_upload.py` (first-pages metadata test): the 15,000-character bound
  is gone; it only checks that the last line is missing, so sending 39,000 characters
  passes. README: only the **first pages** go to the model. Assert the bound (and that
  what is sent is a prefix of the text).

### 2.2 Expected failures that can pass for the wrong reason

`frontend/src/test/setup.ts`: the new `afterEach` throws on any `console.error` or
unmocked request, and Vitest applies the `it.fails` inversion **after** `afterEach`. So
an unrelated console error or unmocked request counts as the "expected failure" of all
5 `it.fails` tests, and fixing a bug might never be noticed. Make each expected failure
fail only on the assertion about its bug (e.g. exclude `it.fails` tests from the
`afterEach` guard, or assert the specific symptom inside the test).

### 2.3 Weak or timing-dependent checks

- `frontend/e2e/upload-summary-chat.spec.ts:145` (zoom keeps the reading position): the
  poll `toBeGreaterThan(before - 25)` passes immediately on the old layout. Wait for the
  new zoom level (e.g. its label) before checking position and page counter.
- `frontend/src/test/fetchMock.ts`: `unanswered` is module-level and drained only in
  `afterEach`, so a late request is blamed on the next test; it duplicates `unhandled`.
- `backend/tests/test_library.py` `older_database` fixture: swaps only `db.engine` and
  `db.SessionLocal`, but `routers/assistant.py` and `services/cache.py` import
  `SessionLocal` by name, so startup pruning and summary/chat saves still use the shared
  test database. The upgrade test therefore never checks pruning on the upgraded
  database.
- `backend/tests/test_summary.py:211` (private-address case of "after a failed download
  the abstract is used"): `downloads == 0` cannot detect repeated attempts, because the
  address check never sends a request. Detect a repeated attempt another way (e.g. count
  address checks).

### 2.4 The backend suite is no longer safe to run in parallel

Running the backend suite with 8 worker processes (`uv run --with pytest-xdist pytest -n 8`)
gives **216 passed, 26 failed, 206 errors** for the current suite; the previous suite
passed all 360 tests this way. Errors are mostly SQLite and missing-folder errors.

Cause, found by running it: `backend/tests/conftest.py` stores the scratch folder's path in
the environment variable `RA_BACKEND_TESTS_SCRATCH` (so that a second session in the same
process reuses it). Child processes inherit environment variables, so every worker process
uses the same scratch folder and SQLite database, and the first worker to finish deletes the
folder in `pytest_sessionfinish` while the others are still running.

Required: each test process (each xdist worker, each forked child) must get its own scratch
folder and database, while the suite still runs twice in one process. `pytest -n 8` must pass
with the same results as a serial run.

## 3. Mutation testing (backend)

mutmut mutated 9 backend modules (2,787 small code changes, called mutants) and ran the tests
that execute each changed function, one mutant at a time. A mutant that no test notices
"survives". Result for the current suite: **77.6% killed** (2163 killed, 619 survived, 5 timed out).

| Module | Killed | Surviving mutants |
|--------|--------|-------------------|
| routers.assistant | 84.9% | 22 |
| routers.papers | 81.4% | 47 |
| services.arxiv | 87.2% | 48 |
| services.cache | 83.3% | 7 |
| services.fulltext | 78.2% | 55 |
| services.llm | 75.5% | 165 |
| services.openalex | 93.8% | 12 |
| services.pdf | 68.4% | 263 |

Functions with the most surviving mutants:

| Function | Surviving mutants |
|----------|-------------------|
| `services.pdf._outline_from_headings` | 72 |
| `services.llm.summarize_sections` | 47 |
| `services.pdf._bookmark_top` | 32 |
| `services.llm._stream_claude_code` | 26 |
| `services.pdf._join_split_numbers` | 26 |
| `services.pdf._page_lines` | 26 |
| `services.arxiv.parse_entry` | 23 |
| `services.fulltext._download` | 23 |
| `services.pdf.extract` | 23 |
| `services.llm.build_context` | 21 |
| `services.llm._extract_claude_code` | 20 |
| `services.pdf.locate_headings` | 19 |
| `routers.papers.ensure_outline` | 18 |
| `services.llm._stream_api` | 18 |
| `services.pdf._guess_title` | 18 |
| `services.fulltext._check_public` | 16 |
| `services.llm._extract_api` | 14 |
| `routers.assistant._ndjson_response` | 12 |
| `routers.papers._get_or_create` | 9 |
| `services.pdf._guess_authors` | 9 |
| `services.arxiv._query` | 8 |
| `services.pdf._guess_year` | 8 |
| `services.pdf._horizontal_lines` | 8 |
| `services.pdf.extract_outline` | 8 |
| `services.arxiv.search` | 7 |

All 619 surviving mutants, each as a diff, are in
`/private/tmp/claude-501/-Users-hongxiangzhang-Documents-593-demo/a3b69e76-b3cf-4951-98bc-3c2b2be9df6d/scratchpad/round2-input/mutation-survivors.md`.

How to use this:
- Prioritize mutants in behavior a user or caller relies on (search results, saved papers,
  extracted metadata, what the model is sent, error messages shown to users, section positions).
- A surviving mutant is a question: "which observable behavior should have changed?" Answer it
  with an assertion on that behavior, not with a test that pins the mutated line.
- Some mutants cannot change anything observable, for example a changed log message or an
  equivalent rewrite. Do not test those; list them as equivalent with the reason.
- Some survivors come from round 1 replacing exact-match checks (for example of the prompt's
  `<paper>` block) with piecewise checks. Do not go back to brittle exact matches; check the
  parts that matter to the model instead.
