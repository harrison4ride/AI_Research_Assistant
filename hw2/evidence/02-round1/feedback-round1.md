# Feedback on the test suite: round 1 (requirements, review, coverage)

The suite (backend/tests, frontend/src/**/*.test.ts(x), frontend/e2e) passes and is
well isolated. It was evaluated in a clean checkout, and every test was reviewed by
reading it against the app's intended behavior. This document lists what the review
and the coverage report found.

## 1. How the tests are judged

The source of truth is the app's **intended** behavior, never its current output:

1. Requirements F1–F5 and their acceptance criteria: `docs/REQUIREMENTS.md`
2. Behavior documented for users: `README.md`, `INSTALL.md`, UI text
3. Intent stated in code comments and docstrings in `backend/app` and `frontend/src`

A passing test is not necessarily a correct one. Categories used below:

- **WEAK**: checks the right behavior, but a plausible bug would still pass.
- **WRONG**: the inputs make the check meaningless, or it passes for the wrong reason.
- **BRITTLE**: checks an implementation detail no requirement needs.
- **REDUNDANT**: adds no detection power over another test.
- **FLAKY**: depends on locale, timers, test order, or timing.

## 2. Problems in existing tests

### 2.1 Backend: library, upload, app (`test_library.py`, `test_upload.py`, `test_app.py`)

| Test | Category | Problem | What it should check |
|------|----------|---------|----------------------|
| test_library.py::test_same_paper_from_arxiv_and_openalex_is_saved_once | WEAK | The arXiv fixture already carries the arXiv DOI, so the plain DOI match dedupes it; the arXiv-id-vs-arXiv-DOI branch (papers.py `find_duplicate`) is never needed and can be deleted with all tests passing. | Save an arXiv result **without** a DOI first (what `arxiv.parse_entry` gives when the feed has no `<arxiv:doi>`), then the OpenAlex copy: 200, same id, one entry. |
| test_library.py::test_doi_match_ignores_case | WEAK | Only stores upper case and sends lower case, which exercises only the SQL-side lower-casing; dropping `.lower()` on the incoming DOI passes. | Both directions (store lower/post upper and the reverse). |
| test_library.py::test_different_papers_get_separate_entries | WEAK | Checks only a length; the two papers differ in source, id, and DOI at once, so matching on "source OR id" still gives 2. | Two different papers from the **same** source; distinct ids; both titles listed. |
| test_library.py::test_filter_longer_than_200_characters_is_rejected | WEAK | Only the rejecting side; a tighter cap than the UI's `maxLength={200}` would pass. | Also a 200-character filter is accepted. |
| test_library.py::test_partial_edit_leaves_other_fields_alone | WEAK | Checks title and authors only; a PATCH that clears unsent fields (e.g. abstract) passes. | Every other field (abstract, url, venue, doi, year) unchanged. |
| test_library.py::test_invalid_edits_are_rejected | WEAK | Only rejecting cases; nothing checks the edge values the edit form allows are accepted (title 500 chars, years 1000 and 2100, abstract 20,000 chars, thousands of authors). For the year/abstract cases it re-checks the title instead of the rejected field. | Add the accepting edge cases; assert the rejected field itself is unchanged. |
| test_library.py::test_deleting_a_paper_deletes_its_conversation | WEAK | Counts all chat rows while only one paper has chat; a delete that wipes every paper's conversation passes. The prune test's chat check has the same blind spot. | Give a second paper a conversation and assert it survives. |
| test_library.py::test_library_survives_a_restart | WEAK | Reuses the same engine and SQLite connections and exits the fixture's client twice; it never restarts anything that holds data. | Dispose the engine (or otherwise reopen the database file) between the two app lifetimes. |
| test_upload.py::test_upload_asks_the_llm_with_the_text_of_the_first_pages | WEAK | `len(first_pages) <= 15000` cannot fail: the sample's whole text is about 1,300 characters. Sending the whole paper passes, although README says only the first pages go to the model. | Upload a PDF longer than ~15,000 characters with a marker on its last page; assert the marker is not sent and the request is a prefix of the text. |
| test_app.py::test_root_explains_where_the_ui_is_when_only_the_api_is_served | WEAK | Both API-only pages (dev mode and "no build found") contain the asserted strings; INSTALL.md says "The page says which case applies". | Assert the dev-mode wording is present and the no-build wording is not; add the no-build case. |
| test_app.py::test_unknown_api_path_is_a_json_404 | WEAK | Runs only with `SERVE_FRONTEND=false`, where no UI routes exist; main.py promises JSON 404s for `/api` in production mode, which no backend test loads. | Also run against the app in production mode (serve_frontend true with a minimal build in a temp folder). |
| test_app.py::test_wrong_method_is_a_405 | WEAK | Status code only, dev mode only. | Assert the JSON body; also in production mode. |
| test_app.py::test_config_for_the_default_claude_code_provider | WEAK | The provider/model it checks come from conftest's pinned environment, not from the defaults in `config.py`; changing the shipped defaults passes. | Build `Settings` without those variables (or clear the cache with them removed) and assert the documented defaults (claude-code, opus). |
| test_app.py::test_config_reports_logged_out_claude_code | WEAK | Compares with the app's own `LOGIN_HINT` constant. | Assert the documented command `claude auth login` appears in the hint. |

