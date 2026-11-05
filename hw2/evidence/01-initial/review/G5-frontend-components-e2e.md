# Review G5: frontend component and end-to-end tests (reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the rubric in
`tools/review-rubric.md` given inline. Scope: frontend/src/components/*.test.tsx,
frontend/e2e/*, playwright.config.ts, backend/tests/support/e2e_server.py. 80 tool
calls, about 29 minutes. Mutations were run against a scratch copy of
`frontend/src` (removed afterwards); Playwright was not run, as instructed. The content is the reviewer's; the HTML bullet
lists in its table cells were flattened into sentences for Markdown.

---

## Review of the component unit tests and the e2e suite

**Result:** 84 tests reviewed (70 unit, 14 e2e). 68 are OK, 11 are WEAK, 4 are BRITTLE, 1 is FLAKY, and none are WRONG or REDUNDANT. I found two likely application bugs (section 4).

**How I checked:**
- **Unit tests:** all 70 pass (`npx vitest run src/components`, no act() warnings).
- **Playwright:** not run, as instructed. The last recorded run in `frontend/test-results/.last-run.json` says "passed".
- **Evidence for WEAK and missing-test claims:** I mutated a copy of `frontend/src` in the session scratchpad, one change at a time, and ran the whole 148-test frontend suite against each. "Survives" below means every test still passed with the bug in place.
- **Repo state:** no repo file was created, edited or deleted. The scratch copy has been removed.

All paths are relative to `/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/`.

## 1. Counts

No file uses `it.each`/`test.each` (and none uses `.skip` or `.only`).

| File | Tests | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|
| frontend/src/components/ChatPanel.test.tsx | 12 | 10 | 2 | 0 | 0 | 0 | 0 |
| frontend/src/components/SummaryPanel.test.tsx | 11 | 10 | 1 | 0 | 0 | 0 | 0 |
| frontend/src/components/UploadBox.test.tsx | 7 | 6 | 0 | 0 | 0 | 1 | 0 |
| frontend/src/components/EditPaperForm.test.tsx | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/FullTextStatus.test.tsx | 8 | 7 | 1 | 0 | 0 | 0 | 0 |
| frontend/src/components/SectionsPanel.test.tsx | 10 | 8 | 0 | 0 | 0 | 2 | 0 |
| frontend/src/components/Markdown.test.tsx (5 Markdown + 2 RichText) | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/components/PaperCard.test.tsx | 8 | 6 | 1 | 0 | 0 | 1 | 0 |
| **Unit total** | **70** | **61** | **5** | 0 | 0 | **4** | 0 |
| frontend/e2e/search-and-library.spec.ts | 4 | 3 | 1 | 0 | 0 | 0 | 0 |
| frontend/e2e/reader.spec.ts | 3 | 1 | 2 | 0 | 0 | 0 | 0 |
| frontend/e2e/upload-summary-chat.spec.ts | 7 | 3 | 3 | 0 | 0 | 0 | 1 |
| **E2e total** | **14** | **7** | **6** | 0 | 0 | 0 | **1** |

The support and helper files (`e2e/support/*`, `playwright.config.ts`, `backend/tests/support/e2e_server.py`, `src/test/*`) contain no tests. Notes on them follow the findings table.

## 2. Findings

| Test (file > name) | Category | Reason (lines) | How to fix |
|---|---|---|---|
| ChatPanel.test.tsx > asks a typed question with Enter and streams the answer | WEAK | All events are sent and the stream is closed (74-75) before the next assertion (77-79), so the live answer is never checked, though README F5 says "Answers stream in". A ChatPanel that shows "Reading the paper…" until `done` and never renders `stream.text` (ChatPanel.tsx 127) passes; that mutation survives. | Send one `text` event and assert the 2nd bubble shows it while the button still reads "Answering…". Then send `done`. |
| ChatPanel.test.tsx > is disabled with an explanation when the LLM is unavailable | WEAK | The test passes in a hint (172) but asserts only the generic heading (174). Dropping the hint from ChatPanel's notice survives. This panel is the only place the reader shows the hint by default: the Sections tab has no notice. INSTALL.md 98-101 says the reader "shows what is missing". | Also assert the hint text, e.g. `getByText(/was not found/)`. |
| SummaryPanel.test.tsx > tells the user when a long paper was cut off | WEAK | Only `truncated: true` is tested (125). No test asserts the note is absent when `truncated: false`; the streaming test sends `false` at 52 but never checks. So showing the note for every summary (`stream.context &&` instead of `stream.context?.truncated &&`, SummaryPanel.tsx 46) survives. | Add the negative case: after `truncated: false`, `queryByText(/very long/)` is null. |
| FullTextStatus.test.tsx > attaches a PDF the user has | WEAK | The file goes straight into the hidden `<input type=file>` (70); "Attach PDF" is never clicked. A button not wired to the picker (FullTextStatus.tsx 60) survives the whole suite, and no e2e test attaches a PDF. | Click "Attach PDF" and spy on the input's `click()`, as UploadBox.test 19-27 does. Then upload. |
| PaperCard.test.tsx > calls back instead of navigating when the title opens the reader | WEAK | Line 68 cannot fail. In jsdom, clicking an `href="#"` link without `preventDefault` leaves `location.hash === ""`; only `href` changes, to `…/#` (verified). Removing `e.preventDefault()` (PaperCard.tsx 59-62) passes this whole file. Only SearchPage.test "opens a result by clicking its title" catches it. | `expect(fireEvent.click(link)).toBe(false)`, or assert no `hashchange` fired / `href` does not end in `#`. |
| PaperCard.test.tsx > toggles the full abstract | BRITTLE | All three assertions are the CSS class `clamped` (37, 40, 42). No requirement names it, and the full abstract is in the DOM either way. A correct restyle breaks the test. | Add `aria-expanded` to the toggle and assert that plus the button label. Leave the visual clamp to e2e. |
| SectionsPanel.test.tsx > lists the sections with their pages | BRITTLE | Line 34 asserts the styling class `level-2`. Subsection indentation is not documented, so a nested `<ol>` or `aria-level` refactor breaks the test. Lines 27-33 are fine. | Drop line 34, or expose the level semantically and assert that. |
| SectionsPanel.test.tsx > highlights the section being read | BRITTLE | README says "The section you are reading is highlighted"; the test checks this only through the class name `active` (60-62). | Mark the active item with `aria-current` and assert it. |
| UploadBox.test.tsx > uploads a PDF dropped onto it | BRITTLE | Finds the drop zone with `.closest('.upload-box')` (87), asserts the styling class `dragging` (90, 94), and never checks which file was sent. | Query the drop zone by role/label and drop the class checks. Assert `form.get('file').name === 'dropped.pdf'`. |
| e2e/search-and-library.spec.ts > filter the library and remove a paper | WEAK | Removal is checked only in page state (51-55). LibraryPage filters removed ids out of every later list response (LibraryPage.tsx 11-12, 21, 36), so even the re-list after clearing the filter cannot show whether the server deleted DPR. A DELETE that returns 204 without deleting passes. | After Remove, `page.reload()` (or `request.get('/api/papers')`) and assert only RAG remains. |
| e2e/reader.spec.ts > open a search result without saving it, ask about it, then save it | WEAK | Line 33 ("the conversation was kept") counts the bubbles ChatPanel loaded at `goto(readerUrl)` (28), before Save; ChatPanel does not refetch after saving, so a save that lost the chat passes, though REQUIREMENTS.md 80 says saving "keeps its chat". Also order-dependent: `emptyLibrary` deletes only library papers, so the unsaved RAG paper and Q&A left by "the model menu…" persist, and the 2nd run of `--repeat-each` can see 4 bubbles. Lines 18 and 32 assert the class `active`. | Reload after Save and assert 2 bubbles. Reset unsaved papers between tests. |
| e2e/reader.spec.ts > the model menu changes the model that answers | WEAK | Only proves the browser sent `model: 'haiku'` (55). The fake CLI ignores `--model` and always reports `claude-fake-1` (fake_claude.py 43, 137), so a backend that ignored the chosen model passes. The menu is found by CSS (`.model-select select`, 51), though it is labelled "Model". | Make the fake report the `--model` it received (e.g. `claude-fake-haiku`) and assert the provenance. Use `getByLabel('Model')`. |
| e2e/upload-summary-chat.spec.ts > upload a PDF: its metadata is extracted and the PDF is shown | WEAK | Authors and year are substring checks on the whole header (19-20); the abstract is a prefix regex (32). An extra parsed "author" (e.g. the affiliation line) or an abstract running into the introduction passes. Exact values are checked only in backend tests. `.react-pdf__Page canvas` (23) ties the test to react-pdf internals. | Assert exact author text and the full abstract. Find the canvas without the library's class name. |
| e2e/upload-summary-chat.spec.ts > ask questions about the uploaded paper, with follow-ups | FLAKY | Line 66 can be satisfied by streamed, not-yet-saved text, and line 68 then reloads. The backend saves only after the CLI's `result` line (assistant.py 98-102), and Starlette cancels the response on disconnect, so a reload in that window drops Q2 and line 69 sees 2 bubbles, not 4. Low probability, higher on a loaded machine. The Clear at 71-73 is also checked only in page state. | Before reloading, wait for `log.getByText('claude-fake-1 via Claude Code')` to have count 2. Reload after Clear too. |
| e2e/upload-summary-chat.spec.ts > a failed answer is reported and nothing is saved | WEAK | After the reload, line 86 (`.chat-log` count 0) holds at once: `.chat-log` renders only after history loads (ChatPanel.tsx 107), and the check runs right after the h1 appears, typically before GET /chat returns. A saved failed question would usually go unnoticed. | Wait for the GET /chat response (`waitForResponse` set up before the reload), or `request.get('/api/papers/{id}/chat')` and expect `[]`. |
| e2e/upload-summary-chat.spec.ts > summarize the sections and jump to one | WEAK | The jump is verified only by "Page 2 of 2" (97). 2 Method, 3 Experiments and 4 Conclusion are all on page 2 (backend/tests/support/pdfs.py 32-40), so a jump that ignores the in-page `top` (PdfViewer.tsx 57-63, 152-154) or lands on the wrong section passes. PdfViewer has no other tests: the PaperPage tests mock it. | Assert the target heading is near the top of the viewer (text-layer bounding box), or that it becomes the highlighted section. |

### Notes on support and helper files

- **`emptyLibrary` (e2e/support/app.ts 30-34):** it only deletes library papers, because GET /api/papers lists `in_library` rows only. Unsaved papers and their chats leak between tests; this causes the order dependence above.
- **`e2e_server.py`:** the setup is sound. It scrubs env vars, disables the repo `.env`, uses a temp DATA_DIR, runs the fake APIs on an ephemeral port, and uses the fake CLI. One caveat: the canned arXiv entry's PDF link is the real `http://arxiv.org/pdf/1706.03762v7` (tests/support/upstream.py 133). Any future test that opens that result would download over the real network.
- **`fetchMock.ts` (95-98):** unregistered requests get a silent 501 and are logged in `unhandled`, but nothing asserts that list is empty. Fix: register mocks in a module-level list and fail in an `afterEach` if any request was unhandled.
- **CSS-class locators:** the `bubbles()` helper (`.chat-log .bubble`, ChatPanel.test.tsx 29-31) and e2e locators such as `.reader-head`, `.panel`, `.chat-log` and `.model-select` break on a class rename. If the classes changed, `bubbles()` would return `[]`, and the `toEqual([])` at line 149 would pass vacuously.
- **Fixed port 8765:** `serve.mjs` checks the port and fails fast, so this is acceptable.

## 3. Missing tests

Each of the following either survives all 148 frontend unit tests (shown by mutation) or is never exercised.

- **F5 chat:** new answers should be added below the earlier conversation (replacing the history with only the new pair, ChatPanel.tsx 62, also passes the e2e tests); pressing Enter while an answer streams must not send a second question (the guard at 56); a failed Clear should show the error and keep the conversation; "Clear conversation" should be disabled while an answer streams.
- **Sections (REQUIREMENTS.md 80; README "Sections"):** the outline should reload once the paper gains a PDF, after an attach or a finished download (SectionsPanel.tsx 33); the "furthest down" rule for two-column papers, and the last section at the end of the document (54-64); no test checks that the highlight tracks scrolling in the real viewer.
- **Attach PDF / download (README 59-64, INSTALL.md 349):** "Attach PDF" should open the picker (see the FullTextStatus finding); attaching another file after a refusal (see bug 1); no e2e test opens a search result with an open-access PDF, because the fake OpenAlex works have none.
- **PdfViewer (README "Center"), no tests at all:** zoom in/out, Fit width, and keeping the reading position when zooming; the "Open PDF ↗" link (`/api/papers/{id}/pdf` in a new tab); the load-failure message "The PDF could not be displayed."; PaperPage's ErrorBoundary fallback; rendering only nearby pages on a long PDF.
- **F4 (minor):** a paper whose full text was never attempted (`full_text_status` null) should show plain "No summary yet."
- **F3 (minor):** a drop during an upload should be ignored, and the same file should be selectable again after a backend refusal.

The backend tests already cover, server-side: restart persistence, full text reaching the model (BODY_MARKER), save keeping the chat, a failed answer saving nothing, and delete.

## 4. Possible application bugs

1. **A refused PDF attachment strands the user.** After the backend rejects an attached file (e.g. 415 "The file is not a PDF."), FullTextStatus switches to its error branch (lines 70-79), which shows only "Retry" (`fetchText(true)`, a download retry); the "Attach PDF" button (rendered only at 97) disappears. Confirmed with a scratch probe test. For an abstract-only paper with no PDF link, the documented remedy is "click Attach PDF" (INSTALL.md 349; README 59-64). The test "shows why an attached file was refused" checks only the message.
2. **The card's "PDF ↗" link can point at a link known to fail** (lower confidence; may be a design choice). PaperCard.tsx 47 uses `paper.pdf_url ?? localPdfHref`. After a failed download plus a manual attach, `pdf_url` still holds the remote link (`attach_pdf` does not touch it), so "PDF ↗" points at the link that failed instead of the stored copy. "prefers the open-access PDF link over the stored copy" (PaperCard.test.tsx 71-77) locks this in.
