# Final review G5: frontend component and end-to-end tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the prompt in
`prompts/G5.txt` (the initial review's prompt plus PdfViewer.test.tsx, the new helpers,
and one sentence on expected failures). Suite: tag `hw2-round2`. 60 tool calls, about
355k tokens, 25 minutes.

---

Review of the component tests, e2e specs and their helpers. Five of 99 tests are non-OK: 1 WRONG, 2 WEAK, 2 BRITTLE. No file was changed.

`npx vitest run src/components` passes (9 files, 92 passed, 1 expected failure = 93 cases). I did not run Playwright; `frontend/test-results/.last-run.json` says the last run passed.

All paths are under `/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/`.

## 1. Counts

| File | Tests | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|
| frontend/src/components/ChatPanel.test.tsx | 16 | 16 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/SummaryPanel.test.tsx | 11 (one `it.each` → 2 cases; 12 cases) | 11 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/UploadBox.test.tsx | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/EditPaperForm.test.tsx | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/FullTextStatus.test.tsx | 9 (incl. 1 `itFailsUntilFixed`) | 9 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/SectionsPanel.test.tsx | 12 (one `it.each` → 9 cases; 20 cases) | 11 | 0 | 0 | 0 | 1 | 0 |
| frontend/src/components/Markdown.test.tsx | 7 (5 Markdown, 2 RichText) | 7 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/PaperCard.test.tsx | 9 | 8 | 0 | 1 | 0 | 0 | 0 |
| frontend/src/components/PdfViewer.test.tsx | 4 | 2 | 1 | 0 | 0 | 1 | 0 |
| frontend/e2e/search-and-library.spec.ts | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| frontend/e2e/reader.spec.ts | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| frontend/e2e/upload-summary-chat.spec.ts | 8 | 7 | 1 | 0 | 0 | 0 | 0 |
| e2e/support/*, playwright.config.ts, backend/tests/support/e2e_server.py, src/test/*, vitest.config.ts | no tests (reviewed below) | | | | | | |
| **Total** | **99** (84 Vitest = 93 cases; 15 Playwright) | **94** | **2** | **1** | **0** | **2** | **0** |

## 2. Findings

| file > test name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/PaperCard.test.tsx > links the open-access PDF when the paper has one, even with a stored copy, and else the stored copy | WRONG | Lines 96-97 expect the remote `pdf_url` to win over a stored copy. That pins the code `paper.pdf_url ?? localPdfHref` (PaperCard.tsx:47), not the intent:<br>• The prop's comment says "Link to a locally stored copy of the PDF, when the library has one" (PaperCard.tsx:35).<br>• When a PDF cannot be downloaded, the documented fix is to attach one (INSTALL.md:349, README.md:59-64).<br>• Attaching never updates `pdf_url` (backend/app/services/fulltext.py:106-131).<br>So for exactly those papers, "PDF ↗" in the Library and the Details tab links to the link that failed (private address, HTTP error, login page), although the attached copy exists. | Expect the stored copy whenever `localPdfHref` is given, and the open-access link only when there is no stored copy. Until the app changes, make that case an `itFailsUntilFixed`. frontend/src/pages/LibraryPage.test.tsx:62 (outside this review) pins the same rule. |
| /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/SectionsPanel.test.tsx > indents subsections under their section | BRITTLE | Lines 10-13 and 57-66 read each `<li>`'s `margin-left` and compare the bare `parseFloat` numbers (jsdom keeps `0.9rem`, index.css:893-895). No requirement or doc asks for indentation; README.md:29-31 asks only for sections with page numbers.<br>• Indenting with `padding-left`, on the button, or with a nested `<ol>` looks the same but fails the test.<br>• Giving every item a px margin makes it compare 4 (px) > 0.9 (rem) and fail, although the subsection is still further right. | Drop it. Or check it in Playwright by comparing the rendered x of the "2.1 Retriever" and "2 Method" titles. Better: have the app expose the level (nested list or `aria-level`) and assert that. |
| /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/PdfViewer.test.tsx > shows the pages, a page counter, and a link to open the PDF itself | BRITTLE | Line 44 expects "600 px wide". That is the placeholder `useState(600)` (PdfViewer.tsx:28), which never changes because the ResizeObserver stub (line 34) never fires. Line 45 expects page 3 not drawn. That is only the initial set `{1, 2}` (PdfViewer.tsx:31), because the IntersectionObserver stub (line 35) never reports. Measuring the width on mount, or a different initial set, breaks the test with no change in behavior. Meanwhile "only pages near the view are drawn" (line 43) is never actually tested. | Keep the page-counter and Open PDF checks, and match `/^Page 1 drawn/` without the width. To test lazy rendering, capture the IntersectionObserver callback in the stub, report pages 1-2 in view and 3 out, then 3 in and 1 out, and assert which pages are drawn. |
| /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/PdfViewer.test.tsx > zooms in and out in steps, and Fit width goes back to the panel width | WEAK | The panel width is never reported (stub, line 34), so 750/600/450 px (lines 61-70) only show that width = 600 × zoom. A broken fit-to-width would still pass: observer not attached, GAP miscounted, or resizes ignored (PdfViewer.tsx:65-78). No e2e test compares the page width with the panel either. The numbers also depend on the 600 placeholder. | Make the stub call back after giving the scroller a known `clientWidth`: 824 → 800 px at 100%, 1000 px at 125%. Then report 624 and check that Fit width gives 600 px. |
| /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/e2e/upload-summary-chat.spec.ts > files that are not PDFs are refused | WEAK | Line 185 (`0 papers`) is the count the page loaded before the uploads. LibraryPage does not reload after a failed upload, so it would still say 0 if the backend had stored the paper before refusing it. Line 176 does not check that notes.txt was never sent. | After the refusal, call `page.reload()` or `request.get('/api/papers')` and expect `[]`, as search-and-library.spec.ts:59 does. Watch `page.on('request')` during the .txt upload and expect no POST /api/papers/upload. |

**Smaller issues in tests counted OK:**
- **SectionsPanel.test.tsx:98, test names:** in `'(outline %#, position %f)'`, `%f` takes the first row value (the Outline object). So all 9 cases are named "position NaN" in the run output, and a failing case won't show its position. Use object rows and `$position`.
- **SectionsPanel.test.tsx:27-32, highlight check:** it reads the `active` CSS class. Reading the stylesheet's computed background (as UploadBox and the e2e `isHighlighted` do) would survive a class rename, and so would an `aria-current` in the app.
- **SectionsPanel.test.tsx:97, two-column case:** `[TWO_COLUMNS, Infinity, ['3 Results']]` is commented as testing the page-null rule. Its expected value also depends on the two-column rule (see section 4). To isolate the page-null rule, use `outline()` plus one section with no page, and expect "2.1 Retriever".
- **SectionsPanel.test.tsx:83 and EditPaperForm.test.tsx:69, vacuous checks:** the "not called" and "no request" assertions can never fail, because neither test clicks or submits. Click the disabled button, or press Enter in the title field, first.
- **UploadBox.test.tsx:33 and FullTextStatus.test.tsx:82, `accept` attribute:** both assert the exact string `'application/pdf,.pdf'`. `.pdf` or `application/pdf` alone would work the same.
- **Class-based locators:** ChatPanel.test.tsx:29-31 (`bubbles()`) and the e2e locators `.chat-log`, `.chat-log .bubble`, `.reader-head`, `.panel`, `.pdf-scroll` depend on class names. upload-summary-chat.spec.ts:97 and :100 treat "conversation cleared" as "`.chat-log` is absent". A labelled `role="log"` in the app would make these stable.
- **e2e/support/app.ts:84-96, throwing poll helpers:** `textHeightInPdfView` and `offsetInPdfView` throw when `boundingBox()` returns null. Playwright's `expect.poll` evaluates the callback outside its retry `try` (`invokePollMatcher` in node_modules/playwright/lib/matchers/expect.js). So a span that is attached but not yet laid out fails the jump and zoom tests at once instead of being polled again. Return `NaN` instead of throwing.

**Test infrastructure (no tests of its own):**
- **e2e launcher:** `e2e_server.py`, `serve.mjs` and `playwright.config.ts` are sound.
  - Settings are isolated before the app reads them.
  - OpenAlex, arXiv and the `claude` CLI are all faked. The fake arXiv PDF link (192.0.2.10, a documentation-only address) is refused without connecting, so nothing reaches the internet.
  - The reset route is safe: paper ids are never reused (`sqlite_autoincrement`, models.py:50), and `store_pdf` recreates the deleted PDF folder (fulltext.py:90-91).
  - The reset does not clear arXiv's throttle/cooldown or the Claude Code status cache. Today this cannot matter: the fake returns only 200 or 500, and a 500 starts no cooldown.
  - The default port 8765 is checked before the build and can be changed with `E2E_PORT`, so a busy port fails the run clearly, not intermittently.
- **Test helpers:** `setup.ts`, `fetchMock.ts`, `console.ts` and `knownBugs.ts` are sound. Unmocked requests and unexpected console errors fail the test, and `itFailsUntilFixed` accepts only an assertion error from the returned check.
- **The expected-failure test:** FullTextStatus "lets the user attach another file after a refused one" (lines 105-118) is OK. Its steps pass, and its first check fails with an AssertionError for exactly the bug it names.

## 3. Missing tests

1. **Fit width really fits the panel and follows resizes, keeping the reading place** (README.md:38 "Fit width"; PdfViewer.tsx:65). No unit test reports a size, and no e2e test checks page width or resizes the window. A viewer that ignores the panel width passes everything.
2. **Only pages near the view are rendered; far pages are released without the scroll jumping** (README.md:39-40; PdfViewer.tsx:32-34, 86-87). The unit test sees only the initial set. The e2e PDFs have at most 5 pages and nothing checks release.
3. **At the end of the document the last section is highlighted** (README.md:31; PdfViewer.tsx:16-18, 118-121, which report "Infinity" at the end). SectionsPanel tests pass Infinity in directly; no test scrolls the real viewer to the end.
4. **Links inside the PDF:** internal links should scroll to their page and external ones open in a new tab (PdfViewer.tsx:203-205). The page-error message "This page could not be displayed." (line 226) is also untested.
5. **Papers whose PDF has no headings, in the UI** (README.md:32-34 and 272-273). The unit test stops at the explanatory message. Nothing shows that after "Summarize sections" the model-named sections appear, located ones with "p. N" and unlocated ones disabled. The fake CLI already answers this prompt, and `pdfs.unstructured_pdf` provides a PDF without headings for an e2e test.
6. **A successful "Regenerate" replacing the saved summary and its provenance line** (README.md:22, F4; the button's text). Only a failed regeneration is tested, and the e2e test generates once.
7. **`javascript:` and `data:` links in model output stay inert** (README.md:110-114 "Model output loads nothing by itself"; Markdown.tsx:7-8). This relies on react-markdown's default URL sanitizing, and no test guards it. The URL-parse-failure branch (Markdown.tsx:13-15) is also untested.
8. **ChatPanel error paths** (ChatPanel.tsx:65-66, 75):
   - an HTTP error before streaming (422 unknown model, 404 paper gone) should give the question back;
   - a stream that ends without a result is tested only for summaries;
   - Enter during IME composition must not send.
9. **UploadBox recovery** (UploadBox.tsx:24, 32): after a failed upload the picker is reset so the same file can be chosen again; a drop during an upload is ignored.
10. **LLM unavailable, end to end** (INSTALL.md:98-101). Each panel is unit-tested, but no e2e test runs the reader with Claude Code logged out or missing. The fake CLI supports `FAKE_CLAUDE_AUTH=logged-out`, but the e2e server's environment is fixed at startup.

## 4. Possible application bugs

1. **"PDF ↗" links the remote copy even when a stored copy exists** (medium confidence). PaperCard.tsx:47 prefers `pdf_url`, and `attach_pdf` (fulltext.py:106-131) never changes `pdf_url`. So after the documented "Attach PDF" fix (INSTALL.md:349), the Library card and the Details tab still link to the URL that failed: a refused private address, an HTTP 503, or a login page. The prop's own comment (PaperCard.tsx:35) points to linking the stored copy. PaperCard.test.tsx:92-101 and LibraryPage.test.tsx:62 assert the current behavior.
2. **ChatPanel keeps a stale error.** A failed "Clear conversation" sets `loadError` (ChatPanel.tsx:87), and nothing ever clears it (it is set only at lines 39 and 87). A later successful clear or answer leaves "Internal Server Error" on screen until the reader is reopened. The same defect was fixed for the outline panel (docs/DEVLOG.md:480, "A failed outline load left its error on screen … Cleared on success").
3. **FullTextStatus after a refused attachment** (already confirmed and covered by the expected failure). The error box also drops the "Only the abstract is available" explanation, and its "Retry" button calls `fetchText(true)` (FullTextStatus.tsx:69-79): it retries the download, not the attachment that failed.
4. **Two-column papers at the end of the document** (low confidence; a design question). SectionsPanel.tsx:54-64 highlights the heading lowest on the page. On a last page where the final section ("4 Discussion") starts higher in the right column, the left column's earlier section ("3 Results") is highlighted at the end, although line 56 says the end means "the last section". The code's stated rule ("the one starting furthest down") supports the current output, so I did not count the test case as wrong.

Source files cited:
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/PaperCard.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/PdfViewer.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/SectionsPanel.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/ChatPanel.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/FullTextStatus.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/UploadBox.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/components/Markdown.tsx
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/e2e/support/app.ts
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/backend/app/services/fulltext.py
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/backend/app/models.py
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/backend/tests/support/e2e_server.py
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/src/index.css
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/README.md
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/INSTALL.md
- /Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/docs/DEVLOG.md
