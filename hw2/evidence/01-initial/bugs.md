# Application bugs found while evaluating the initial suite

No test in the initial suite fails on the unmodified app (360/360 backend,
148/148 frontend; the one end-to-end failure is a flaky test, see
`eval/metrics.json` → `e2e`). The bugs below were found by **reviewing** the code
and tests, so the initial suite **did not detect** them. Each one is a gap for the
improvement rounds: a correct test must fail on it (marked `xfail(strict=True)`
until the app is fixed, because the app stays frozen during the experiment).

## BUG-1: an empty answer cut off at the length limit is saved as only the cut-off note

- **Where:** `backend/app/services/llm.py`, `_stream_claude_code` (lines 320–324) and
  `_stream_api` (lines 375–379).
- **Intended behavior:** an empty model answer is an error ("The model returned an
  empty answer. Try again.") and nothing is saved; README: "a failed or refused
  request never stores partial text".
- **Actual behavior:** the cut-off note is appended *before* the empty-answer
  check. When the model spends its whole token budget on thinking and returns no
  text with `stop_reason == "max_tokens"`, the answer becomes
  `"\n\n*(The answer was cut off because it reached the length limit.)*"`, passes
  the check, and the summary endpoint saves it over the previous good summary
  (`routers/assistant.py`, `save()` in `summarize`).
- **Reproduction (2026-11-04, scratch checkout of `hw2-initial`):** fake Claude Code
  run with `text=""`:
  - `stop_reason="end_turn"` → `LlmError: The model returned an empty answer. Try again.` (correct)
  - `stop_reason="max_tokens"` → saved text `'\n\n*(The answer was cut off because it reached the length limit.)*'` (bug)
- **Found by:** review G3 (backend LLM tests), confirmed by reproduction.
- **Detected by the initial suite:** no.

## BUG-2 (minor): a non-HTTP PDF link is reported as "a local or private address"

- **Where:** `backend/app/services/fulltext.py`, `ensure_full_text` (lines 193–194)
  maps every `UnsafeUrl` to "The PDF link points to a local or private address, so
  it was not downloaded.", but `_check_public` also raises `UnsafeUrl` for schemes
  other than http/https (`ftp://`, `file://`).
- **Intended behavior:** the full-text panel explains why only the abstract is
  available; for an `ftp://` link the reason is the unsupported scheme.
- **Impact:** low (the download is correctly refused; only the explanation is wrong;
  OpenAlex rarely gives non-HTTP links).
- **Found by:** the generating agent itself, which listed it as a "minor finding" in
  its report instead of writing a failing test.
- **Detected by the initial suite:** no (the test at `test_fulltext.py:191` checks
  only that such links are refused).

## BUG-3: a malformed PDF link makes every reader endpoint for that paper fail with 500

- **Where:** `backend/app/services/fulltext.py`, `_check_public` (`urlsplit(url)` and
  `.port`, lines 64–67) raises `ValueError` for links such as
  `https://example.org:99999/x.pdf` or `http://[::1/x.pdf`; `ensure_full_text`
  catches only `UnsafeUrl`, `TooLarge`, HTTP errors, and `PdfError`.
- **Intended behavior:** expected download failures are recorded in
  `full_text_status`/`full_text_error` "rather than raised" (docstring), and the
  reader falls back to the abstract and offers Attach PDF (README).
- **Reproduction (2026-11-04, scratch checkout of `hw2-initial`, TestClient with
  `raise_server_exceptions=False`):** for both links, `POST /fulltext`,
  `GET /outline`, and `POST /summary` all return **500**, and `full_text_status`
  stays `null`, so every later request fails the same way.
- **Severity:** medium for the affected paper (no summary, Q&A, or outline; the
  reader's error state offers only "Retry").
- **Found by:** review G2, confirmed by reproduction. **Detected by the initial suite:** no.

## BUG-4 (low): text beyond page 300 is dropped without being reported as cut off

- **Where:** `backend/app/services/pdf.py` reads at most `MAX_PDF_PAGES_FOR_TEXT = 300`
  pages but stores the full `page_count`; `llm.build_context` then tells the model
  "Full text extracted from the PDF (302 pages)." with `truncated=False`.
- **Intended behavior:** README: when the text is cut off, the model and the UI are told.
- **Reproduction:** a generated 302-page PDF: `page_count=302`, page 301's text
  absent, `truncated=False`, note "(302 pages)".
- **Found by:** review G2, confirmed. **Detected by the initial suite:** no; the
  test `test_only_the_first_300_pages_are_read` asserts the cut itself and so
  cements the undisclosed behavior.

## BUG-5 (low): real titles that start with "Main", "Paper", "Document", or "arXiv" are discarded as placeholders

- **Where:** `backend/app/services/pdf.py`, `JUNK_META_TITLE` has no word boundary
  after the placeholder words.
- **Intended behavior:** the comment says it filters "placeholder titles that PDF
  producers write into the metadata".
- **Reproduction:** `JUNK_META_TITLE.match("Maintaining Consistency in Distributed Logs")`
  and `.match("Paperclip Maximizers")` both match, so the layout guess replaces the
  PDF's real title.
- **Found by:** review G2, confirmed. **Detected by the initial suite:** no.

## BUG-6: the reader re-renders continuously while a paper is open

- **Where:** `frontend/src/App.tsx:73` passes a new inline `onLibraryState`
  callback on every render; `frontend/src/pages/PaperPage.tsx:41–43` runs an effect
  whenever that callback changes and calls it, and the callback stores a new object
  in App's state (`setPaperInLibrary({ id, inLibrary })`), which renders App again.
- **Intended behavior:** the page settles after loading (React's own warning:
  "Maximum update depth exceeded … one of the dependencies changes on every render").
- **Reproduction (2026-11-04, scratch checkout of `hw2-initial`, Vitest + React
  Profiler, `PdfViewer` mocked as in the suite):** in the 1 s after a paper loaded,
  2,661 React commits and 51 "Maximum update depth" warnings for an unsaved paper;
  3,109 commits and 59 warnings for a saved one. An earlier probe that waited inside
  `act()` never finished, because the effects keep scheduling updates.
- **Impact:** medium: constant CPU use whenever any paper is open; the page looks
  correct, so it is easy to miss.
- **Found by:** review G4, confirmed by measurement. **Detected by the initial suite:**
  no; the tests assert only what is rendered, and nothing fails on React console errors.

## BUG-7 (low): after a refused PDF attachment, the "Attach PDF" button disappears

- **Where:** `frontend/src/components/FullTextStatus.tsx`: a failed attach sets
  `error`, and the error branch (line 70) offers only "Retry", which retries the
  *download*; the Attach PDF button is rendered only in the "abstract only" branch
  (line 97).
- **Intended behavior:** for a paper without an open-access PDF, the documented remedy
  is "Attach PDF" (README, INSTALL.md); a rejected file should leave that option.
- **Found by:** review G5 (probe test), confirmed by code reading. **Detected by the
  initial suite:** no.

## BUG-8 (low): "Search OpenAlex instead" appears for any error, and searches the current input

- **Where:** `frontend/src/pages/SearchPage.tsx:187–205` shows the button whenever an
  error is displayed while the source menu says arXiv and the box has text; the error
  slot is shared with "Read" failures, and the button runs `input`, not the failed query.
- **Intended behavior:** README ties the button to a failed arXiv search ("runs the same
  query on OpenAlex").
- **Found by:** review G4, confirmed by code reading. **Detected by the initial suite:** no.

## Design questions raised by the review (not counted as bugs)

- **PDF link precedence:** `PaperCard` links "PDF ↗" to `pdf_url` before the stored copy,
  so after a failed download plus a manual attach the card still links to the publisher
  URL that failed. A test (`PaperCard.test.tsx` "prefers the open-access PDF link over
  the stored copy") locks this in. Reviewers G4 and G5 disagree on whether it is a bug.
- **Title from PDF properties:** a title stored in the PDF's properties wins even when it
  does not appear on the page (`pdf.py:184–185`), unlike arXiv and model titles, which
  must appear on the page (review G1).
- **Abstract-only summaries and F4:** when no PDF can be obtained, summaries use the
  abstract and are labelled "abstract only" (documented in README). Under a strict
  reading of F4 ("not just title/metadata") this fallback could be questioned (review G3).
