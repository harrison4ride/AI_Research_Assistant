# Final review G2: backend search, full-text, outline, and PDF tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the prompt in
`prompts/G2.txt` (the initial review's prompt plus the new helpers and one sentence on
expected failures). Suite: tag `hw2-round2`. 54 tool calls, about 349k tokens,
25 minutes.

---

## Review of the four backend test files: 11 of 140 tests are not OK, plus 7 likely app bugs

Paths below are relative to `/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant/backend`. I changed no files. I checked suspected app behaviour with in-memory probes only (`httpx.MockTransport` and generated PDFs).

## 1. Counts

Running the four files gives 218 passed and 2 xfailed (the two `@known_bug` tests).

| File | Test functions | Parametrized functions (cases) | Collected items | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|---|---|
| tests/test_search.py | 38 | 8 (30) | 60 | 34 | 1 | 1 | 1 | 1 | 0 |
| tests/test_fulltext.py | 29 | 5 (21) | 45 | 26 | 1 | 0 | 1 | 1 | 0 |
| tests/test_outline.py | 18 | 0 | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| tests/test_pdf_extraction.py | 55 | 14 (56) | 97 | 51 | 2 | 0 | 0 | 2 | 0 |
| **Total** | **140** | **27 (107)** | **220** | **129** | **4** | **1** | **2** | **4** | **0** |

## 2. Findings

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_search.py::test_arxiv_rejection_without_a_reason_is_reported | WRONG | L283-284 expect the detail `"arXiv rejected the query: arXiv rejected the query."`, which is a stutter. arxiv.py L94 already uses the full sentence `"arXiv rejected the query."` as the fallback when arXiv gives no reason. arxiv.py L161 then adds the prefix `"arXiv rejected the query: "` again. The search page shows the text as is (SearchPage.tsx L187-189). If the message were fixed, this test would fail. | Expect `(400, "arXiv rejected the query.")`, or at least that the detail does not repeat itself. Fix the app to build the message once. |
| test_search.py::test_arxiv_entry_without_journal_reference_is_labelled_arxiv | REDUNDANT | L251-257 assert `venue == "arXiv"` and `doi is None` for an entry without journal_ref or DOI. `test_arxiv_entries_with_missing_fields` (L208-217) parses an entry with neither and compares the whole dict, which includes both values. No plausible bug fails one test but not the other. | Delete it, or give it a new input, such as a whitespace-only `<arxiv:journal_ref> </arxiv:journal_ref>` (the blank-text path in `_text`). |
| test_search.py::test_arxiv_calls_are_spaced_3_seconds_apart | WEAK | In L344-347 the fake reply takes no time on `clock`, so each call ends when it starts. arxiv.py L99 says the app keeps "3 s between the end of one and the start of the next" (README L276). A bug that counts the 3 s from the previous call's start passes all 3 cases, for example setting `_last_finished` before the `get`. With a slow arXiv, calls would then run back to back. | In `feed`, call `clock.advance(2)` before returning (a 2 s reply). Then expect start gaps of 5.0, 5.0 and 7.0 for later = 1.0, 2.5 and 5.0. The buggy version gives 3.0 and 4.5. |
| test_search.py::test_the_cache_keeps_the_256_most_recently_used_searches | BRITTLE | L483-496 hard-code 256 and the exact least-recently-used eviction order. The docs only promise a 10-minute lifetime (README L130, L223, L279-280). 256 is the undocumented `CACHE_SIZE` in search.py L19, so changing the size breaks the test while all documented behaviour holds. | Loop over `search_router.CACHE_SIZE` instead of 256. Assert only the bound: after CACHE_SIZE+1 different searches, the oldest one is fetched again. Drop the eviction-order steps unless that order becomes a documented rule. |
| test_fulltext.py::test_download_connects_to_the_checked_address | REDUNDANT | L74-78 check host, Host header and SNI name (PUBLIC_IP, papers.example.org, papers.example.org) for the only request. `test_redirect_to_another_public_host_is_followed` (L225-228) checks the same three values for the same first request to PDF_URL, plus a second hop. Neither test exercises the DNS rebinding the comment describes: the fake DNS gives the same answer on every lookup, and `dns.lookups` is never checked. | Make it a real rebinding test: answer PUBLIC_IP on the first lookup and 10.0.0.7 after that (or assert `dns.lookups == ["papers.example.org"]`), and assert the request still goes to PUBLIC_IP. Otherwise delete it. |
| test_fulltext.py::test_a_pdf_download_cannot_hang_forever | WEAK | L152 only checks that the values in `request.extensions["timeout"]` are numbers. The fake transport never enforces timeouts, so a units slip passes: `timeout=0.06` (every real download fails) or `timeout=60_000` (effectively no limit). Also, the 60 s per-phase timeout at fulltext.py L143 does not limit a host that keeps trickling bytes, and the download holds the per-paper lock meanwhile. | Bound each value, for example `5 <= t <= 120`. Add a case where the fake raises `httpx.ReadTimeout` and the paper records "The PDF could not be downloaded." (the fallback INSTALL.md L349 describes). |
| test_fulltext.py::test_only_http_and_https_links_are_allowed | BRITTLE | L287-290 call the private `fulltext._check_public` and require the `UnsafeUrl` class. The documented behaviour is "downloads only http(s) links" (README L107) with a true reason in the message (INSTALL.md L349). Two plausible changes would break this test without breaking that behaviour: moving the scheme check into its own helper, or raising a separate exception for non-http links. The second is the obvious fix for the known bug tested at L304-317. | Test through `POST /fulltext`: save a paper with each link, then assert `full_text_status == "error"`, `upstream.requests == []` and `dns.lookups == []`. |
| test_pdf_extraction.py::test_the_text_is_every_page_in_order_separated_by_blank_lines | BRITTLE | L43-47 rebuild the expected text with the app's own algorithm (pdf.py L167-168: strip each page's `get_text()` and join with `"\n\n"`) and compare exactly. Nothing in the requirements or docs fixes the page separator (README L21; F4 only needs the content). Switching to `"\n"`, form feeds or page markers breaks the test. | Assert that a phrase from each page appears in page order (increasing `text.index`), without fixing the separator. |
| test_pdf_extraction.py::test_a_placeholder_author_in_pdf_properties_is_ignored | WEAK | L136 uses `"me"`, which only the length rule rejects (`len > 3`, pdf.py L189). Realistic placeholders pass that rule and replace the authors read from the layout. I checked that "Microsoft Office User", "Administrator", "user" and "jsmith" each become the whole author list. | Parametrize with real placeholder values. This needs an app rule for authors similar to `JUNK_META_TITLE` (section 4, item 4). |
| test_pdf_extraction.py::test_a_running_header_that_repeats_a_heading_is_listed_once | WEAK | L475 checks titles only. A dedup that keeps the last occurrence (for example a dict keyed by title) would point "2 Method" at the page-3 running header and still pass. Today the kept entry is the 9-pt running header at y=40 on page 2, not the heading at y=90 (I checked). | Assert (title, page) pairs: `[("1 Introduction",1), ("2 Method",2), ("3 Results",3)]`. |
| test_pdf_extraction.py::test_an_abstract_that_runs_on_is_cut_to_its_first_3000_characters | BRITTLE | L218 (`2900 < len(abstract) <= 3000`) pins the bare literal 3000 from pdf.py L137 and L140. No requirement or doc sets a length limit for abstracts. Changing the cap breaks the test while F3 is still met. | Name the cap in pdf.py (for example `MAX_ABSTRACT_CHARS`). Assert the abstract is a prefix of the cleaned body and no longer than that constant. |