### 2.2 Backend: search, full text, outline, PDF (`test_search.py`, `test_fulltext.py`, `test_outline.py`, `test_pdf_extraction.py`)

| Test | Category | Problem | What it should check |
|------|----------|---------|----------------------|
| test_search.py::test_openalex_abstract_is_rebuilt_from_the_inverted_index | WEAK | No word has more than one position; a rebuild that keeps only each word's first position passes. Real abstracts repeat words. | e.g. `{"the": [0, 3], "cat": [1], "saw": [2], "dog": [4]}` → "the cat saw the dog". |
| test_fulltext.py::test_redirect_loops_give_up | WEAK | Expected count comes from the code's own `MAX_REDIRECTS`; README promises "at most 5". | Literal 6 requests (1 + 5 redirects); optionally a chain of exactly 5 that succeeds. |
| test_fulltext.py::test_public_address_check_returns_the_ip_to_connect_to | REDUNDANT | Duplicates `test_download_connects_to_the_checked_address`. | Delete, or repurpose: a host resolving to one public and one private address must be refused (needs the fake DNS to return several addresses). |
| test_outline.py::test_outline_lists_the_sections_of_the_pdf | WEAK | `top` checked only as 0–1; setting every `top` to 0 passes. `top` drives "jump to section" and the highlight. | Order within a page (Abstract above 1 Introduction on page 1; 2 Method above 3 Experiments above 4 Conclusion on page 2), or compare with the generator's y position. |
| test_outline.py::test_section_headings_are_passed_to_the_model_as_data | BRITTLE | Matches the exact spacing of `json.dumps`; the same string is pinned in test_llm_service.py. | Parse the `<headings>` block as JSON and compare; use a title containing `"` to exercise escaping. |
| test_pdf_extraction.py::test_locate_headings_in_reading_order | WEAK | Every title is found on the same page either way; a search that does not move forward passes. | An out-of-order case: `["Experiments", "Introduction"]` → `[2, None]`. |
| test_pdf_extraction.py::test_heading_beats_an_earlier_mention_in_the_text | REDUNDANT | Same search as the reading-order test. | Delete, or repurpose for the untested rule that a heading line starting with the title beats a mention in running text. |
| test_pdf_extraction.py::test_only_the_first_300_pages_are_read | BRITTLE | Pins the bare constant `MAX_PDF_PAGES_FOR_TEXT = 300`, which no document mentions. | If the cap is intended: assert via the constant **and** check that the cut is disclosed the way README promises for long papers ("the model and the UI are told"). |

### 2.3 Backend: summaries, Q&A, LLM service, Claude Code CLI (`test_summary.py`, `test_chat.py`, `test_llm_service.py`, `test_claude_code_cli.py`)

