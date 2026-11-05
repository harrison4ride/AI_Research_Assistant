# Held-out seeded faults (P0)

Written on 2026-11-04 before any test existed, from the code at tag `hw2-baseline`.
The patches are in `tools/faults/`; no test-writing agent is shown them.
A fault counts as detected when at least one test that passes on the clean app fails on the faulty app.

| ID | Layer | Origin | Fault | Intended behavior it violates |
|----|-------|--------|-------|-------------------------------|
| B01 | backend | history (DEVLOG M1 #1) | OpenAlex HTML-tag stripping deletes text between '<' and '>' | F1: search results show the abstract; text such as 'p < 0.05 when n > 30' must survive |
| B02 | backend | history (DEVLOG M1 design note) | arXiv query builder keeps stopwords in the AND clause | F1: 'attention is all you need' must find the paper; arXiv drops stopwords, so an AND on one matches nothing |
| B03 | backend | history (DEVLOG M1 #2) | arXiv error feeds (HTTP 200 with an /api/errors entry) are returned as search results | F1 error handling: a rejected query must surface as an error, not as a fake paper |
| B04 | backend | history (DEVLOG M2 #8) | Duplicate detection ignores DOIs, so the same paper saved from arXiv and OpenAlex becomes two entries | F2: saving a paper that is already in the library returns the existing entry |
| B05 | backend | history (DEVLOG M3 #1) | PATCH with authors=null stores NULL, after which reading the paper fails with 500 | F3: the user can correct extracted metadata; clearing authors must not break the paper |
| B06 | backend | new | Library filter no longer matches author names | F2: the library filter matches title, author, or abstract (README, LibraryPage placeholder) |
| B07 | backend | new | PDF signature check is off by one: a file that starts with %PDF- is rejected as not a PDF | F3: uploading a normal PDF works |
| B08 | backend | new | Q&A history is sent to the model newest-first | F5: follow-up questions are answered with the earlier turns as context, in order |
| B09 | backend | new | Prompt uses the abstract whenever one exists, even when the full text is available | F4: the summary must be based on the paper's content, not only its metadata |
| B10 | backend | new | Cache cleanup also deletes saved library papers that were not opened recently | F2: saved papers persist; only papers opened from search and never saved are pruned |
| B11 | backend | new | Search cache key ignores the source, so switching arXiv/OpenAlex returns the other source's cached results | F1: results come from the selected search source |
| B12 | backend | new | Library list includes papers that were only opened for reading, never saved | F2: the library shows the papers the user saved |
| F01 | frontend | history (DEVLOG M1 #5) | paperKey falls back to the title before the URL/DOI, so different untitled papers collide | F1: every search result keeps its own identity (save state, list keys) |
| F02 | frontend | history (DEVLOG M0 #6) | Validation errors (FastAPI 422 detail arrays) lose their message; only the status text is shown | Error handling: the user sees what was wrong with the request |
| F03 | frontend | history (DEVLOG M0 #5) | Routes with a trailing slash (#/library/, #/paper/3/) fall back to the search page | Navigation: a bookmarked or refreshed URL opens the same page |
| F04 | frontend | new | Stream reader drops the last event when the stream does not end with a newline | F4/F5: every streamed event, including the final one, is delivered |
| F05 | frontend | new | A 'reset' event (fallback model restarted) does not clear the partial text | F4/F5: after a fallback, only the new model's answer is shown |
| F06 | frontend | new | The question is put back into the input after a successful answer instead of after a failure | F5: after an answer the input is empty; after a failure the question is kept for retry |

Total 18: 12 backend, 6 frontend; 8 re-introduced from HW1 history, 10 new.
