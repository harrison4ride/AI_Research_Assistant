# Review G2: backend search, full-text, outline, and PDF tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the rubric in
`tools/review-rubric.md` given inline. Scope: test_search.py, test_fulltext.py,
test_outline.py, test_pdf_extraction.py. The reviewer verified each non-OK call by
in-memory mutation runs (no file changes).

---

Most tests check the intended behavior: 73 of 81 are OK, 4 are WEAK, 2 REDUNDANT, 2 BRITTLE, and none are WRONG or FLAKY. The review also found 4 application bugs, one of which leaves an affected paper with no summary, Q&A or outline.

All 121 collected cases pass (4.3 s). I checked every non-OK finding with in-memory mutation runs: a pytest plugin patched one app function after collection, then re-ran the target files. Nothing was written to the repo (bytecode and pytest cache were off, the isolated test DATA_DIR was asserted, and `git status` was unchanged). Mutations that should fail did fail. "Survived" below means the mutation passed every test in the files it was run against.

## 1. Counts

| File | Test functions | Parametrized | Collected cases | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|---|---|
| backend/tests/test_search.py | 27 | 3 functions, 14 cases | 38 | 26 | 1 | 0 | 0 | 0 | 0 |
| backend/tests/test_fulltext.py | 16 | 3 functions, 14 cases | 27 | 14 | 1 | 0 | 1 | 0 | 0 |
| backend/tests/test_outline.py | 13 | none | 13 | 11 | 1 | 0 | 0 | 1 | 0 |
| backend/tests/test_pdf_extraction.py | 25 | 5 functions, 23 cases | 43 | 22 | 1 | 0 | 1 | 1 | 0 |
| Total | 81 | 11 functions, 51 cases | 121 | 73 | 4 | 0 | 2 | 2 | 0 |

Parametrized functions and their case counts:
- **test_search:** `test_openalex_errors_become_clear_http_errors` (3), `test_arxiv_errors` (2), `test_invalid_search_requests_are_rejected_before_calling_any_source` (9).
- **test_fulltext:** `test_download_failures_are_recorded_with_the_reason` (4), `test_links_to_local_or_private_addresses_are_not_downloaded` (7), `test_only_http_and_https_links_are_allowed` (3).
- **test_pdf_extraction:** `test_author_names_are_split_from_a_line` (5), `test_abstract_is_found_after_its_heading` (4), `test_abstract_ends_before_keywords_footnotes_and_venue_notes` (5), `test_unusable_pdfs_raise_a_readable_error` (3), `test_title_on_page` (6).

Why none is FLAKY:
- `test_years_in_the_future_are_ignored` computes the year from `date.today()` on both sides; it could only fail in a microsecond window at New Year's midnight.
- `test_arxiv_rate_limit_pauses_further_calls` rounds a monotonic-clock difference that is computed immediately.
- `test_section_summaries_through_claude_code` runs a fake CLI, not the real one, with timeouts of 8 to 600 s. A slow status check counts as "ready", so the outcome does not change.