| Test | Category | Problem | What it should check |
|------|----------|---------|----------------------|
| test_chat.py::test_questions_about_an_unsaved_paper_work_and_are_kept_when_it_is_saved | WEAK | Ignores the response of `POST /save` and only counts history; a `/save` returning 500 passes. | `/save` returns 200 with `in_library` true, the paper is listed, and the history contents are exact. |
| test_chat.py::test_longest_allowed_question_is_accepted | WEAK | Status 200 only, but this endpoint reports failures in-band with 200. | The stream ends in `done`, the model got the full 4,000-character question, and it was saved. |
| test_chat.py::test_invalid_questions_are_rejected (case with a 101-character model) | WRONG | A 101-character model id is also rejected by the unknown-model check, so the case cannot detect losing `max_length=100`. | Assert the 422 is a validation error on `body.model` (FastAPI's list-shaped detail). |
| test_chat.py::test_follow_up_question_through_claude_code | BRITTLE | Pins exact prompt sentences; the fake CLI parses the same wording. Keep the behavior: it is the only test that catches the Claude Code path dropping history. | Earlier Q and A appear inside a `<turn-…>` tag and the prompt ends with the new question; make the fake independent of the wording. |
| test_llm_service.py::test_context_with_full_text | BRITTLE | Pins the whole `<paper>` block byte for byte. | Assert the pieces: kind, truncated, title/authors/year/page count/full text present, `cache_control` on the paper block, and `system_text` contains both instructions and paper. |
| test_llm_service.py::test_claude_code_errors_reach_the_user_unchanged | REDUNDANT | Uses `match=` (regex search), so "unchanged" is never checked; exact-equality tests elsewhere already cover it. | Delete, or make it an exact equality check. |
| test_llm_service.py::test_api_answer_cut_off_at_the_length_limit | WEAK | Only `endswith(note)`; replacing the answer by the note alone passes. | Exact text: answer + note. |
| test_claude_code_cli.py::test_cli_is_locked_down_and_gets_the_prompts | WEAK | Compares argv with the app's own `LOCKDOWN_ARGS`; removing `--tools ""`, `--strict-mcp-config`, and `--safe-mode` passes all backend tests. README/INSTALL document the lock-down. | Assert the literal flags (`--tools ""`, `--disallowedTools mcp__*`, `--strict-mcp-config`, `--setting-sources ""`, `--no-session-persistence`, `--disable-slash-commands`, `--safe-mode`, `--max-turns 1`) and that the system prompt is not on argv. |
| test_claude_code_cli.py::test_lines_that_are_not_events_are_skipped | WEAK | Collects the streamed chunks but never asserts them; streaming junk lines to the user passes. | `"".join(chunks) == "Still answered."` |
| test_claude_code_cli.py::test_a_hanging_cli_is_stopped_at_the_timeout | WEAK | Shows `run()` returns quickly, not that the CLI was killed. | Have the fake record its PID; after `run()` the process must be gone. |
| test_claude_code_cli.py::test_status_ready | REDUNDANT | Same assertion as two other status tests. | Delete or merge. |
| test_claude_code_cli.py::test_summary_request_through_the_provider | REDUNDANT | Same chain and checks as test_summary.py::test_summary_through_claude_code. | Delete. |

Also inside tests otherwise rated OK: `test_claude_code_answer_streams_and_names_the_model` asserts a timeout value that only exists in the fake; `test_summary.py` pins "Full text extracted from the PDF (2 pages)."; `fake_claude.py` picks its reply by matching prompt phrases, which couples many tests to prompt wording.

### 2.4 Frontend: api, router, App, pages

| Test | Category | Problem | What it should check |
|------|----------|---------|----------------------|
| api.test.ts > uploads a PDF as multipart form data | WEAK | Never looks at headers; a hand-set `Content-Type` without a boundary (breaks real uploads) passes. | No Content-Type header is set by the app. |
| api.test.ts > passes a cancellation through instead of calling it a network error | WEAK | The stub rejects regardless of the signal; removing the signal from the fetch call passes. | The stub honors `init.signal`; abort the controller and expect the abort error (or assert the same signal object is passed). |
| App.test.tsx > opens a paper in the reader and marks the tab it belongs to | WEAK | Only the unsaved case; a reader that always highlights Search passes. Relies on the `active` class. | Both cases (unsaved → Search, saved → Library, the other tab not active); no tab marked while the paper loads; the page settles after loading with no React errors logged (e.g. "Maximum update depth exceeded"). |
| SearchPage.test.tsx > shows each result with title, authors, year, venue, abstract, and links | FLAKY | Hard-codes "1,234", but the app uses `toLocaleString()`; fails under a German locale. | Build the expected text with `toLocaleString()` (or pin a locale in the test setup). |
| SearchPage.test.tsx > offers OpenAlex when arXiv fails | WEAK | Never inspects the second request; README says it "runs the same query on OpenAlex". | Assert the second request is `q=<failed query>&source=openalex&page=1&per_page=10`. |
| LibraryPage.test.tsx > links to the stored PDF of a paper that has one | WEAK | The only paper with a stored PDF has no `pdf_url`, so the test cannot tell which link wins. | Add a paper with both a stored PDF and a `pdf_url`; decide the expected link from PaperCard's documented intent (its prop comment). |
| LibraryPage.test.tsx > filters on the server as the user types | FLAKY | Depends on real 200 ms debounce timing. | Fake timers with user-event's `advanceTimers`. |
| PaperPage.test.tsx > says how long an unsaved paper is kept | WEAK | Uses the default (7), so a UI hard-coding "7 days" passes. | A non-default value (3 → "after 3 days") and 1 → "after 1 day". |
| PaperPage.test.tsx > falls back to the default model when the remembered one is gone | WRONG | The default is also the first option, and a `<select>` with an unknown value shows its first option, so the test cannot fail. | Put the default after another option; also check the request sends the default model. |

### 2.5 Frontend: components and end-to-end

| Test | Category | Problem | What it should check |
|------|----------|---------|----------------------|
| ChatPanel.test.tsx > asks a typed question with Enter and streams the answer | WEAK | All events arrive before the first assertion; the live answer is never checked (README: answers stream in). | Send one text event, assert it is shown while "Answering…", then finish. |
| ChatPanel.test.tsx > is disabled with an explanation when the LLM is unavailable | WEAK | Passes a hint but asserts only the heading. | The hint text is shown. |
| SummaryPanel.test.tsx > tells the user when a long paper was cut off | WEAK | No negative case. | The note is absent when `truncated` is false. |
| FullTextStatus.test.tsx > attaches a PDF the user has | WEAK | The file goes straight into the hidden input; the "Attach PDF" button is never clicked. | Click "Attach PDF" (it opens the picker), then upload. |
| PaperCard.test.tsx > calls back instead of navigating when the title opens the reader | WEAK | In jsdom the asserted hash cannot change; removing `preventDefault` passes. | Assert the click's default was prevented. |
| PaperCard.test.tsx > toggles the full abstract | BRITTLE | Asserts the CSS class `clamped`. | Assert accessible state (e.g. the toggle's label/`aria-expanded`). |
| SectionsPanel.test.tsx > lists the sections with their pages | BRITTLE | Asserts the styling class `level-2`. | Drop it or use semantic structure. |
| SectionsPanel.test.tsx > highlights the section being read | BRITTLE | Only through the class `active`. | Accessible marker (e.g. `aria-current`) or visible state. |
| UploadBox.test.tsx > uploads a PDF dropped onto it | BRITTLE | Finds the zone by CSS class, asserts `dragging`, never checks which file was sent. | Query by role/label; assert the sent file name. |
| e2e search-and-library > filter the library and remove a paper | WEAK | Removal checked only in page state, which filters removed ids anyway. | Reload (or query the API) and assert the paper is gone on the server. |
| e2e reader > open a search result without saving it, ask about it, then save it | WEAK | Counts chat bubbles loaded before Save; order-dependent because unsaved papers leak between tests. | Reload after Save and assert the conversation; reset unsaved papers between tests. |
| e2e reader > the model menu changes the model that answers | WEAK | The fake CLI ignores `--model`, so a backend ignoring the choice passes. | Make the fake report the model it received and assert the provenance; find the menu by its label. |
| e2e upload-summary-chat > upload a PDF: its metadata is extracted and the PDF is shown | WEAK | Substring checks on authors/year, prefix regex on the abstract; react-pdf class names. | Exact author list and full abstract. |
| e2e upload-summary-chat > ask questions about the uploaded paper, with follow-ups | FLAKY | May reload while the second answer is still streaming (saved only at the end), then sees 2 bubbles. | Wait for both answers to be saved before reloading; reload after Clear too. |
| e2e upload-summary-chat > a failed answer is reported and nothing is saved | WEAK | The "nothing saved" check runs before the history has loaded. | Wait for the chat request, or query the API. |
| e2e upload-summary-chat > summarize the sections and jump to one | WEAK, and failed once in four clean runs | Verified only by "Page 2 of 2", while three sections are on page 2; it clicks before checking that the PDF pages have rendered. | Wait for the pages to render; assert the target heading is near the top of the viewer or becomes the highlighted section. |

### 2.6 Test infrastructure

- `frontend/src/test/fetchMock.ts`: unregistered requests get a silent 501; nothing fails the
  test. Fail in `afterEach` when a request was not handled.
- `frontend/e2e/support/app.ts` `emptyLibrary()`: deletes only saved papers (the list endpoint
  shows only those); papers opened but not saved, and their chats, leak between tests.
- `backend/tests/support/upstream.py`: the canned arXiv entry has a real
  `arxiv.org` PDF link; opening it in an end-to-end test would use the internet.
- `backend/tests/conftest.py`: fakes are installed by patching `get_client`/`stream_reply`
  in each module separately, and per-test reset patches private globals one by one
  (misses e.g. `fulltext._locks`); the e2e launcher duplicates the settings isolation.
- The backend suite cannot run twice in one Python process: `pytest_sessionfinish` deletes
  the temp data folder while `app.db` stays cached with its engine.
- No test fails on unexpected React console errors.

## 3. Coverage report (clean checkout)

Backend (coverage.py): 94.4% of lines (1,747/1,850), 87.5% of branches (443/506).

| File | Line % | Branch % |
|------|--------|----------|
| app/services/http.py | 66.7 | 25.0 |
| app/main.py | 77.2 | 50.0 |
| app/db.py | 87.2 | 62.5 |
| app/routers/papers.py | 91.8 | 89.2 |
| app/services/fulltext.py | 93.2 | 86.1 |
| app/services/pdf.py | 93.3 | 81.0 |
| app/routers/assistant.py | 93.9 | 82.1 |
| app/services/arxiv.py | 94.1 | 90.6 |
| app/services/claude_code.py | 95.3 | 92.9 |
| app/routers/search.py | 96.8 | 83.3 |
| app/config.py | 97.7 | 50.0 |
| app/services/llm.py | 98.9 | 97.0 |
| others (models, schemas, cache, openalex) | 100 | 83–100 |

Frontend (V8): 81.2% of lines, 78.5% of branches.

| File | Lines % | Branches % |
|------|---------|------------|
| src/components/PdfViewer.tsx | 0 | 0 |
| src/components/ErrorBoundary.tsx | 66.7 | 50.0 |
| src/pages/PaperPage.tsx | 88.0 | 72.0 |
| src/components/ChatPanel.tsx | 88.9 | 92.5 |
| src/components/Markdown.tsx | 88.9 | 66.7 |
| src/useModelChoice.ts | 90.9 | 100 |
| src/components/UploadBox.tsx | 95.8 | 88.9 |
| src/components/FullTextStatus.tsx | 96.7 | 90.5 |
| src/api.ts | 98.5 | 80.8 |
| src/useLlmStream.ts, SearchPage.tsx, LibraryPage.tsx, others | 100 | 50–96 |

## 4. Behavior no test checks

Each item states the intended behavior and where it is documented.

**Search (F1)**
- arXiv requests are spaced 3 s apart (README; `arxiv.py`); every test switches the spacing off.
- arXiv cooldown: `Retry-After` above 600 s is capped at 600, below 60 s or non-numeric gives 60, and arXiv is called again once the pause ends (README; INSTALL "up to 600 seconds").
- Search cache: entries expire after 10 minutes, the cache holds at most 256 entries, and `per_page` is part of the key (README; `search.py`).
- The response echoes the requested page (feeds "Load more").
- The largest valid values are accepted: page 100, per_page 50, a 300-character query.
- An arXiv connection error gives 502 "Could not reach arXiv…" without starting a cooldown.

**Library (F2)**
- Database upgrade: `init_db` adds missing nullable columns to an older database and back-fills `in_library`/`saved_at`, and stops with a clear error for a new NOT NULL column (`db.py`).
- Pruning keeps a PDF that another paper still uses; the cleanup runs every 12 hours and carries on after a failed run (`main.py`); a paper saved or reopened between the SELECT and the DELETE is kept (`cache.py`).
- Production mode: `/` serves index.html with `Cache-Control: no-cache`, `/favicon.svg` and `/assets` are served, the no-build page explains itself, and a `backend/.env` file triggers the documented warning.
- Re-opening an unsaved paper through `POST /api/papers/open` refreshes `last_opened_at`; input validation on `/open`.
- Saving an unsaved paper keeps its summary and section outline, not only its chat.

**Upload and metadata (F3)**
- When arXiv's metadata is rejected or arXiv does not know the id, the first pages go to the model (`papers.py`).
- Upload during an arXiv pause skips the lookup, sends no arXiv request, and still succeeds.
- `looks_like_pdf` accepts up to 1 KB of junk before `%PDF-` and rejects it beyond that.
- A real title stored in the PDF's properties that starts with "Main", "Paper", "Document", or "arXiv" is kept; only placeholder titles are filtered (comment in `pdf.py`).
- When the PDF has more pages than are read, the cut is disclosed like any other cut (README: the model and the UI are told when the text is cut off).
- `GET /{id}/pdf` when the recorded file is gone; attaching to a paper deleted mid-request (404, stored file removed); oversized, corrupt, or encrypted files sent to the attach endpoint leave the paper unchanged.

**Full-text download (F4 context)**
- A host with a private address among its addresses is refused; TLS uses the real host name while connecting to the pinned IP; each redirect hop connects to its own checked IP.
- A malformed PDF link (an invalid port such as `:99999`, or a broken IPv6 literal) is an expected failure: it is recorded in `full_text_status`/`full_text_error` "rather than raised" (`ensure_full_text` docstring), and the reader falls back to the abstract.
- A non-HTTP link (`ftp://`) is refused with a reason that is true for it.
- One download per paper at a time; a paper deleted mid-download gives 404 and nothing is stored.
- `GET /outline` downloads the PDF of a search result that was never fetched, then lists its sections.

**Summaries and Q&A (F4, F5)**
- Refusal, cut-off, and empty answers through the real Claude Code path (the fake CLI already has `refusal`, `max_tokens`, and `empty` modes): an error event, and the previous summary kept.
- An answer that is empty but stopped at the length limit: per the empty-answer guard, it is an error and nothing is saved.
- Cancelling a streamed answer saves nothing and stops the CLI.
- After a failed PDF download (404, private address), summaries and answers use the abstract and are labelled so, without re-downloading each time.
- `/summary` and `/chat` end to end with the API provider (`LLM_PROVIDER=api`).
- `/chat` with nothing to read gives 422; a paper deleted during its full-text download gives 404 (both endpoints).
- Section summaries are discarded (404/409) when the paper is deleted or its PDF replaced during the model call.
- The metadata prompt's privacy instruction; a status check that times out counts as ready; the 3 s not-ready cache; effort omitted for Haiku in API-mode metadata extraction; "Could not start Claude Code".

**Frontend**
- Back navigation uses the browser history when there is an earlier in-app page.
- The reader rechecks `/api/config` on window focus, at most every 5 s.
- Streamed answers are aborted on unmount and when a new request starts.
- Out-of-order responses: an older search answering last is dropped; a stale library filter response is dropped and does not bring back a deleted paper.
- "Search OpenAlex instead" appears only after a failed arXiv search, and runs the query that failed.
- After a refused attachment, the user can still attach another file.
- Error paths: non-404 load errors, failed save, failed or cancelled remove in the reader, the PDF viewer's load failure and the ErrorBoundary fallback, a failed library removal (500) leaves the paper listed.
- "Load more" stops at page 100.
- Chat: a new answer is appended below the earlier ones; Enter while streaming does not send a second question; a failed Clear keeps the conversation; Clear is disabled while streaming.
- Sections: the outline reloads when the paper gains a PDF; the "being read" rule.
- PdfViewer (no unit tests): zoom in/out and Fit width keep the reading position; "Open PDF ↗"; the load-failure message.
