# Review G1: backend library, upload, and app tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the rubric in
`tools/review-rubric.md` given inline. Scope: test_library.py, test_upload.py,
test_app.py. 50 tool calls, about 25 minutes. The reviewer verified each WEAK call
by swapping single app functions in memory and re-running the backend suite.

---

## 1. Counts

13 of the 78 test functions are WEAK; the other 65 are OK. No test is WRONG, REDUNDANT, BRITTLE or FLAKY.

| File | Test functions | Parametrized | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|---|
| test_library.py | 43 | 5 functions, 24 cases (62 collected) | 36 | 7 | 0 | 0 | 0 | 0 |
| test_upload.py | 24 | 2 functions, 6 cases (28 collected) | 23 | 1 | 0 | 0 | 0 | 0 |
| test_app.py | 11 | none (11 collected) | 6 | 5 | 0 | 0 | 0 | 0 |
| **Total** | **78** | **30 cases (101 collected)** | **65** | **13** | 0 | 0 | 0 | 0 |

- **Status:** all 101 tests pass.
- **Not flaky:** they still pass with misleading variables exported (`CACHED_PAPER_DAYS=30`, `LLM_PROVIDER=api`, `MAX_PDF_MB=1`, `ANTHROPIC_PROFILE`, …) and with the file order reversed. They use no network, no real CLI and no sleeps.

## 2. Findings

