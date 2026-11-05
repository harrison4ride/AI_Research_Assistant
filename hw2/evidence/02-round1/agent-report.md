# Round 1 subagent's final report (verbatim)

Agent: fresh-context Claude Code subagent (general-purpose), started 2026-11-04 with
the prompt in `prompt-sent.md` and the feedback in `feedback-round1.md`. It used 157
tool calls, about 667k tokens, and 85 minutes. These are its own claims; the
evaluation in this folder checks them.

---

## Round 1 test-suite improvements: report

All three suites pass under `make test` (exit 0). I changed only test code and test support files. No application code was modified, nothing was committed or branched, and `demo/` and `backend/data` were not touched. The e2e suite used port 8765 (checked free first); ports 8000 and 5173 were never used.

### Test counts

| Suite | Before | After (last `make test` run) |
|---|---|---|
| Backend (pytest) | 360 passed | 448 passed, 10 xfailed (all `strict=True`), 458 total |
| Frontend (Vitest) | 148 passed, 14 files | 184 passed, 5 expected failures (`it.fails`), 189 total, 16 files |
| E2E (Playwright) | 14 passed | 15 passed |

**Stability and strength checks:**
- **E2E:** `--repeat-each=4` passed 60/60. This includes the jump-to-section test that failed in 1 of 4 runs during your evaluation.
- **Frontend:** passed in 3 shuffled orders.
- **Backend:** passed with test files in reverse order, and now runs twice in one process.
- **Type check and lint:** `tsc -b` and `oxlint` are clean.
- **Expected failures:** each one was run unmarked to confirm it fails for the stated reason.
- **Mutation checks:** I applied 16 of the feedback's "a bug would still pass" mutations at runtime through a throwaway pytest plugin, never by editing app files. Each one is now caught by its strengthened test.

### Suspected application bugs (kept as expected failures)

**Backend (xfail, strict):**
1. **Real titles thrown away as placeholders.** A title in the PDF's properties that starts with Paper, Main, Document or arXiv is discarded. The placeholder pattern `JUNK_META_TITLE` in `app/services/pdf.py` has no end anchor. For example, "Paper Recommendation with Graph Neural Networks" is replaced by the layout guess. 4 cases, in `test_upload.py`.
2. **The 300-page cut is not disclosed.** A 302-page PDF yields `truncated: false`, and the model is told "Full text extracted from the PDF (302 pages)" although only 300 pages were read. In `test_summary.py`.
3. **Malformed PDF links cause 500 errors.** A link with port 99999 or a broken IPv6 literal makes `urlsplit` raise `ValueError`, which `ensure_full_text` does not catch. `/fulltext` and `/summary` answer 500 instead of recording the failure and using the abstract, which the `ensure_full_text` docstring promises. 2 cases, in `test_fulltext.py`.
4. **Wrong reason for `ftp://` links.** An `ftp://` link to a public host is refused as "points to a local or private address", which is false. In `test_fulltext.py`.
5. **Empty cut-off answers are saved.** An empty answer that stopped at the length limit is saved as just the cut-off note, with both providers, because the note is appended before the empty-answer check. In `test_llm_service.py`.

**Frontend (`it.fails`):**
6. **Endless re-rendering with a paper open.** `App` passes a new `onLibraryState` function on every render, and `PaperPage`'s effect depends on it. The test measured 145 renders in 200 ms after everything had loaded, and React logs "Maximum update depth exceeded". The original test finished before React reported it. In `App.test.tsx`.
7. **"Search OpenAlex instead" searches the wrong text.** It runs whatever is in the search box when clicked, not the query that failed. After an edit it sent "rag evaluation" instead of "rag"; the README says it runs the same query. In `SearchPage.test.tsx`.
8. **"Search OpenAlex instead" after an OpenAlex failure.** The button appears after a failed OpenAlex search once the source menu is switched to arXiv. In `SearchPage.test.tsx`.
9. **Library card links the external PDF.** When a paper has both a stored PDF and an open-access link, the card links the external one (`paper.pdf_url ?? localPdfHref`). PaperCard's prop comment says to link the stored copy when the library has one. In `LibraryPage.test.tsx`.
10. **Attach PDF disappears after a refused file.** The panel then shows only the error and a "Retry" link, which retries the download. In `FullTextStatus.test.tsx`.

Bugs 1, 3, 5 and 6 are clear-cut. Bugs 2, 4, 7, 8, 9 and 10 rest on my reading of the README or code comments, so please confirm the intended behavior.

### What changed, by feedback item

**2.1 Library, upload, app** — every listed test was strengthened:
- **Duplicates:** arXiv is saved without a DOI first; DOI case is checked in both directions; two papers from the same source get separate entries.
- **Filter:** a 200-character filter is accepted, 201 is rejected.
- **Edits:** a partial edit leaves every other field unchanged. Rejected edits leave the rejected field itself unchanged. The largest values the edit form allows are accepted (500-character title, years 1000 and 2100, 20,000-character abstract, 10,000 authors).
- **Deleting:** a second paper's conversation must survive a delete, and a prune.
- **Restart:** the test runs two app lifetimes and disposes the database engine between them.
- **Upload:** a 40,000-character PDF; the model must get a prefix of the text that excludes the last page.
- **Root page:** dev-mode wording is present and no-build wording absent. The no-build page is now tested too.
- **404/405 errors:** JSON bodies are checked in both dev and production mode. Production mode loads a fresh copy of `app/main.py` against a minimal build in a temp folder.
- **Defaults:** `Settings()` is built with the variables removed and checked against the INSTALL.md defaults table.
- **Logged-out hint:** must contain the documented command `` `claude auth login` ``.

