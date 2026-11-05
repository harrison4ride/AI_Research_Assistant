# `/code-review high` on round 2's changes (hw2-round1..hw2-round2): raw output

Run on 2026-11-04 as an evaluation lens (forked execution of the code-review skill), with
these arguments:

> high hw2-round1..hw2-round2 (round 2 of improving the agent-generated test suite; only
> test code and test configuration changed. Review the changed and added tests for
> incorrect expectations, tests that cannot fail or pass for the wrong reason, weak
> assertions, flakiness or timing dependence, isolation leaks, and test-infrastructure
> bugs. The expected-failure tests (backend @known_bug with fails_until_fixed(), frontend
> itFailsUntilFixed) mark confirmed application bugs: check that each one asserts
> genuinely intended behavior, fails only because of the bug it names, and would pass once
> the app is fixed. Do not run the Playwright end-to-end tests and do not start servers on
> ports 8000, 5173 or 8765.)

Verbatim result:

---

I reviewed hw2-round1..hw2-round2 and found 10 issues. Both suites pass as they stand: the backend has 553 passed and 5 strict xfails, all ending in `StillBroken`, and the frontend has 186 passed and 4 expected failures. I did not run the Playwright tests or start any servers. No CLAUDE.md applies to these files.

The most serious finding is a test that hard-codes a garbled error message as correct. Next come three expected-failure tests where an unrelated failure, or a fix of only part of the bug, would still count as "still broken". The last three are minor cleanup.

```json
[
  {
    "file": "backend/tests/test_search.py",
    "line": 284,
    "summary": "test_arxiv_rejection_without_a_reason_is_reported asserts the garbled detail \"arXiv rejected the query: arXiv rejected the query.\" as the correct message, so it locks in an app defect: arxiv.py:94's fallback text gets the same prefix again at arxiv.py:161.",
    "failure_scenario": "arXiv returns an error entry with no <summary>, and the user sees the stuttering message. If someone fixes the message (e.g. to \"arXiv rejected the query.\"), this test fails and pushes them to undo the fix. It should be a @known_bug test of the intended message, or check only the status and the prefix."
  },
  {
    "file": "backend/tests/test_llm_service.py",
    "line": 384,
    "summary": "test_an_empty_answer_cut_off_at_the_length_limit_is_an_error catches every LlmError from both providers, records its message, and compares the messages only inside fails_until_fixed(), so any unrelated LlmError counts as the known bug.",
    "failure_scenario": "Suppose _stream_api later adds a credentials check, or the Claude Code path raises \"Claude Code not found\". The mismatch becomes StillBroken and the strict xfail still passes, which hides a new failure. Before the `with`, the test should assert that each outcome is either the buggy answer (only the cut-off note) or the expected error."
  },
  {
    "file": "backend/tests/test_fulltext.py",
    "line": 329,
    "summary": "Two distinct malformed links are now merged into one expected-failure test (and likewise the 4 titles in test_upload and the 2 providers in test_llm_service), so fixing one case is invisible while the others still fail. The invalid port fails in `parts.port`; the broken IPv6 literal fails in `urlsplit`.",
    "failure_scenario": "A fix catches the port ValueError but not the IPv6 one. The test still raises StillBroken, so nobody sees that the port case now works, and it can later regress unnoticed. The round-1 version, one test per link, reported each case on its own."
  },
  {
    "file": "backend/tests/test_fulltext.py",
    "line": 152,
    "summary": "test_a_pdf_download_cannot_hang_forever only checks that the request's timeout values are numbers. The shared AsyncClient in http.py already defaults to timeout=20.0, and httpx timeouts apply to each read, not to the whole download.",
    "failure_scenario": "Deleting `timeout=60.0` from `_download` still passes, because the client's 20 s default is still numeric. A host that sends one byte every 19 s also never times out, so the download can hang forever while the test claims it cannot. The test fails only if someone passes timeout=None explicitly."
  },
  {
    "file": "frontend/src/pages/LibraryPage.test.tsx",
    "line": 62,
    "summary": "The round-1 expected-failure test (a stored copy should be linked even when an open-access link exists) was deleted and replaced by a test asserting the opposite. PaperCard.tsx:35 still documents localPdfHref as \"Link to a locally stored copy of the PDF, when the library has one\".",
    "failure_scenario": "The open-access download fails (e.g. 403) and the user attaches the PDF by hand. The library card's \"PDF ↗\" still opens the broken publisher link, and the new tests (here and PaperCard.test.tsx:92) assert exactly that, so the reported bug is now encoded as correct behavior."
  },
  {
    "file": "frontend/src/test/fetchMock.ts",
    "line": 125,
    "summary": "The new check for requests sent after a test ended (`mock.ended` / takeLateRequests) almost never runs. unstubGlobals restores fetch at the start of the next test (Vitest's onBeforeTryTask), and that test's mockFetch then replaces the global fetch.",
    "failure_scenario": "A component from test A fetches after A's cleanup. The request goes to the real fetch, or to test B's mock, where it is reported as B's unmocked request. That is the misattribution the comment says this code prevents; only requests in the short gap between A's afterEach and the start of B are ever reported as late."
  },
  {
    "file": "backend/tests/test_fulltext.py",
    "line": 317,
    "summary": "The ftp expected-failure check requires the word \"http\" in the fixed error message. That is one particular wording, not the intended behavior (a true reason that does not mention private addresses).",
    "failure_scenario": "A correct fix that reports \"Only web links can be downloaded.\" still fails the check inside fails_until_fixed. The strict xfail keeps passing as StillBroken and the fix goes unnoticed."
  },
  {
    "file": "backend/tests/test_library.py",
    "line": 190,
    "summary": "In test_a_result_that_another_request_stores_at_the_same_moment_is_not_stored_twice, the `in_library` assertion cannot fail: the simulated competing request stores the same in_library value that the endpoint under test would set.",
    "failure_scenario": "If reuse() stopped promoting an unsaved copy into the library when a save races an open, the test would still pass. The open-then-save race is the case where promotion matters, and it is never exercised."
  },
  {
    "file": "backend/tests/test_pdf_extraction.py",
    "line": 42,
    "summary": "test_the_text_is_every_page_in_order_separated_by_blank_lines builds its expected value with the same PyMuPDF calls the app uses (page.get_text().strip() joined with blank lines), so it checks the implementation against itself.",
    "failure_scenario": "Any defect in how get_text() orders or drops text appears in both the expected and the actual value, and the test passes. Its only effect is to block legitimate cleanup such as de-hyphenation. An independent check would assert that known markers appear in page order."
  },
  {
    "file": "backend/tests/test_upload.py",
    "line": 299,
    "summary": "The \"pad the sample PDF to exactly N MB plus extra bytes\" logic is repeated inline here and as the with_size() helper in test_fulltext.py:49, instead of living once in support/pdfs.py.",
    "failure_scenario": "Two copies of the boundary arithmetic for the size limit can drift apart, so one of the over-limit tests could quietly stop testing exactly one byte over."
  }
]
```
