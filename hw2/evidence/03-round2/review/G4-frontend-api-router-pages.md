# Final review G4: frontend API client, router, app, and page tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the prompt in
`prompts/G4.txt` (the initial review's prompt plus useLlmStream.test.ts, the new helpers,
and one sentence on expected failures). Suite: tag `hw2-round2`. 55 tool calls, about
354k tokens, 29 minutes.

---

## 1. Counts

All 97 cases pass today: 94 pass and 3 are expected failures. I ran the seven files four more times in shuffled order (seeds 7, 1234, 98765, 4242) with no change, so I found no order dependence. I changed no files.

| File | Tests (cases) | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|
| api.test.ts | 19 (20: it.each "uploads/attaches a PDF as multipart form data" has 2 cases) | 16 | 2 | 0 | 0 | 1 | 0 |
| router.test.ts | 3 (11: it.each `parseHash` has 9 cases) | 2 | 0 | 0 | 0 | 1 | 0 |
| App.test.tsx | 7 (8: it.each "marks the tab…" has 2 cases; 1 expected failure) | 5 | 2 | 0 | 0 | 0 | 0 |
| pages/SearchPage.test.tsx | 21 (21; 2 expected failures) | 19 | 1 | 0 | 0 | 0 | 1 |
| pages/LibraryPage.test.tsx | 13 (13) | 12 | 0 | 0 | 0 | 1 | 0 |
| pages/PaperPage.test.tsx | 21 (22: it.each "says how long an unsaved paper is kept" has 2 cases) | 20 | 1 | 0 | 0 | 0 | 0 |
| useLlmStream.test.ts | 2 (2) | 1 | 1 | 0 | 0 | 0 | 0 |
| **Total** | **86 (97)** | **75** | **7** | **0** | **0** | **3** | **1** |

**The 3 expected failures are all OK.** Each one checks intended behavior, every step before its check passes today, and each check fails only on the bug it names:
- **"settles after opening a paper, without React errors"**: the oracle is React's own loop error. The check watches a real 200 ms window. That is sound here, because the loop never stops while the bug exists, and the chat request is answered in the same render as the outline the steps wait for.
- **"runs the query that failed on OpenAlex even after the search box was edited"**: matches README:19, "runs the same query on OpenAlex".
- **"offers OpenAlex only after an arXiv search failed"**: also matches README:19.

## 2. Findings