## 2. Findings

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_search.py::test_openalex_abstract_is_rebuilt_from_the_inverted_index | WEAK | At L340 every word has exactly one position ("Hello" and "hello" are separate keys). The other fixture abstracts (support/upstream.py L80, test L86) have no repeated words either. A rebuild that keeps only each word's first position (sorting items by `positions[0]`) survived all 38 cases. Real OpenAlex abstracts repeat "the", "of" and "a" at many positions (openalex.py L33 docstring: `{word: [positions]}`). | Add a word with several positions: `rebuild_abstract({"the": [0, 3], "cat": [1], "saw": [2], "dog": [4]}) == "the cat saw the dog"`. |
| test_fulltext.py::test_redirect_loops_give_up | WEAK | L155 takes the expected count from the code itself (`fulltext.MAX_REDIRECTS + 1`). With `MAX_REDIRECTS = 20` all 27 cases still pass, but README L108, INSTALL L217 and PLAN L69-70 all promise "at most 5". | Assert `len(upstream.requests) == 6` (first request plus 5 redirects). Optionally add a chain of exactly 5 redirects that ends in a PDF and succeeds. |
| test_fulltext.py::test_public_address_check_returns_the_ip_to_connect_to | REDUNDANT | Duplicates `test_download_connects_to_the_checked_address` (L45-54). That test uses the same host and IP and asserts the request really went to PUBLIC_IP. Making `_check_public` return the hostname fails both tests. Removing the IP pinning fails only L45-54. So L197-199 catches nothing extra. | Delete it, or reuse it for the untested rule that all resolved addresses must be public (fake DNS answering a public and a private address must raise UnsafeUrl). That needs the conftest `dns` fixture to accept a list per host. |
| test_outline.py::test_outline_lists_the_sections_of_the_pdf | WEAK | L35 checks `top` only as `0 <= top <= 1`. Setting every `top` to 0 survived all 56 tests in test_outline.py and test_pdf_extraction.py. Reading the x coordinate instead of y would also pass. `top` drives "jump to section" and the highlight of the section being read (README L30-31; SectionsPanel.tsx L58-64, L94). | Assert ordering within each page: Abstract < 1 Introduction on page 1, and 2 Method < 3 Experiments < 4 Conclusion on page 2 (currently 0.251/0.363 and 0.097/0.189/0.263). Or compare against the generator's y/792 with a tolerance. |
| test_outline.py::test_section_headings_are_passed_to_the_model_as_data | BRITTLE | L82 matches the exact spacing `json.dumps` produces: `'{"n": 2, "heading": "1 Introduction"}'`. Switching to compact separators still passes headings as JSON data, which is the intent at llm.py L517. Yet that change fails only this test; the other 12 outline tests pass, including the Claude Code path. The plain heading also cannot show that quotes are escaped. test_llm_service.py L521-522 pins the same string. | Cut out the `<headings>` block, `json.loads` it, and compare it to `[{"n": i, "heading": t}, ...]`. Use a bookmark title containing `"` so escaping is exercised. Keep the `call.model == "sonnet"` and BODY_MARKER assertions. |
| test_pdf_extraction.py::test_locate_headings_in_reading_order | WEAK | At L203-205 every title is found on the same page whether or not the search moves forward. Replacing `start = hit[0]` with `start = 0` (pdf.py L429; docstring L395 says "searching forward through the document in order") survived all 56 tests in test_outline.py and test_pdf_extraction.py. | Add an out-of-order case: `locate_headings(sample_pdf(), ["Experiments", "Introduction"])` must give `[2, None]` (I confirmed this output). Without the forward search, "Introduction" comes back on page 1. |
| test_pdf_extraction.py::test_heading_beats_an_earlier_mention_in_the_text | REDUNDANT | Duplicates `test_locate_headings_in_reading_order`. L211 ("Method" found on page 2) runs exactly the same search as that test's "2. Method" entry at L203: same normalized target "method", same start page, same mention on page 1. A "first match wins" mutation fails both, and no plausible bug fails only this one. | Delete it, or reuse it for rank 1, which no test covers (pdf.py L421: a heading line that starts with the title should beat a mention in running text). |
| test_pdf_extraction.py::test_only_the_first_300_pages_are_read | BRITTLE | L108-116 pins `MAX_PDF_PAGES_FOR_TEXT = 300` (pdf.py L39). That is a bare constant with no comment; neither README nor INSTALL mentions it (README L87-89 documents only the `LLM_MAX_PAPER_CHARS` cut). Raising it to 500 fails only this test; the other 82 tests in test_pdf_extraction.py, test_outline.py and test_fulltext.py pass. The test also locks in a cut nobody is told about (bug 2 below). | If the cap is intended, document it, assert against `pdf.MAX_PDF_PAGES_FOR_TEXT`, and also assert that the cut is disclosed. Otherwise drop the test. |

## 3. Missing tests

No test anywhere in backend/tests covers the following.

**Search (F1):**
- **arXiv 3-second spacing** (README L275-276; arxiv.py L31, L98-111). conftest.py L91 and support/e2e_server.py L124 set `_MIN_INTERVAL = 0`, so the spacing code never runs.
- **Cooldown limits and expiry** (README L277-279; INSTALL L346 "up to 600 seconds"):
  - Retry-After above 600 should be capped at 600.
  - Retry-After below 60, or non-numeric, should give 60.
  - arXiv should be called again once the pause ends.
  - Removing either limit survived.
- **Result cache** (README L223, L279-280; PLAN L30):
  - Entries should expire after 10 minutes; a cache that never expires survived.
  - The cache should hold at most 256 entries.
  - `per_page` should be part of the cache key; a key without it survived.
- **Response echoes the requested page** (SearchPage.tsx L123 feeds "Load more"; README L19). Forcing `page=1` in the response survived, because `test_openalex_is_the_default_source_and_gets_the_query_and_paging` never reads the response.
- **Largest valid values are accepted:** page=100 and per_page=50 (README L223; SearchPage.tsx L8), and a 300-character query (SearchPage.tsx L164). Only the rejected side is tested.
- **arXiv connection error** should give 502 "Could not reach arXiv…" without starting a cooldown (arxiv.py L148-150).

