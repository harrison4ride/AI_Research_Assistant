# Final review G1: backend library, upload, app, and isolation tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the prompt in
`prompts/G1.txt` (the initial review's prompt plus test_isolation.py, the new helpers,
and one sentence on expected failures). Suite: tag `hw2-round2`. 57 tool calls, about
374k tokens, 30 minutes.

---

## 1. Counts

All four files pass today: 170 passed and 1 xfailed, the known-bug test. No repository file was changed. I checked the WEAK claims by mutating the app in memory with a pytest plugin in my scratchpad (`…/scratchpad/plugins/mutation_plugin.py`, set with `MUTATION=…`) and running the whole backend suite, which is 553 passed + 5 xfailed at baseline.

| File | Test functions | Parametrized functions → cases | Collected | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|---|---|
| test_library.py | 57 | 12 → 51 | 96 | 49 | 4 | 0 | 4 | 0 | 0 |
| test_upload.py | 31 | 5 → 22 | 48 | 27 | 2 | 0 | 1 | 1 | 0 |
| test_app.py | 19 | 4 → 11 | 26 | 19 | 0 | 0 | 0 | 0 | 0 |
| test_isolation.py | 1 | 0 → 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **108** | **21 → 84** | **171** | **96** | **6** | **0** | **5** | **1** | **0** |

Known-bug test: `test_upload.py::test_a_real_title_in_pdf_properties_is_kept_whatever_word_it_starts_with` is **OK**.
- Its expectation matches pdf.py:36 ("Placeholder titles that PDF producers write into the metadata").
- The 201 check is outside `fails_until_fixed`.
- With `--runxfail`, the only failure is the title list: all four come back as the layout title "Retrieval Helps Language Models Stay Factual". So it fails only because of the JUNK_META_TITLE prefix match it names.