| file > test name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| api.test.ts > requests > saves a search result as JSON | BRITTLE | Line 110 compares `init.headers` with the exact plain object `{ 'Content-Type': 'application/json' }`. The backend needs the Content-Type, but not this form. Passing a `Headers` instance or adding an `Accept` header would fail the test with no change on the wire. Line 127 of the same file already uses the robust form. | `expect(new Headers(call.init?.headers).get('Content-Type')).toBe('application/json')` |
| api.test.ts > requests > edits metadata with PATCH | WEAK | Line 135 checks only the body. The fetch mock parses any string body as JSON (fetchMock.ts:99-108), but FastAPI does not. A string body sent without `Content-Type: application/json` goes out as text/plain, which fastapi/routing.py:449-462 (installed 0.142.2) keeps as raw bytes, so the backend answers 422. **Bug that slips through:** `updatePaper` losing its header (api.ts:149). Only the e2e test "fix the extracted metadata" would catch it. | Also assert the Content-Type, as in the previous row. |
| api.test.ts > streamed answers > posts a question with the chosen model | WEAK | Same gap at line 188 (api.ts:177). A question sent as text/plain gets 422 from the backend, and this test still passes. | Assert the `Content-Type: application/json` header. |
| router.test.ts > paperKey > falls back to the URL, then the DOI, then the title | BRITTLE | Lines 28-30 pin the order url → doi → title and the exact `source:value` strings. No requirement or comment states that order; types.ts:140 says only "Stable identity". What matters is that results without an external id don't collide, which the de-duplication in `appendUnique` and the React keys rely on. Preferring the DOI over the URL would be a correct change, yet line 28 fails because the fixture also has a DOI. | Assert the property instead. Two "(untitled)" results with no external id that differ only in url (no doi), or only in doi (no url), get different keys, and an identical copy gets the same key. |
| App.test.tsx > marks the tab an open paper belongs to once it has loaded (it.each, 2 cases) | WEAK | The check "not claimed while the paper loads" (line 83) can't catch the stale-state bug that App.tsx:11-14 guards against. No paper was open before, so `paperInLibrary` is null whatever line 14 does. **Bug that slips through:** dropping `paperInLibrary?.id === route.id` from App.tsx:14 (a regression an earlier code review fixed). Going from a library paper to another paper would then keep "Library" marked while the new paper loads, and the test still passes. It is also BRITTLE: it reads the mark only from the CSS class `active` (`markedTabs`, line 37). "starts on the search page" (line 47) and "switches pages with the tabs" (line 59) use the same helper, but only for a secondary assertion. | Open a library paper first (`#/paper/3`, wait for "Library"). Then go to `#/paper/4` with a deferred load, expect no marked tab, then "Search" once it loads. Read the mark from `aria-current="page"` (add it in App.tsx) or from the computed background via `useAppStylesheet()`, as e2e/support/app.ts:66-76 does. |
| App.test.tsx > goes back to the page the paper was opened from | WEAK | `withPaper(backend())` opens an unsaved paper (line 121; the default `inLibrary=false` is at line 24). An unsaved paper's own tab is Search, so landing on `#/search` (line 131) doesn't prove that Back followed the browser history (PaperPage.tsx:116-119, router.ts:18-20). **Bug that slips through:** `back()` sending users to the paper's own tab (`in_library ? '#/library' : '#/search'`). It passes this test, and also PaperPage's "goes back to the library when there is no earlier page", which uses a library paper. | Use a library paper (`withPaper(backend(), true)`) opened from `#/search` and expect `#/search`. Optionally assert that `history.length` didn't grow. |
| SearchPage.test.tsx > stops offering more after page 100, the last page the backend serves | FLAKY | The test makes 99 clicks on a growing list against a fixed 20 s timeout (line 231). I measured it on an 8-core M1 Pro: 3.8 s with only the seven reviewed files, and 6.2-14.1 s under `npm test` (all 16 files in parallel, which is what `make test-frontend` runs). That is up to 70% of the budget, so a slower or busier CI machine can time out with no bug present. | Start near the cap. Restore a search at page 99 through the state the page reloads (sessionStorage `search-state`, SearchPage.tsx:37-46), check that "Load more" is offered, click once, then expect a page-100 request and no "Load more". At minimum, raise the timeout well above the measured time. |
| SearchPage.test.tsx > keeps the last search when the user comes back to the page | WEAK | It searches the default source, OpenAlex, with total 1 (line 322), so it can't tell whether the source and paging are restored ("Keep the last search across tab switches and page refreshes", SearchPage.tsx:37). **Bug that slips through:** `useState<SearchSource>('openalex')` instead of `state.source` (SearchPage.tsx:57). After returning, the menu would show OpenAlex next to arXiv results and the next search would go to the wrong source, yet the test passes. | Search arXiv with total greater than the result count, unmount, render again. Assert the menu shows arXiv, the count says "… from arXiv", and "Load more" asks arXiv for page 2. |
| LibraryPage.test.tsx > filters on the server once the user stops typing for 200 ms | BRITTLE | Lines 88-97 pin the debounce at exactly 200 ms: nothing at 199 ms, a request at 200 ms. No requirement or doc gives that value; LibraryPage.tsx:14 says only "Debounced". Retuning it to 150 or 300 ms keeps the behavior correct but breaks the test. | Right after typing, assert no new request has gone out. Then advance by a generous amount (e.g. 1 s) and assert exactly `[null, 'bert']` plus the filtered list. Checking that no request goes out for a prefix keeps the debounce covered. |
| PaperPage.test.tsx > switches between sections, summary, and details | WEAK | Lines 172-176 check only that each tab's content appears, never that the previous panel goes away. **Bug that slips through:** all three panels stay rendered whatever tab is selected (for example, kept mounted to avoid refetching the outline, without being hidden). The test still passes. | After each click, also assert the previous panel's content is gone: no "1 Introduction" button on Summary, no "Generate summary" on Details. Also check that `aria-selected` moved. |
| useLlmStream.test.ts > stops a running request when a new one starts, and ignores what the old one still sends | WEAK | It never checks `error`. **Bug that slips through:** dropping `!ctrl.signal.aborted` at useLlmStream.ts:53. The old request's end would then set "The response ended unexpectedly…" while the new request runs, and lines 42-46 still pass. The rejection guard at useLlmStream.ts:57 is never exercised, because `controlledRequest().open` resolves on abort instead of rejecting, as fetch does. Today's UI prevents overlapping requests, so this affects only the hook's own contract. | Add `expect(result.current.error).toBeNull()` after `first.finish()`. Add a case where the old request rejects with an AbortError when its signal fires, and assert `error` stays null. |