**How I tested:** I swapped single app functions in memory (no file was changed; the plugin aborts unless the database is the test scratch one) and reran the whole backend suite (360 tests). "Survives" means all 360 still pass with the bug in place.

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_library.py::test_same_paper_from_arxiv_and_openalex_is_saved_once | WEAK | `ARXIV_META` already carries the arXiv DOI (support/papers.py L25), so the plain DOI match (papers.py L69, L75) dedupes it. The arXiv-id-vs-arXiv-DOI branch (papers.py L70-71) is never needed, although the `find_duplicate` docstring (L61-65) says it exists for exactly this order. Deleting that branch survives. | Save `meta(ARXIV_META, doi=None)` first (what `arxiv.parse_entry` produces when the feed has no `<arxiv:doi>`), then post `OPENALEX_META`. Assert 200, same id, one entry. The current app passes this. |
| test_library.py::test_doi_match_ignores_case | WEAK | L102-104 only stores an upper-case DOI and sends a lower-case one, which exercises only the SQL-side `func.lower` (papers.py L75). Dropping `.lower()` on the incoming DOI (L69) survives. Then a paper saved from OpenAlex (lower-case DOIs) and later posted with a mixed-case DOI is stored twice. | Parametrize both directions: store lower and post upper, and the reverse. |
| test_library.py::test_different_papers_get_separate_entries | WEAK | L113 checks only a length, and the two papers differ in source, external_id and DOI at once. Changing `&` to `|` on papers.py L66 (match on source OR id) still gives 2 here; only the filter test catches that bug. | Use two different papers from the same source, e.g. `BERT_META` and `meta(BERT_META, external_id="W2", doi="10.1/other", title="Other")`. Assert distinct ids and that both titles are listed. |
| test_library.py::test_filter_longer_than_200_characters_is_rejected | WEAK | L264 checks only the rejecting side. A cap tighter than the UI's (LibraryPage.tsx L61 `maxLength={200}`), e.g. `max_length=100` at papers.py L81, would reject filters the UI allows and still pass. | Also assert `q="x"*200` returns 200 (it does today). |
| test_library.py::test_partial_edit_leaves_other_fields_alone | WEAK | L304-305 check title and authors only. A PATCH that clears fields it was not sent survives: the tested bug sets `paper.abstract = None` when abstract is absent (update_paper, papers.py L344-356). | After the year-only PATCH, assert every other `ARXIV_META` field (abstract, url, venue, doi) is unchanged. |
| test_library.py::test_invalid_edits_are_rejected | WEAK | L335-343 contain only rejecting cases (501 chars, 999, 2101, 20001). Nothing checks that the edge values are accepted, so an off-by-one or tighter limit in schemas.py L122-126 (`lt=2100`, `max_length=499`) passes. Those edge values are ones the edit form allows (EditPaperForm.tsx L43 `maxLength={500}`, L54-55 `min=1000 max=2100`). Also, for the year and abstract cases, L350 re-checks the title, not the rejected field. | Add accepting cases: title `"x"*500`, years 1000 and 2100, abstract `"x"*20000`, a few thousand authors (schemas.py L123 comment). I checked that the app accepts all of these. Assert the rejected field itself is unchanged. |
| test_library.py::test_deleting_a_paper_deletes_its_conversation | WEAK | L384 counts all `ChatMessage` rows, and only the deleted paper has messages. A `delete_paper` that wipes every paper's conversation (`db.execute(delete(ChatMessage))`) survives. | Give a second paper a message and assert it survives (GET `/api/papers/{other}/chat`). The prune test's chat check (L451-452) has the same blind spot. |
| test_upload.py::test_upload_asks_the_llm_with_the_text_of_the_first_pages | WEAK | L55 `len(first_pages) <= 15000` cannot fail: the sample PDF's whole text is 1,317 characters. Sending the whole paper (dropping `[:15000]` at papers.py L251) survives, although README L21 and L256-258 say only the first pages go to the model. | Upload a PDF longer than about 15,000 characters with a marker on its last page. Assert the marker is absent from the request and that the request is a prefix of the text. |
| test_app.py::test_root_explains_where_the_ui_is_when_only_the_api_is_served | WEAK | Both API-only pages, the dev-mode one and "No frontend build was found" (main.py L86-95), contain both asserted strings (L19-20). INSTALL.md L338 says "The page says which case applies." I checked: with `SERVE_FRONTEND=true` and no build, the page says "No frontend build was found … Run make build" and this test still passes, so an inverted branch would go unnoticed. | Assert `"In development mode"` is in the text and `"No frontend build"` is not. |
| test_app.py::test_unknown_api_path_is_a_json_404 | WEAK | It runs only with `SERVE_FRONTEND=false` (conftest.py L41), where no UI routes exist, so it only checks a FastAPI default. main.py L60-62 promises JSON 404s for `/api` in the production branch, which no backend test loads. I checked: a SPA fallback route `/{path:path}` added to that branch makes `/api/does-not-exist` return 200 HTML, and this test catches that only when run against a production-mode app. | Also run it against `app.main` reloaded with `serve_frontend=True` and a minimal build (index.html plus `assets/` in tmp_path), the way support/e2e_server.py configures it. |
| test_app.py::test_wrong_method_is_a_405 | WEAK | L30 checks only the status code, and only in dev mode. main.py L62 promises JSON 405s; an error handler that renders HTML but keeps `exc.status_code` would pass. | Assert `response.json() == {"detail": "Method Not Allowed"}` and also run it in the production-mode app. |
| test_app.py::test_config_for_the_default_claude_code_provider | WEAK | The provider and model values checked at L35-37 come from conftest.py L42-43 (`LLM_PROVIDER=claude-code`, `CLAUDE_CODE_MODEL=opus`), not from the defaults in config.py L47 and L49. Changing the default provider to "api" or the default model to "sonnet" still passes, although REQUIREMENTS.md L78 and README L211-213 promise claude-code and opus. Only `cached_paper_days == 7` checks a real default. No test in the suite builds Settings without these variables. | Remove both variables with monkeypatch.delenv and assert on `config.Settings(_env_file=None)`, or clear the `get_settings` cache and call `/api/config`. |
| test_app.py::test_config_reports_logged_out_claude_code | WEAK | L63 compares against the app's own constant `claude_code.LOGIN_HINT`. A wrong command in that constant (anything other than the `claude auth login` documented in INSTALL.md L343) passes, and no backend test pins that text. | Assert `"claude auth login"` is in `body["llm_hint"]`. |

