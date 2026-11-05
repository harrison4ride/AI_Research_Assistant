# `/code-review high` on the initial test suite (hw2-baseline..hw2-initial)

Run on 2026-11-04 as an evaluation lens. Findings are recorded, not fixed, so the
initial suite stays an honest snapshot; they are inputs to the improvement rounds.

| # | File:line | Finding | Rubric category |
|---|-----------|---------|-----------------|
| 1 | frontend/e2e/support/app.ts:31 | `emptyLibrary()` deletes only papers listed by `GET /api/papers` (saved ones); papers opened but never saved, and their chats, stay in the shared e2e database, so "each test starts empty" does not hold | FLAKY (order-dependent) |
| 2 | frontend/src/test/fetchMock.ts:93 | Unregistered requests get a 501 and are only recorded in `unhandled`; nothing asserts it is empty, so a wrong or new endpoint passes silently | WEAK (test infrastructure) |
| 3 | backend/tests/test_upload.py:55 | `assert len(first_pages) <= 15000` is vacuous: the sample PDF has about 2 KB of text, so the 15,000-character cap is never exercised | WEAK |
| 4 | backend/tests/test_chat.py:139 | The 101-character `model` case passes because of the unknown-model check, not the `max_length=100` validation it targets | WRONG (passes for the wrong reason) |
| 5 | backend/tests/conftest.py:101 | Network and LLM fakes patch `get_client`/`stream_reply` per module; a new module importing them directly would bypass the fakes | Infrastructure robustness |
| 6 | backend/tests/support/e2e_server.py:54 | The fake arXiv feed contains a real `arxiv.org` PDF link; opening that result in an e2e test would download from the internet | FLAKY risk (hermeticity) |
| 7 | backend/tests/test_library.py:273 | "survives a restart" reuses the same engine and SQLite file and exits the fixture's client twice; it never restarts anything that holds data | WEAK |
| 8 | frontend/src/pages/LibraryPage.test.tsx:65 | Debounce test uses real timers; a slow re-render over 200 ms makes it fail | FLAKY risk (timing) |
| 9 | backend/tests/conftest.py:77 | Per-test reset patches private module globals one by one and misses some (`claude_code._background`, `fulltext._locks`, `http._client`) | Infrastructure robustness |
| 10 | backend/tests/support/e2e_server.py:101 | Copies conftest's settings-isolation code; the two copies can drift | Maintainability |