## 3. Missing tests

None of these is exercised by any unit or e2e test; I checked by grepping src/ and e2e/.

**F1 Search**
- **Out-of-order answers:** an older search's answer arriving after a newer one must be dropped and must not clear "Searching…" (SearchPage.tsx:60-61, 111-134). The library has this test; the search page does not.
- **Saved-marks lookup failure:** if GET /api/papers/keys fails, search and save must still work ("Non-fatal", SearchPage.tsx:75-77).
- **Unknown total:** `total: null` is allowed (types.ts:130, and both search clients can return it). The count should then omit "of N" and no "Load more" should appear (SearchPage.tsx:149-153, 225-227).
- **Opening guard:** while a result opens, the Read buttons are disabled and show "Opening…", and a second click sends no second POST /api/papers/open (SearchPage.tsx:84-87, 242-245).

**F2 Library**
- **No PDF at all:** a paper with neither an open-access PDF nor a stored copy should show no "PDF ↗" link (LibraryPage.tsx:89). Every card in the PDF-link test has `has_pdf: true`, so a dead `/api/papers/{id}/pdf` link would pass.

**Reader (added requirements, README:25-57)**
- **Header buttons:** an unsaved paper's header has no Remove, and Remove appears after saving (README:42-43).
- **Saved date:** after "Save to library", the Details tab should show the save time (README:34-36). This is currently wrong; see section 4.
- **Reader without /api/config:** when that request fails, the model menu should be hidden, requests should go out without a model, and Details should say "after a while" (PaperPage.tsx:58-60, 236-238; ModelSelect.tsx:13). A stale config answer should be ignored (PaperPage.tsx:54).
- **Model choice without localStorage:** when localStorage throws, `useModelChoice` should fall back to the default and keep the choice for the page (useModelChoice.ts:6-12, 21-27).

**Navigation**
- **Switching papers:** moving from one open paper to another must not mark the previous paper's tab (App.tsx:11-14); see the "marks the tab" row in section 2.
- **Back after reload or back/forward:** Back must use the depth stored in `history.state` (router.ts:18-24, 48-55). For example, Search → paper → reload → Back should return to Search.
- **Rewriting hashes at runtime:** an unknown or non-canonical hash entered while the app runs (e.g. `#/settings`, `#/paper/4/`) should be rewritten (router.ts:41-45). Only the initial-load case is tested.
- **Health polling stops:** the UI should stop polling once the backend answers (README:239, "polls it until the backend answers"). The App test asserts only "at least 2 calls" (line 146); advancing time again and asserting the count stays the same would cover it.

**API and streaming**
- **JSON Content-Type for the other requests:** `openPaper`, `updatePaper`, `streamAnswer` and `summarizeOutline` (api.ts:97-99, 113-115, 147-150, 175-178) are never checked for the header; only `savePaper` is. The mock's lenient JSON parsing hides a missing header, so only e2e would notice.
- **Untested error paths:** a 200 stream with no body, "The response has no body." (api.ts:186); a 422 detail list with no usable `msg`; and a JSON error body without `detail` (api.ts:31-55).

## 4. Possible application bugs

1. **New: after "Save to library" in the reader, the Details tab shows the wrong "Saved" date.**
   - PaperPage.tsx:98 copies only `in_library` from the POST /api/papers/{id}/save response, so `saved_at` stays null.
   - The Details line (PaperPage.tsx:233-234, `(paper.in_library && paper.saved_at) || paper.created_at`) then prints "Saved" with the first-opened time. This lasts until the page is reloaded.
   - The backend does set and return `saved_at` (backend/app/routers/papers.py:286-294).
   - README:34-36 says Details shows "when the paper was saved or first opened". No test opens Details after saving.
2. **The three bugs named by the expected-failure tests are real**, and I agree with all three:
   - App.tsx:73 passes a new `onLibraryState` on every render, and the effect at PaperPage.tsx:41-43 depends on it, which causes the render loop.
   - "Search OpenAlex instead" runs whatever is in the search box (SearchPage.tsx:198), not the query that failed.
   - The button is offered whenever an error shows while arXiv is selected (SearchPage.tsx:190). It also appears after a failed "Read" (which sets the same error, SearchPage.tsx:91-92) following an arXiv search, where clicking it reruns the search instead of the open. The existing expected-failure test covers only the failed-OpenAlex-search case.
3. **No test asserts behavior that contradicts the documented intent.**