## 2. Findings

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_library.py::test_saved_paper_detail_has_no_summary_yet | WEAK | Lines 77-80 compare only `title`. `summary` and `summary_model` are None for every new row by column default. A GET /api/papers/{id} that returned wrong `authors`, `doi`, `in_library` or `saved_at` would still pass. | `assert detail == {**paper, "summary": None, "summary_model": None, "summary_context": None, "summary_created_at": None}`. PaperDetail is PaperOut plus these four fields, and a GET of a library paper changes nothing. |
| test_library.py::test_timestamps_are_utc_with_offset | WEAK | The only check that the stored time is really UTC is the 1-minute window at line 89. It can tell local time from UTC only when the machine's zone is not UTC. I replaced `datetime.now(timezone.utc)` in routers/papers.py with naive local `datetime.now()`: the test fails on this machine (EST), but all 553 backend tests pass under `TZ=UTC`, as on a typical CI runner. The TZ fixture is used only for pruning, with hand-made timestamps (lines 622-628). | Use the existing `local_time_far_from_utc` fixture (lines 608-619) in this test. |
| test_library.py::test_saving_the_same_paper_twice_returns_the_existing_entry | REDUNDANT | Lines 92-98 make the same two POSTs and the same three checks (201 then 200, same id, one entry) as `test_the_same_result_without_a_doi_is_kept_once[save]` (156-166). That case can only match on (source, external_id). ARXIV_META also matches on its DOI and arXiv id, so any bug that fails this test also fails that one. DOI matching is covered by `test_doi_match_ignores_case`. | Delete it. Or make it check something new: a second save that carries different metadata returns the stored entry unchanged (README API row: "returns the existing entry"), so "Edit details" corrections survive a re-save from search. |
| test_library.py::test_opening_again_returns_the_same_entry | REDUNDANT | Lines 243-249 are covered by `test_the_same_result_without_a_doi_is_kept_once[open]`: same endpoint, same paper without its DOI, and it also checks the first 201 and that only one row is stored. Also covered by `test_opening_a_search_result_again_postpones_its_deletion` (726-737), which reopens BERT_META with its DOI and checks the id. | Delete it. |
| test_library.py::test_saving_an_opened_paper_from_search_keeps_its_id_and_conversation | REDUNDANT | Lines 271-281 repeat `test_saving_an_opened_paper_keeps_its_summary_section_summaries_and_conversation[search page]` (750-778). Both open BERT_META, add a conversation, POST the same result to /api/papers, and check 200, same id, in library, and conversation kept. The later test also checks the summary and the outline. | Delete it. |
| test_library.py::test_pruning_removes_the_pdf_of_a_deleted_paper | REDUNDANT | Lines 631-637 prune one stale unsaved paper with its own PDF and check `not pdf_file.exists()`. `test_pruning_removes_every_stale_paper_with_its_own_pdf` (597-605) does the same for two papers and also checks the count and the rows. | Delete it. |
| test_library.py::test_unsaved_papers_are_also_pruned_every_12_hours | WEAK | Lines 691-695 call the private `_prune_periodically()` directly with a fake `asyncio`. Nothing checks that the app actually starts it. With the lifespan replaced by one that never calls `asyncio.create_task(_prune_periodically())` (main.py:31), all 553 backend tests pass. REQUIREMENTS line 84 and README line 56 promise pruning "every 12 hours". The fake namespace, which has only `sleep` and `to_thread`, also ties the test to those two calls. | Keep the loop test. Add a TestClient run with `main_module._prune_periodically` replaced by a spy coroutine, and assert it starts at startup and is cancelled at shutdown. |
| test_library.py::test_pruning_follows_the_cached_paper_days_setting | WEAK | With CACHED_PAPER_DAYS=30 it only checks that an 8-day-old paper is kept (703-707). Any rule that keeps papers for at least 8 days passes. A retention cap of `min(days, 10)` in cache.py:18 passed all 553 backend tests, yet it would delete papers after 10 days under a 30-day setting. No test uses a value below the default 7. | At 30 days, also check that a 31-day-old paper is removed and a 29-day-old one is kept. Add a case with CACHED_PAPER_DAYS=1 (or 3) that removes a 2-day-old (or 4-day-old) unsaved paper. |
| test_upload.py::test_upload_asks_the_llm_with_the_text_of_the_first_pages_only | BRITTLE | Line 66, `len(first_pages) <= 15_000`, pins the literal in `extracted.text[:15000]` (papers.py:251). README 256-258 and INSTALL 180 promise only "the first pages". Sending 20,000 characters would also be correct (about 5 of this PDF's 11 pages, still without the last line), but it fails here. Lines 65 and 67-69 already check the documented behavior: a prefix of the text, more than page 1, not the last page. | Drop line 66. Or make the limit a named app constant (it is also hard-coded at papers.py:202) and compare against that. |
| test_upload.py::test_placeholder_title_in_pdf_properties_is_ignored | WEAK | 5 of the 8 cases on line 148 ("untitled", "paper", "main", "arXiv", "main.pdf") are 8 characters or shorter. `len(meta_title) > 8` (pdf.py:184) drops them before JUNK_META_TITLE is ever consulted. With the regex disabled, those 5 cases still pass. With `untitled\|paper\|main\|arxiv` removed from the regex, all 553 backend tests pass, though "Untitled document" (the Google Docs default) would then become the paper's title. | Use placeholders longer than 8 characters that only the regex catches, e.g. "Untitled document", "Document12", "final_paper.pdf", "main_v2.tex". This also guards the fix for the known bug. |
| test_upload.py::test_a_real_title_in_pdf_properties_is_kept | REDUNDANT | Lines 155-158 check that a real properties title (over 8 characters, matching no placeholder) is used. That is the same input kind as `test_pdf_metadata_title_and_authors_are_used` (138-144), whose checks are a superset. "Untangling…" does not start with a placeholder word, so it cannot catch the prefix bug either; the known-bug test covers that. | Delete it. |
| test_upload.py::test_arxiv_pdf_gets_its_metadata_from_arxiv | WEAK | Lines 196-204 check title, authors, year, doi, url and venue, but not the abstract. F3 requires the abstract, and papers.py:247 copies it from arXiv. When `_arxiv_metadata` is mutated to keep the PDF's own abstract, all 553 backend tests pass. | Add `assert paper["abstract"] == "The dominant sequence transduction models are based on complex recurrent networks."` This is arXiv's summary and differs from SAMPLE_ABSTRACT. |

No test is WRONG or FLAKY. The race tests patch internals to inject the race: `papers_router.find_duplicate`, `cache.delete`, `fulltext.store_pdf`. What they assert is still app behavior, so I rated them OK.

## 3. Missing tests

1. **The app starts the 12-hour pruner and cancels it at shutdown** (main.py:31-35; REQUIREMENTS line 84; README line 56). No test covers this; see the WEAK row.
2. **CACHED_PAPER_DAYS values other than 7, on the delete side** (INSTALL line 183: deleted "after this many days", "Must be at least 1"). No test checks a value below 7, or that pruning happens at a non-default value.
3. **Concurrent upload of the same file**, the IntegrityError path in papers.py:258-266 ("the same file was uploaded concurrently"). It should answer 200 with the existing entry and leave one row. Only the search-result race is tested (test_library.py:169-191).
4. **Promotion across sources** (README F2: "keeps one entry when their DOI or arXiv id matches"; API row for `POST /api/papers`: "moves an unsaved one into the library"). Open a paper from arXiv, then save its OpenAlex copy: the unsaved arXiv row should move into the library. Dedupe and promotion are each tested only on their own.
5. **Two stale unsaved papers sharing one PDF**: the file must be gone once both are pruned (README 53-56; cache.py:29-33). Only the case "a library paper still uses it" is tested.
6. **The database's real location and persistence across a process restart** (INSTALL 52-53: "a single file, backend/data/app.db, created on first start").
   - conftest's `scratch.connect_engine_to` rewrites every connection of the app's engine to the scratch file.
   - So `test_library_survives_a_restart` cannot notice a wrong `DB_PATH` or engine URL in db.py:21-24.
   - The e2e server uses db.py's real path, but it never restarts the process.
   - A cheap test: `assert engine.url.database == str(settings.data_dir / "app.db")`, and the file exists after startup.
7. **"Never reuse a deleted paper's id" on an upgraded database** (models.py:48-50). Only a fresh database is tested (test_library.py:549-555), and an upgraded one fails today (bug 1 below).
8. **Re-attaching the identical PDF keeps the outline and its section summaries.** fulltext.py:119-123 resets them only when the file changes, and only that reset is tested (test_outline.py::test_attaching_a_new_pdf_resets_the_outline).

## 4. Possible application bugs

No test in these files asserts behavior contrary to the oracle. I found these app problems:

1. **Upgraded pre-M3 databases reuse deleted paper ids.** This contradicts models.py:48-50 ("stale links or in-flight requests for it must not land on a different paper").
   - `sqlite_autoincrement` arrived in M3 (commit 0f59187). A papers table created at M2 (49aa60f) has no AUTOINCREMENT; that is the same schema as `M2_PAPERS_TABLE`, which I checked against git.
   - `init_db()` (db.py:49-66) only adds columns, so it never fixes this.
   - Evidence, from a script run on a scratch DATA_DIR with isolated settings:
     - fresh database: create ids 1 and 2, delete 2 → the next paper gets id 3;
     - M2 database after `init_db()`: the next paper gets id **2**.
   - `test_an_older_database_is_upgraded_and_keeps_its_papers` never deletes and re-adds a paper, so it misses this.
2. **The edit form can send values the backend rejects** (same class as DEVLOG M2 #6). Low severity.
   - The abstract textarea (EditPaperForm.tsx:62) has no maxLength, and the form always resends all four fields (lines 25-30).
   - `PaperUpdate` caps the abstract at 20,000 characters (schemas.py:126).
   - Stored abstracts are not capped: `PaperMeta` has no limit, and papers.py:210-211 accepts an LLM abstract of any length ≥ 100. So for such a paper, even a title-only edit fails with 422.
   - The same applies to authors (limit 10,000) and to a stored title over 500 characters: pdf.py:184 accepts properties titles of any length, and `maxLength={500}` does not trim a pre-filled value.
   - The name `test_the_largest_edits_the_form_allows_are_accepted` implies 20,000 is the form's limit; it is not.
3. **The known bug in pdf.py:37 is real, and the xfail test is correct.** A warning for the fix:
   - As whole titles, the bare words `untitled|paper|main|arxiv` are already dropped by `len > 8`; they only matter as prefixes.
   - Anchoring the whole pattern with `$` would stop catching "Microsoft Word - …", which an existing test would catch.
   - It would also stop catching "Untitled document", which no test checks today.