**Known-bug tests (both rated OK):**
- **ftp link, L304-317.** It checks the right intended behaviour (README L107, INSTALL.md L349). Every step outside `fails_until_fixed` passes today, so only the named bug makes it xfail. One caveat: L317 requires "http" in the message, so a correct fix worded "uses the unsupported ftp protocol" would keep it xfailing.
- **Malformed link, L324-342.** It checks the right intended behaviour (fulltext.py L169-171 docstring, README L62-64). Every step outside `fails_until_fixed` passes today, so only the named bug makes it xfail.

**Tests kept OK, with caveats:**
- Nine test_pdf_extraction tests (L148-218) call the private helpers `_split_names`, `_guess_year` and `_guess_abstract` directly. What they assert is intent stated in pdf.py comments, but changing those helpers' signatures would break them.
- test_search L55 requires the `select` parameter. Without `select`, OpenAlex returns all fields anyway, so dropping it would break the test for no behaviour change.
- test_search L205 pins `sortBy=relevance`, which is already arXiv's default.
- In test_search L316, the HTTP-date in the Retry-After case is already in the past. 60 s is therefore correct whether or not the app parses dates, so this case cannot show that a future date is honoured.
- test_pdf_extraction L173-184 read the real `date.today()`, as the app does. They could only fail if a run crosses midnight on New Year's Eve, so I did not count them as FLAKY.

## 3. Missing tests

**Search (F1; README L19, L223, L276-280; INSTALL.md L346, L351)**
- OpenAlex body that is valid JSON but not an object (`null`, `[]`), or `results` with null entries. This should be the 502 "unusable response" path (openalex.py L86-91, http.py L11); today it returns 500.
- OpenAlex link falling back to the DOI URL when there is no landing page (openalex.py L56). The only missing-fields test also sets `doi=None`.
- OpenAlex reply without `meta`, which should give `total: null` (openalex.py L90). The arXiv version is tested at L239-248.
- arXiv `Retry-After` given as a future HTTP-date should give a longer pause (README L277-278, INSTALL.md L346).
- Two concurrent arXiv searches should go out one at a time, 3 s apart (arxiv.py L31, L98-99). Only sequential calls are tested.
- A search waiting for the arXiv lock while another call starts a pause should fail with the pause message and send nothing (arxiv.py L102-104).

