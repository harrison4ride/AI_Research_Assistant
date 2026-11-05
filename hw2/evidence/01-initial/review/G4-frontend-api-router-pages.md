# Review G4: frontend api, router, App, and page tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the rubric in
`tools/review-rubric.md` given inline. Scope: api.test.ts, router.test.ts,
App.test.tsx, SearchPage/LibraryPage/PaperPage tests. 64 tool calls, about 26
minutes. Mutations (M1–M7) were injected in memory through a `readFile` hook; no
repository file was edited.

---

Of the 70 tests in the six files (78 cases), 61 are OK, 6 are WEAK, 2 are FLAKY and 1 is WRONG; none are REDUNDANT or BRITTLE. I also found three app bugs. The worst is that the reader re-renders endlessly whenever a paper is open, and the tests can't see it. All 78 cases pass today.

How I checked: I injected mutations (M1–M7) and probe tests in memory only. A `fs.promises.readFile` hook passed through `NODE_OPTIONS` rewrote source text as it was read, and vitest ran with `--no-fsModuleCache`. No repo file was edited. Paths below are relative to `/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant`.

## 1. Counts

| File | Tests | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|
| frontend/src/api.test.ts | 19 | 17 | 2 | 0 | 0 | 0 | 0 |
| frontend/src/router.test.ts | 3 (the `parseHash` `it.each` expands to 9 cases, so 11 cases) | 3 | 0 | 0 | 0 | 0 | 0 |
| frontend/src/App.test.tsx | 5 | 4 | 1 | 0 | 0 | 0 | 0 |
| frontend/src/pages/SearchPage.test.tsx | 18 | 16 | 1 | 0 | 0 | 0 | 1 |
| frontend/src/pages/LibraryPage.test.tsx | 11 | 9 | 1 | 0 | 0 | 0 | 1 |
| frontend/src/pages/PaperPage.test.tsx | 14 | 12 | 1 | 1 | 0 | 0 | 0 |
| **Total** | **70 (78 cases)** | **61** | **6** | **1** | **0** | **0** | **2** |

## 2. Findings

