# Testing

The app has three automated test suites. None of them calls a real LLM or an outside
service, reads your `.env`, or touches your library in `backend/data/`. The only
download is Chromium for the end-to-end tests, once (see [Install](#install)).

| Suite | Location | Tools | Tests |
|-------|----------|-------|-------|
| Backend | `backend/tests/` | pytest, pytest-asyncio | 558: 553 pass, 5 are expected failures |
| Frontend | `frontend/src/**/*.test.ts(x)`, next to the code they test | Vitest, React Testing Library, jsdom | 190: 186 pass, 4 are expected failures |
| End-to-end | `frontend/e2e/` | Playwright with Chromium | 15 |

The nine expected failures check application bugs that are confirmed but not fixed
yet; see [Known Bugs](#known-bugs).

## Install

Install the app as [INSTALL.md](../INSTALL.md) describes (`make install` runs
`scripts/setup.sh`). That also installs the test tools: uv installs the backend's
`dev` dependency group, and npm installs the frontend's devDependencies. The tests
need neither an Anthropic API key nor a Claude Code login.

The end-to-end tests also need Playwright's Chromium (about 210 MB). `make test-e2e`
and `make test` download it into `frontend/node_modules/` the first time; without
`make`, run `cd frontend && npm run test:e2e:install`.

## Run the Tests

| Command | What it runs | Result |
|---------|--------------|--------|
| `make test` | all three suites, in the order below | |
| `make test-backend` | `cd backend && uv run pytest` | `553 passed, 5 xfailed` |
| `make test-frontend` | `cd frontend && npm test` | `Tests  186 passed \| 4 expected fail (190)` |
| `make test-e2e` | `cd frontend && npm run test:e2e:install && npm run test:e2e` (the first command downloads Chromium if it is missing) | `15 passed` |

To run one file or a subset, call the tools directly, for example
`cd backend && uv run pytest tests/test_search.py -k cache` or
`cd frontend && npx vitest run src/pages/SearchPage.test.tsx`.

The end-to-end tests build the UI into a temporary folder and start the real backend
on port 8765, with an empty temporary database, fake arXiv, OpenAlex, and PDF hosts,
and a fake `claude` program. They refuse to start when port 8765 is in use, so they
never talk to a server you started yourself; set `E2E_PORT` to use another port.

The backend suite can also run in parallel processes:
`cd backend && uv run --with pytest-xdist pytest -n 8`.

## Measure Coverage

| Command | What it runs | Report |
|---------|--------------|--------|
| `make coverage` | both commands below | |
| `make coverage-backend` | `cd backend && uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=html --cov-report=json:htmlcov/coverage.json`, then prints the line and branch percentages from that JSON | the files with uncovered lines, a last line `Backend coverage: lines … branches …`, and `backend/htmlcov/index.html` |
| `make coverage-frontend` | `cd frontend && npm run test:coverage` | a table per file, then `Lines` and `Branches` totals, and `frontend/coverage/index.html` |

The backend measures `backend/app` (set in `backend/pyproject.toml`), and the frontend
measures `frontend/src` without the test files and `src/test/` (set in
`frontend/vitest.config.ts`). The `TOTAL` row of the backend table is coverage.py's
combined figure for statements and branches (98%); the line after it gives the two
separately.

Coverage of the current suite, whose tests are those of tag `hw2-round2`, in a clean
checkout:

| Suite | Lines | Branches |
|-------|-------|----------|
| Backend | 98.6% (1,825 of 1,850 statements) | 95.7% (484 of 506) |
| Frontend | 94.78% (600 of 633) | 86.09% (520 of 604) |

The end-to-end suite is not measured for coverage.

## Known Bugs

Nine tests check behavior that the app gets wrong today. Each is marked as an expected
failure, so the suite stays green, and each may fail only at the one check its bug
breaks. A failure anywhere else in such a test (a setup step, a request no test
registered, an unexpected console error) is reported as a normal failure.

| Bug | Test |
|-----|------|
| An empty answer that stopped at the length limit is saved as only the "cut off" note | `backend/tests/test_llm_service.py::test_an_empty_answer_cut_off_at_the_length_limit_is_an_error` |
| An `ftp://` PDF link is refused as "a local or private address" | `backend/tests/test_fulltext.py::test_a_link_that_is_not_http_is_refused_with_a_true_reason` |
| A malformed PDF link (port 99999, a broken IPv6 address) gives HTTP 500 | `backend/tests/test_fulltext.py::test_a_malformed_pdf_link_is_recorded_and_the_abstract_is_used` |
| Text after page 300 is dropped without telling the model or the reader | `backend/tests/test_summary.py::test_a_pdf_longer_than_the_page_limit_is_reported_as_cut_off` |
| A real PDF title that starts with "Main", "Paper", "Document", or "arXiv" is discarded | `backend/tests/test_upload.py::test_a_real_title_in_pdf_properties_is_kept_whatever_word_it_starts_with` |
| The reader re-renders without end while a paper is open | `frontend/src/App.test.tsx`: "settles after opening a paper, without React errors" |
| "Attach PDF" disappears after a refused file | `frontend/src/components/FullTextStatus.test.tsx`: "lets the user attach another file after a refused one" |
| "Search OpenAlex instead" searches the edited search box, not the query that failed | `frontend/src/pages/SearchPage.test.tsx`: "runs the query that failed on OpenAlex even after the search box was edited" |
| "Search OpenAlex instead" also appears after an OpenAlex search failed | `frontend/src/pages/SearchPage.test.tsx`: "offers OpenAlex only after an arXiv search failed" |

When a fix makes one of these tests pass, the suite fails on purpose: pytest reports
`XPASS(strict)`, and Vitest reports that the bug seems fixed. Then turn the test into
a normal one:

- **Backend:** remove the `@known_bug(...)` decorator and the
  `with fails_until_fixed():` line, and dedent the block that line held.
- **Frontend:** change `itFailsUntilFixed` to `it`, and replace the function the test
  returns at its end with that function's body: `return () => <check>` becomes
  `<check>`, and `return async () => { … }` becomes the statements inside the braces.
  Under plain `it`, a returned function is never called, so the test would pass without
  checking anything.

`backend/tests/support/known_bugs.py` and `frontend/src/test/knownBugs.ts` explain the
markers.

Four of the backend checks are coarser than that, as the HW2 evaluation showed, so
check them by hand after a fix:

- In the empty-answer test, any `LlmError` counts as the bug, so an unrelated error
  keeps it in XFAIL.
- The malformed-link test checks both links in one check, so fixing only one of them
  changes nothing.
- The ftp and 300-page tests expect particular words in the fixed message ("http" and
  "cut off"), so a correct fix worded differently still reports the bug as present.

## How the Tests Are Isolated

**Backend.** `backend/tests/conftest.py` sets every setting itself and never reads
`.env` (`support/isolation.py`). Each test process gets its own temporary folder for
the SQLite database and stored PDFs (`support/scratch.py`), and each test starts with
an empty database and fresh module-level state (`support/app_state.py`). All outgoing
HTTP requests go to fake arXiv, OpenAlex, and PDF hosts (`support/upstream.py`), which
fail any request that no test registered; DNS lookups are faked too. The model is a
fake (`support/fake_llm.py`, `support/fake_anthropic.py`), and the Claude Code provider
runs a fake `claude` program (`support/fake_claude.py`) that speaks the CLI's
streaming format. A controllable clock (`support/clock.py`) lets arXiv's 3-second
spacing and the 10-minute search cache run without real waiting.

**Frontend.** Every request goes to a fetch mock (`src/test/fetchMock.ts`). A request
that no test registered fails the test, and so does an unexpected `console.error`
(`src/test/console.ts`), which is how React reports problems such as render loops. A
request that a component sends after its test has ended is not reliably reported: it
reaches the next test's mock, or the real `fetch` once Vitest has restored it.
`src/test/stylesheet.ts` loads the app's `index.css`, so tests can check what the user
sees, for example that a long abstract is clamped until it is expanded.

**End-to-end.** `frontend/e2e/support/serve.mjs` starts the real app through
`backend/tests/support/e2e_server.py`, which isolates the settings the same way as the
backend tests and resets the database before each test.

## How the Suite Was Made

Claude Code generated these tests for HW2. One fresh-context agent wrote the initial
suite (tag `hw2-initial`), and two more agents improved it from feedback (tags
`hw2-round1` and `hw2-round2`). Application code did not change during this work:
`backend/app` and `frontend/src` (apart from test files) are the same at these tags as
at `hw2-baseline`.