**Full-text download (README L59-64, L106-109; INSTALL L215-218; PLAN L36-37, L67-72):**
- **Host with a private address among its addresses** should be refused (PLAN L69; fulltext.py L73). The fake DNS returns one address per host, and changing `all` to `any` survived.
- **TLS uses the real host name (SNI)** while connecting to the pinned IP (fulltext.py L144-145; PLAN L70-71). Removing `extensions={"sni_hostname": ...}` survived. The connection test could assert `request.extensions["sni_hostname"]`.
- **Each redirect hop connects to its own checked IP** (README L108-109; fulltext.py L136). Leaving hop 2 unpinned survived. The public-redirect test could assert `[r.url.host for r in upstream.requests] == [PUBLIC_IP, "93.184.216.99"]`.
- **Malformed PDF link** (invalid port or IPv6 literal) should be recorded as an error (`ensure_full_text` docstring L169-171). It currently crashes; see bug 1.
- **Concurrency and deletion:**
  - Overlapping requests should trigger only one download per paper (fulltext.py L25-26).
  - A paper deleted mid-download should give 404 with nothing stored (L161-163, L205-206).
- **GET /outline downloads the PDF** of a search result that was never fetched, then lists its sections (PLAN L36-37). Only the summary path is covered (`test_summary.py::test_summary_downloads_the_open_access_pdf_first`).

**Outline (README L29-34, L268-273; REQUIREMENTS L80-81):**
- **Section positions:** heading positions are the WEAK row above. Bookmark positions, including the coordinate flip for named destinations (pdf.py L260-271), are untested: forcing `_bookmark_top` to 0 survived.
- **Summaries are discarded** when the paper is deleted (404) or its PDF replaced (409) during the model call (assistant.py L242-249). Same for `ensure_outline`'s 409 (papers.py L323-325). `FakeLLM.reply(before=...)` already supports this; test_summary.py L192 uses it for summaries.
- **Saving an unsaved paper keeps its section outline and summaries** (REQUIREMENTS L80; README L52-53). test_library.py checks only the chat.
- **More than 120 bookmarks** should keep only level-1 entries (pdf.py L277-278).

**PDF metadata (F3):**
- A real title in the PDF's properties that starts with "Main", "Paper", "Document" or "arXiv" should be kept (pdf.py L36-37). Such a test would expose bug 3.

## 4. Possible application bugs

No test asserts behavior that contradicts the documented intent. The closest is the 300-page test, which locks in bug 2. I reproduced all four bugs below in the isolated test setup.

1. **A malformed PDF link breaks every endpoint for that paper** (medium severity for the papers affected).
   - **Cause:** `_check_public` calls `urlsplit(url)` and `.port` (fulltext.py L64-67). These raise ValueError for links like `https://host:99999/x.pdf` or `http://[::1/x.pdf`. `ensure_full_text` catches only UnsafeUrl, TooLarge, HTTP errors and PdfError (L193-203).
   - **Observed:** POST /fulltext, GET /outline and POST /summary all raised `ValueError: Port out of range 0-65535` or `Invalid IPv6 URL`. `full_text_status` stays None, so every later call fails the same way.
   - **Why it is wrong:** the docstring (L169-171) says expected failures are "recorded ... rather than raised", and README L62-64 says the app falls back to the abstract and offers Attach PDF.
   - **User impact:** the reader's error state shows only a "Retry" link (FullTextStatus.tsx L70-78). The only Attach PDF button is in the other branch, so the user cannot recover from the reader.
   - **Fix:** catch ValueError and `httpx.InvalidURL` in `_check_public` and `_download`, or turn them into UnsafeUrl.
2. **Text past page 300 is dropped without telling anyone.**
   - **Cause:** `extract` reads at most 300 pages (pdf.py L39, L167) but stores the full page count. `build_context` (llm.py L133-140) then tells the model "Full text extracted from the PDF (302 pages)." with `truncated=False`.
   - **Observed:** with the test's own 302-page file, the text lacks page 301 and is only 27,598 characters.
   - **Why it is wrong:** README L87-89 promises that the model and the Summary tab are told when the text is cut off.
   - **Severity:** low, because dense 300-page PDFs hit `LLM_MAX_PAPER_CHARS` first and are flagged.
3. **Real titles are rejected as placeholders.**
   - **Cause:** `JUNK_META_TITLE` (pdf.py L37) has no word boundary, so "Maintaining Consistency…", "Paperclip…", "Documenting…" and "arXiv Usage…" all match.
   - **Observed:** a PDF whose properties hold "Maintaining Consistency in Distributed Logs" gets the title guessed from the layout instead.
   - **Why it is wrong:** the comment at L36 says the pattern is meant only for placeholder titles that PDF producers write.
   - **Severity:** low, because the layout guess is the fallback and arXiv or Claude metadata usually override it.
4. **Wrong explanation for non-http(s) links.**
   - **Cause:** an `ftp://…` link raises UnsafeUrl (fulltext.py L65-66), which is reported as "The PDF link points to a local or private address, so it was not downloaded." (L193-194).
   - **Why it is wrong:** not downloading is intended (README L106-107), but the stated reason is false. INSTALL L349 tells users this message means a local or private address.
   - **Severity:** low.