| file > test name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| api.test.ts > requests > uploads a PDF as multipart form data | WEAK | L112-121 only checks that the body is a `FormData` with a `file` entry; it never looks at `init.headers`. The classic bug (a hand-set `Content-Type: multipart/form-data` with no boundary, or `apiFetch` adding a default JSON type) breaks real uploads (F3). With M7 (that header added to `uploadPdf`) all 78 still pass. Only the e2e upload against the real backend would notice. | Also assert that no Content-Type is set, so the browser adds the boundary: `expect(new Headers(api.calls[0].init?.headers).has('content-type')).toBe(false)`. |
| api.test.ts > streamed answers > passes a cancellation through instead of calling it a network error | WEAK | L193-200: the stub always rejects with `AbortError` and ignores `init.signal`. So the test can't tell whether `streamEvents` passes the signal to fetch (api.ts L179). With M6 (`signal` removed from the fetch call) cancellation is broken, contrary to useLlmStream.ts L8-9 "The request is aborted when the component unmounts", and all 78 still pass. | Make the stub honor the signal: `(_, init) => new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(abort)))`. Start `streamSummary`, then call `controller.abort()`, and expect `rejects.toBe(abort)`. Or assert `fetch.mock.calls[0][1].signal === controller.signal`. |
| App.test.tsx > opens a paper in the reader and marks the tab it belongs to | WEAK | L47-60 covers only `in_library: false`. "Search active, Library not" is also what a reader that always highlights Search produces; M3 (`onPaperSearchTab = route.name === 'paper'`) keeps all 78 green. It doesn't check the intent "no tab is claimed while the paper loads" (App.tsx L11-12). It passes despite the render loop in 4A. It also depends on the `active` CSS class, the only signal the app exposes. | Use `it.each` over `in_library` false (Search active) and true (Library active), asserting the other tab is not active. Hold `GET /api/papers/4` with `deferred()` and assert neither tab is active while it waits. Expose `aria-current="page"` on the active tab and assert that instead of the class. After the paper loads, assert `console.error` got no "Maximum update depth" warning. |
| SearchPage.test.tsx > shows each result with title, authors, year, venue, abstract, and links | FLAKY | The result depends on the machine's locale, not on chance. L41 hard-codes "1,234", but SearchPage.tsx L226 formats with `toLocaleString()`. Under `LANG=de_DE.UTF-8` the app correctly shows "1.234" and this test fails (verified). | Build the expected text with `` `Showing 2 of ${(1234).toLocaleString()} results for “transformers” from OpenAlex` ``, or use an explicit locale in the app and assert that. |
| SearchPage.test.tsx > offers OpenAlex when arXiv fails | WEAK | L111-127: the mock answers every non-arXiv request with results (L113-117), and the test never inspects the second request. So README L19 "runs the same query on OpenAlex" is never checked. M5 (`run(state.query, 'openalex', 1)`) keeps all 78 green. It sends `q=''`, because the failed search never set `state.query`, and the real backend answers that with 422. | Add `expect(Object.fromEntries(api.callsTo('GET','/api/search')[1].query)).toEqual({ q: 'rag', source: 'openalex', page: '1', per_page: '10' })`. |
| LibraryPage.test.tsx > links to the stored PDF of a paper that has one | WEAK | L40-46: the only paper with a stored PDF has `pdf_url: null` (L9, from fixtures.ts L27). The test therefore can't tell "link to the stored copy" (PaperCard.tsx L35 comment) from "use `pdf_url` when there is one". The app does the second (PaperCard.tsx L47). An in-memory probe with `has_pdf: true` plus a `pdf_url` got the external URL, not `/api/papers/3/pdf`. | Add a paper with `has_pdf: true` and a non-null `pdf_url`, and expect `/api/papers/{id}/pdf`. That fails today: either fix PaperCard (`localPdfHref ?? paper.pdf_url`), or, if the external link is intended, assert that and correct the comment. |
| LibraryPage.test.tsx > filters on the server as the user types | FLAKY | The "one request for the whole word" assertion (L65) holds only if user-event types all four keys within LibraryPage's real 200 ms debounce (LibraryPage.tsx L17-25). A pause of more than 200 ms between keystrokes (a GC pause or a loaded CI machine) adds a request and fails against a correct app. The odds are low, but it depends on the wall clock. | Use fake timers without `shouldAdvanceTime`, and `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`. Type "bert" and assert no new request. Then run `await act(() => vi.advanceTimersByTimeAsync(200))` and assert `[null, 'bert']` with synchronous queries. |
| PaperPage.test.tsx > says how long an unsaved paper is kept | WEAK | L126-134 uses `cached_paper_days: 7`, which is the documented default (README L54-57, INSTALL L183 "shows this number"). A UI that hard-codes "7 days" instead of reading `/api/config` passes: M4 keeps all 78 green. | Use a non-default value (3 → "after 3 days") and add a case for 1 → "after 1 day". |
| PaperPage.test.tsx > falls back to the default model when the remembered one is gone | WRONG (the inputs make the check meaningless) | L156-161: the default model `opus` is also the first menu option (fixtures.ts L61-65). A controlled `<select>` whose value matches no option shows its first option, so the combobox reads `opus` whether or not `useModelChoice` falls back (useModelChoice.ts L19). M1 (fallback removed) keeps all 78 green. Under M1, `retired-model` is sent and the backend rejects it with 422 (README L83). | Put the default after another option: `llm_models: [sonnet, opus]`, default `opus`. I verified this passes today and fails under M1. Also check the request: Generate summary should send `model=opus`. |

These tests are still rated OK, but each has one assertion tied to a representation detail:
- api.test.ts L109 compares the exact headers object.
- App.test.tsx L23 and L34 rely on the `active` class.
- PaperPage.test.tsx L146 reads the `llm-model` storage key.

M2 (results never marked exhausted) was caught 3 out of 3 times by "stops offering more when a page adds nothing new", so that test is OK.

## 3. Missing tests

I checked the component tests and the e2e specs before listing these.

1. **Back navigation** (router.ts L18-30 and L48-56; PaperPage.tsx L116-119): "← Back" should call `history.back()` when there is an earlier in-app page, and the depth should survive browser back/forward. Only the depth-0 fallback is tested (PaperPage.test.tsx L91-98), and no other suite covers it.
2. **LLM readiness recheck** (INSTALL.md L343; PaperPage.tsx L62-73): the reader rechecks `/api/config` on window focus, at most once every 5 s. Nothing tests it.
3. **Cancelling a streamed summary or answer** (F4/F5; useLlmStream.ts L8-9, L17, L21): the stream should abort on unmount or when a new request starts. Nothing tests it; the api test only fakes the abort (finding 2).
4. **Responses arriving out of order** (F1/F2):
   - SearchPage should drop an older search that answers last (SearchPage.tsx L60-61, L116, L131).
   - LibraryPage should drop a stale filter response, and should not bring back a just-deleted paper through a list request already in flight (LibraryPage.tsx L11-12, L14-21).