**2.2 Search, full text, outline, PDF:**
- The inverted-index test uses repeated words.
- The redirect limit is the literal 6 requests, plus a 5-hop chain that succeeds.
- The redundant address test now checks that a host with one public and one private address is refused.
- Outline `top` values are compared with PyMuPDF's own text positions.
- Headings are parsed as JSON from the prompt, including a title with quotes.
- Heading search covers the out-of-order case. The redundant test now checks that a heading starting with the title beats a mention in the text.
- The page cap is tested through its constant, plus the disclosure test (bug 2).

**2.3 Summaries, Q&A, LLM service, CLI:**
- Strengthened every listed test as requested.
- Deleted the three redundant tests (`test_claude_code_errors_reach_the_user_unchanged`, `test_status_ready`, `test_summary_request_through_the_provider`).
- The hung CLI's PID must be gone after the timeout.
- The CLI lock-down flags are checked literally, and the system prompt must not be on argv.
- The fake CLI (`backend/tests/support/fake_claude.py`) no longer matches prompt sentences. It replies with what it received (last prompt line, title, end of the paper text, number of quoted turns). It reports `claude-fake-<alias>` for `--model`, records its PID, and has a chunk-delay setting.

**2.4 and 2.5 Frontend and e2e:** all listed items done.
- **Upload requests:** the upload and attach calls set no Content-Type header.
- **Cancellation:** the abort test uses a fetch stub that honors `init.signal`.
- **App tabs:** both saved and unsaved papers, and no tab marked while the paper loads.
- **Locale:** the result count is built with `toLocaleString()`.
- **Retry request:** the exact OpenAlex retry request is asserted.
- **Debounce:** fake timers. `frontend/src/test/timers.ts` bridges Vitest's clock to Testing Library, which otherwise hangs.
- **Retention and model:** retention text for 3 days and 1 day; the default model fallback with the default listed second.
- **Streaming:** the live answer text is checked mid-stream.
- **PaperCard:** `preventDefault` is checked, and the abstract toggle is checked through its label.
- **Upload box:** found by its role, and the sent file name is asserted.
- **E2E:** checks the server after removals and saves, finds the model menu by its label, and checks the reported model. It asserts exact authors and the full abstract, and checks the PDF through its text layer instead of react-pdf class names. Reloads happen only after answers are saved. The jump test uses a 5-page PDF and checks the heading position, the page counter and the visible highlight.

**2.6 Infrastructure:**
- **Frontend guards:** a request the mock didn't answer, or an unexpected `console.error`, now fails the test.
- **E2E reset:** `POST /__e2e__/reset` exists only in the test server (`e2e_server.py`). It deletes saved and opened papers, chats, PDFs and the search cache before each test.
- **Offline arXiv link:** the e2e server's arXiv link uses a documentation-only address, which the app refuses without connecting.
- **Backend fakes:** HTTP is faked once, at httpx's network layer, and the model once, at the provider dispatch.
- **State reset:** all module-level state is reset each test, and a new guard test (`test_isolation.py`) fails if the app adds state that isn't reset.
- **Shared settings:** settings isolation is shared with the e2e server.
- **Time:** arXiv spacing/cooldown and the search cache run on a fake clock, so the real 3-second spacing now runs in every test without slowing it.
- **Double run:** the suite can run twice in one process.

**Sections 3 and 4 (new tests):** almost every listed behavior is now tested.
- **Search:** spacing, cooldown bounds and resumption, cache expiry, size and key, largest valid values.
- **Database and pruning:** database upgrade and the NOT NULL error; pruning races, the 12-hour schedule, and shared PDFs.
- **Production and opening:** production-mode serving and the `backend/.env` warning; reopening and `/open` validation.
- **Saving:** a saved paper keeps its summary and section summaries.
- **Upload:** upload fallbacks, junk before the PDF header, and attach races and refusals.
- **Downloads:** SNI and per-hop address pinning; one download per paper at a time.
- **LLM paths:** the API provider end to end; refusal, empty and cut-off answers through the CLI.
- **Cancellation:** cancelling mid-answer over a real connection stops the CLI and saves nothing.
- **Frontend:** back navigation, config recheck on focus, error paths, error-boundary fallback, "Load more" stopping at page 100, chat behaviors, the section highlight rule, new `PdfViewer` unit tests, and an e2e test that zooming keeps the reading position.

### Not addressed, or only partly
- **Tab and section highlights in unit tests.** The app has no accessible marker (no `aria-current`), and jsdom cannot compute the stylesheet colors (I checked). So unit tests still read the `active` class, through one documented helper each. The e2e tests check the visible highlight.
- **"An older search answering last is dropped."** Not tested: the UI can't trigger it, because every way to start a search is disabled or hidden while one runs.
- **"Aborted when a new request starts."** Tested at the hook level (`useLlmStream`), because the UI disables a second start.
- **Coverage** was not re-measured. The coverage tools aren't installed in the project, and I installed nothing.

New support files are in `backend/tests/support/` (`isolation.py`, `clock.py`, `app_state.py`, `fake_anthropic.py`) and `frontend/src/test/` (`console.ts`, `timers.ts`). The new test files are `backend/tests/test_isolation.py`, `frontend/src/components/PdfViewer.test.tsx` and `frontend/src/useLlmStream.test.ts`.