**Full text (README L59-64, L106-109; INSTALL.md L215-218, L349)**
- A redirect whose `Location` is not http(s) (`file:///...`) or is malformed (`http://[::1`, port 99999). It should be recorded with a true reason, not answered with 500 (fulltext.py L147-149). The known bugs are tested only for direct links.
- A DNS answer that changes between lookups, with a check of one lookup per hop (README L108-109).
- An `httpx.ReadTimeout` in the middle of a download should be recorded, and the abstract used (fulltext.py L199-201). Only ConnectError is tested.
- `fulltext._locks` should be empty after concurrent downloads finish ("reference-counted and removed when unused", fulltext.py L25-27).

**Outline (README L29-36, L268-273; REQUIREMENTS L80-81)**
- `POST /outline/summaries` for an unknown paper should return 404. Only the GET is tested.
- `POST /outline/summaries` when the stored PDF can't be read should return 422 with the outline's reason (assistant.py L211-213).
- When the PDF has no headings and the model names the sections:
  - Its sections should be saved, so a later GET returns them with pages.
  - "Regenerate summaries" (SectionsPanel.tsx L71) should replace the earlier summaries (assistant.py L229-253).
  - A reply with no usable sections should return 502 "The model did not return the paper's sections. Try again." at the endpoint (llm.py L569-570). Only the service function is tested.
- The outline should be extracted once and then served from the database (papers.py L307-331).
- `GET /outline` for a search result deleted while its PDF downloads should return 404 (papers.py L301-302).

**PDF extraction (F3; README L21, L262-273)**
- Author names with lowercase particles, such as "Laurens van der Maaten" (pdf.py L112).
- Placeholder authors in the PDF properties that are longer than 3 characters (pdf.py L189-190).
- More than 120 bookmarks mixing levels 1 and 2: only level-1 entries should be kept (pdf.py L277-278). The existing bound test uses only level-1 bookmarks, so deleting this filter would go unnoticed. I checked that the filter works: 160 mixed bookmarks give 80 level-1 entries.
- "Bibliography" should end heading detection the same way "References" does (pdf.py L225).

## 4. Possible application bugs

1. **Repeated arXiv error text.** When arXiv rejects a query without a reason, the message is "arXiv rejected the query: arXiv rejected the query." It comes from arxiv.py L94 plus L161, the WRONG test above enforces it, and the search alert shows it as is.
2. **Malformed OpenAlex JSON gives HTTP 500.** The parser assumes dicts (`data.get`, `work.get`, `a.get` at openalex.py L41-52 and L90-91), and search.py L41 only catches UpstreamError. With a mock transport, all of these raise AttributeError: `[]`, `null`, `{"results":[null]}` and `{"results":[{"authorships":[null]}]}`. The intended path is a 502 (openalex.py L89, http.py L11).
3. **arXiv Retry-After dates are ignored.** arxiv.py L123 only accepts digits. A `Retry-After` set to now + 5 minutes as an HTTP-date gives a 60 s pause (checked). README L277-278 and INSTALL.md L346 promise a longer pause when the header asks for one, up to 600 s.
4. **Placeholder authors in the PDF properties replace the real ones.** pdf.py L189-190 accepts any value longer than 3 characters. "Microsoft Office User", "Administrator", "user" and "jsmith" each become the full author list (checked). This breaks F3 (REQUIREMENTS L15) whenever Claude metadata extraction is off or unavailable.
5. **Authors with lowercase particles are dropped.** pdf.py L112 requires every word to start with a capital letter. `_split_names("Laurens van der Maaten, Geoffrey Hinton")` and `extract(...)` both return `["Geoffrey Hinton"]` (checked). README L262-265 only admits mis-split names on unusual layouts, not dropped common names.
6. **Both known bugs are also reachable through a redirect.** fulltext.py L148 joins the `Location`, and the next `_check_public` raises ValueError ("Invalid IPv6 URL" or "Port out of range", checked). `ensure_full_text` does not catch it (L193-203), so the request returns 500. A `Location: file:///...` gets the false "local or private address" reason.
7. **IPv6-literal PDF links send a malformed Host header.** The header is `2606:4700::1111` without brackets (fulltext.py L141; checked against `httpx.URL.host`). RFC 3986 §3.2.2 and RFC 9110 §7.2 require `[...]`. This is a rare edge case.

Two related bugs are already tracked as known-bug tests in other files: the `JUNK_META_TITLE` missing end anchor (test_upload.py L169) and the silent 300-page text cut (test_summary.py L199).

Separately, several MCP connectors need authorization (Amplitude, Hex, Atlassian, Intercom, Linear, Notion, Slack), and two failed to connect (common-kg, definite). This review did not need any of them.