5. **Top tab state** (App.tsx L11-16):
   - No tab should be marked while the paper loads.
   - A library paper should mark Library and not Search. The e2e (reader.spec.ts L32) only checks that Library becomes active after saving, not that Search goes inactive.
   - The reader should settle after loading; such a test would catch bug 4A.
6. **Scope of "Search OpenAlex instead"** (README L19): the button should appear only after a failed arXiv search. No test checks it stays hidden after other errors, and today it doesn't (bug 4B).
7. **Error paths in the reader and library** (F2):
   - A load error other than 404 shows the backend's message (PaperPage.tsx L81-83).
   - A failed "Save to library" (L99-100).
   - Remove cancelled or failed inside the reader (L106-113).
   - The fallback when the PDF viewer fails to load (L247-256).
   - A library removal that fails with a 500 leaves the paper listed (LibraryPage.tsx L34-40). The existing failure test uses a 404 and checks only the message.
8. **Paging cap:** "Load more" should stop at page 100, the backend's `page ≤ 100` limit (SearchPage.tsx L8, L151; backend/app/routers/search.py L27).
9. **Remembered-model fallback** (useModelChoice.ts L14-19): effectively untested, because the test in finding 9 cannot fail.

## 4. Possible application bugs

No test asserts a bug as if it were intended behavior; the tests just can't see these.

**A. The reader re-renders endlessly while a paper is open (App.tsx L73 together with PaperPage.tsx L41-43).**
- Cause: App passes a new inline `onLibraryState` on every render, and that callback stores a new object (`setPaperInLibrary({ id, inLibrary })`). PaperPage re-runs its effect whenever the callback changes, which sets App state again, which renders App again.
- Evidence 1: I loaded the real `src/App.tsx` in memory at `#/paper/4` with an unsaved paper. It made 3,888 React commits in 1 s with no further fetches, and React logged "Maximum update depth exceeded… one of the dependencies changes on every render" 84 times.
- Evidence 2: a probe injected into App.test.tsx collected 59 of those warnings in 1 s.
- The page looks correct, which is why App.test.tsx L47-60 passes.
- Cost: constant CPU use while any paper is open. SectionsPanel, FullTextStatus and ModelSelect are not memoized, so they re-render every time.
- Fix: keep the previous state when nothing changed (`setPaperInLibrary(p => p?.id === id && p.inLibrary === v ? p : { id, inLibrary: v })`), and/or call the callback only when `paper.in_library` changes.

**B. "Search OpenAlex instead" appears for errors that are not failed arXiv searches.**
- SearchPage.tsx L187-205 shows the button whenever the menu says arXiv and the box has text, and the error slot is shared with Read failures (L91-92).
- Evidence: in a probe, an arXiv search succeeded and then Read failed with a 502; the button appeared.
- Switching the source menu after a failure also turns the button on or off.
- The button re-runs whatever is in the input box, not the query that failed. README L19 ties it to a failed arXiv search.

**C. "PDF ↗" ignores the stored PDF when the paper also has a `pdf_url`.**
- PaperCard.tsx L47 uses `paper.pdf_url ?? localPdfHref`, but its prop comment (L35) says it links "a locally stored copy … when the library has one".
- `attach_pdf` (backend/app/services/fulltext.py L106-118) never clears `pdf_url`.
- Result: a paywalled result whose download failed (for example "The PDF link returned HTTP 403") and that the user fixed with "Attach PDF" still links to the publisher URL that already failed. This affects both the Library card and the Details tab (README L62-64 describes this scenario).
- Evidence: the in-memory LibraryPage probe got the external URL.

**Side effect to pass on:** one in-memory experiment made Vite regenerate its git-ignored dependency cache at `/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/frontend/node_modules/.vite/deps/`.
- No tracked file changed; `git status` shows only the user's existing untracked `demo/` files.
- Vite rebuilds that cache on the next `npm run dev`, and deleting it is also safe.
- The test runs updated vitest's own caches as usual. A scan found no mutated code in them, and the six files still pass 78/78.
