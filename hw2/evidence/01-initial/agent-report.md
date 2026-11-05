# P1 subagent's final report (verbatim)

Agent: fresh-context Claude Code subagent (general-purpose), started 2026-11-04 with
the prompt in `prompt-sent.md`. It used 181 tool calls, about 514k tokens, and 52
minutes. These are its own claims; the evaluation in this folder checks them.

---

I added a test suite with three layers (pytest for the backend, Vitest with React Testing Library for the frontend, and Playwright end-to-end tests). In the last run all 522 tests passed with `make test` from the repo root. No application code was changed, nothing was committed, and `demo/` was not touched.

## Last run (`make test`, exit code 0)

| Suite | Tests | Time |
|---|---|---|
| Backend (pytest) | 360 passed | 6.9 s |
| Frontend (Vitest) | 148 passed | about 4 s |
| End-to-end (Playwright, Chromium) | 14 passed | 11.3 s |

The unit suites also passed three more times in a row, and once with the backend files in reverse order.

To check that the tests catch real bugs, I put 21 deliberate bugs into scratch copies of the code (12 backend, 9 frontend), and at least one test failed for each. The real `backend/data/app.db` is byte-identical after all runs, and no temp folders or processes are left behind.

## Commands
- **Everything:** `make test`
- **Backend:** `cd backend && uv run pytest`
- **Frontend:** `cd frontend && npm test`
- **End-to-end:** `make test-e2e`, which first runs `npm run test:e2e:install` (a quick no-op once the browser is there) and then `npm run test:e2e`.

## Coverage of the five features
- **Search:** 38 backend tests, 18 frontend tests, 4 end-to-end tests. They cover OpenAlex and arXiv parsing, input validation, upstream errors and timeouts, arXiv rate-limit pauses, caching, and saved-result markers.
- **Library:** 62 backend tests, 11 frontend tests. They cover saving, duplicates across sources, opening without saving, filtering (including non-ASCII names), editing, deleting, data surviving a restart, and cleanup of unsaved papers.
- **Upload and metadata:** 28 backend upload tests and 43 PDF-extraction tests, plus 7 upload-box and 7 edit-form frontend tests. They cover extraction from the layout, from arXiv, and from the LLM, plus non-PDF, corrupt, password-protected, scanned and oversized files.
- **Summaries:** 17 backend tests, 11 frontend tests. They check the summary uses the full text or falls back to the abstract, and cover streaming, failures, regeneration, truncation, and the paper being deleted mid-answer.
- **Questions:** 27 backend tests, 12 frontend tests. They cover follow-up history and its limit, validation, failed answers saving nothing, and clearing the conversation.

There are also tests for open-access PDF download (including refusing local and private addresses), the section outline, both LLM providers, Markdown safety in model output, and the reader page.

## How the real LLM and network are kept out
- **Backend tests:** they never read `.env`. The Claude Code path points at a missing file and the API client at a closed local port with a fake key. They use a fake model, or a fake `claude` program that answers in the CLI's streaming format. Every outgoing HTTP request and DNS lookup is faked, and any request no test registered fails the test.
- **End-to-end tests:** they run the real app (built UI, backend, SQLite) on port 8765, with a fake OpenAlex/arXiv server and the fake `claude`. The launcher refuses to start if the port is in use, never touches 8000 or 5173, builds the UI into a temp folder so `frontend/dist` is untouched, and deletes its temporary database afterwards.

## Things you should know
- **Dev dependencies:** pytest 9.2 and pytest-asyncio are new in `backend`. Vitest 5.1, jsdom 29, React Testing Library and Playwright 1.64 are new in `frontend`. Both lockfiles only gained packages; no existing version changed, and `./scripts/setup.sh --check` still passes.
- **Playwright browser:** it is stored in `frontend/node_modules` (about 206 MB) so nothing is written outside the repo. `npm ci` deletes it, and the next `make test-e2e` downloads it again (needs network once).
- **Tests are part of the build:** frontend test files are in `src/`, so `npm run build` type-checks them. A type error in a test would fail the production build. Type-check and lint pass now.

## What I could not test
- **Real Claude, through either provider:** excluded on purpose. Compatibility with the real CLI output and the real API parameters is not verified; the fakes reflect what the app's code expects.
- **Real OpenAlex and arXiv responses:** all search results are canned.
- **Real-world PDFs:** the test PDFs are generated with standard fonts, so two-column layouts, small caps and real ligature characters are not covered. Ligature handling is tested on text only.
- **Timing races:**
  - not tested: deleting a paper during a PDF download, two identical saves at once, a PDF replaced during section summaries, the 12-hour cleanup loop, and arXiv's 3-second spacing (set to 0 in tests). These would need timing hooks in the app.
  - tested: deleting a paper while a summary or answer is being written.
- **PDF viewer:** zoom, scrolling and the current-section highlight are only covered lightly, in Chromium only. `scripts/setup.sh` is not tested.
- **Search page stale-response guard:** a late answer from an earlier search can't be produced through the UI, because every way to start a search is disabled while one runs.
- **Helpful but optional app change:** if the OpenAlex and arXiv URLs were settings, the end-to-end tests could start the unmodified server instead of patching those constants in their launcher.

Minor findings, not changed:
- A non-HTTP PDF link such as `ftp://` gets the misleading message "points to a local or private address".
- The README still says "There are no automated tests yet".

## Files
Changed:
- `Makefile`: added the `test`, `test-backend`, `test-frontend` and `test-e2e` targets.
- `backend/pyproject.toml`: dev dependencies and pytest settings.
- `backend/uv.lock`
- `frontend/package.json`: dev dependencies and the test scripts.
- `frontend/package-lock.json`
- `frontend/.gitignore`: Playwright output folders.

Created, in `backend/tests/`:
- `conftest.py`
- `test_app.py`, `test_search.py`, `test_library.py`, `test_upload.py`, `test_fulltext.py`, `test_summary.py`, `test_chat.py`, `test_outline.py`, `test_llm_service.py`, `test_claude_code_cli.py`, `test_pdf_extraction.py`
- `support/`: `__init__.py`, `pdfs.py`, `upstream.py`, `papers.py`, `fake_llm.py`, `fake_claude.py`, `e2e_server.py`

Created, in `frontend/`:
- `vitest.config.ts`, `playwright.config.ts`
- `src/test/`: `setup.ts`, `fetchMock.ts`, `fixtures.ts`
- `src/api.test.ts`, `src/router.test.ts`, `src/App.test.tsx`
- `src/pages/`: `SearchPage.test.tsx`, `LibraryPage.test.tsx`, `PaperPage.test.tsx`
- `src/components/`: `ChatPanel.test.tsx`, `SummaryPanel.test.tsx`, `UploadBox.test.tsx`, `EditPaperForm.test.tsx`, `FullTextStatus.test.tsx`, `SectionsPanel.test.tsx`, `Markdown.test.tsx`, `PaperCard.test.tsx`
- `e2e/`: `search-and-library.spec.ts`, `upload-summary-chat.spec.ts`, `reader.spec.ts`, `support/app.ts`, `support/serve.mjs`