Smaller issues inside tests I rated OK:
- **Storage naming:** test_upload.py L42, L68 and L268 pin how files are stored (an upload's external_id equals the SHA-256 of the file; files are named `<sha256>.pdf`). Storage by content hash is documented intent in code comments (fulltext.py L88, papers.py L403), so I kept these OK. A change of hash or naming that users would never see would still break these lines.
- **Mislabelled filter case:** test_library.py L233 labels the "attention" case `# title`, but it also matches `ARXIV_META`'s abstract ("attention mechanisms", support/papers.py L18-20). Title-only matching is still covered by the "ÜBER" and "efficient" cases.
- **In-process restart:** test_library.py L273-280 restarts only the app's startup/shutdown, in the same process, reusing the same database engine and open connections. Calling `engine.dispose()` between the two clients would make it reopen the SQLite file like a real restart.

## 3. Missing tests

1. **F2 dedupe, arXiv first:** saving an arXiv result that has no DOI, then the OpenAlex copy (papers.py L70-71; README L20). The branch can be deleted with all 360 tests passing.
2. **Database upgrade (db.py L41-69):** `init_db` adding missing nullable columns to an older database, filling in `in_library=1` and `saved_at=created_at` (L67-69), and the clear RuntimeError for a new NOT NULL column (L57-63). This matters for F2 "survives restart": without the fill-in, older papers have `in_library` NULL and `GET /api/papers`, which keeps only `in_library` true (papers.py L86), drops them. No test anywhere.
3. **Pruning keeps a shared PDF:** a PDF still used by another paper must survive pruning (README L54-55; cache.py L32). A pruner that deletes the file unconditionally survives all 360 tests.
4. **Pruning every 12 hours:** the periodic run, and the loop carrying on after a failed run (main.py L39-46; REQUIREMENTS.md L84). Can be tested by monkeypatching `asyncio.sleep` in app.main.
5. **Pruning race guard (cache.py L27-29):** a paper saved or reopened between the SELECT and the DELETE must be kept.
6. **Production mode (main.py L69-80):** `/` serves index.html with `Cache-Control: no-cache`, plus `/favicon.svg` and `/assets`. Also untested: the no-build explanation page (L89-95; INSTALL.md L338) and the warning when backend/.env exists (L25-28; INSTALL.md L163). The Playwright tests run in production mode but assert none of these.
7. **F3, AI fallback after arXiv:** when arXiv's answer is rejected or arXiv has no such id, the first pages should go to the language model (the LLM; README L256-258; papers.py L243-252). test_arxiv_id_of_a_cited_paper_is_not_trusted leaves `fake_llm.metadata` as None and never checks `metadata_requests`, so a refactor that skips the model whenever an arXiv id was found would pass.
8. **F3, upload during an arXiv pause:** the upload should skip the arXiv lookup, send no arXiv request and still return 201 (README L276-279). Only search is tested during the pause.
9. **PDF header check:** `looks_like_pdf` accepts up to 1 KB of junk before `%PDF-` and rejects it beyond that (fulltext.py L79-80). Not tested anywhere.
10. **Error paths in papers.py:**
    - GET `/{id}/pdf` when the paper records a PDF but the file is gone from disk (L391-393).
    - Attaching to a paper deleted mid-request: 404, and the stored file is removed (L381-382; fulltext.py L126-129).
    - Oversized, corrupt or encrypted files sent to the attach endpoint leave the paper unchanged. Only the "not a PDF" (415) case is tested for attach.
11. **Config:** the shipped default provider and model (see the last-but-one row above). Also settings validation: `CACHED_PAPER_DAYS=0` or `LLM_EFFORT=fast` should stop startup with a message naming the setting (INSTALL.md L183, L188-190). No backend test.

Lower priority: input validation on `POST /api/papers/open` (source "upload", missing external_id), and re-opening an unsaved paper through it refreshing `last_opened_at` (papers.py L125-126). Removing that refresh also survives all 360 tests, though the reader's follow-up GET refreshes it anyway.

## 4. Possible application bugs

None confirmed. What I checked:
- No test asserts behavior that contradicts the docs.
- Production mode behaves as main.py L60-74 says: JSON 404/405 for `/api`, index.html served with `no-cache`, favicon served.
- The backend accepts every value the UI allows: a 500-character title, years 1000 and 2100, a 20,000-character abstract, 5,000 authors, a 200-character filter.
- Saving an arXiv result without a DOI and then the OpenAlex copy correctly gives one entry.
- Git status is unchanged apart from your pre-existing untracked demo/ files, and the real backend/data was not touched.

One judgment call, not a documented contradiction: test_pdf_metadata_title_and_authors_are_used (test_upload.py L124-130) locks in that the title stored in the PDF's properties wins over the title visible on the page, even when it does not appear on the page (pdf.py L184-185). Elsewhere the app distrusts off-page titles from arXiv and from the model (papers.py L175-177, L196-202), and README L21 names only arXiv, Claude and layout heuristics as sources. When no model is available (README L170-171 says upload works without one), a leftover template title in the PDF properties would become the paper's title. Worth deciding whether that is intended before this test cements it.
