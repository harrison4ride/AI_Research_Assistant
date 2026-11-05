# `/code-review high` on round 1's changes (hw2-initial..hw2-round1)

Run on 2026-11-04 as an evaluation lens; findings are recorded, not fixed, and become
part of round 2's feedback. The reviewer ran the 10 backend strict-xfail cases with
`--runxfail` and the 5 frontend `it.fails` tests as plain tests: every one fails today,
at the point matching the bug its reason names. One of them (row 1) asserts behavior
that the code appears to have chosen deliberately.

| # | File:line | Finding | Kind |
|---|-----------|---------|------|
| 1 | frontend/src/pages/LibraryPage.test.tsx:71 | The `it.fails` test treats "open-access link wins over the stored copy" as a bug, but `PaperCard` does this on purpose (`paper.pdf_url ?? localPdfHref`), and the same diff deleted the PaperCard test that pinned it | Wrong expectation (design choice marked as a bug) |
| 2 | frontend/src/test/setup.ts:27 | The new `afterEach` throws on any `console.error` or unmocked request, and Vitest applies the `it.fails` inversion after `afterEach`, so any such problem counts as the "expected failure" of all 5 `it.fails` tests | Infrastructure: expected failures can pass for an unrelated reason |
| 3 | frontend/e2e/upload-summary-chat.spec.ts:145 | In the zoom loop, `expect.poll(...).toBeGreaterThan(before - 25)` passes immediately on the old layout; no step waits for the new zoom | Timing-dependent (weak) |
| 4 | frontend/src/components/PaperCard.test.tsx:34 | "toggles the full abstract" now checks only the button label; an abstract that never expands passes | Regression: weakened while removing a CSS-class check |
| 5 | frontend/src/components/UploadBox.test.tsx:84 | The `dragging` assertions were dropped; nothing tests the drag-over highlight or its reset | Regression: behavior no longer tested |
| 6 | frontend/src/components/SectionsPanel.test.tsx:48 | The `level-2` check was replaced by a title check; nothing tests that subsections are indented | Regression: behavior no longer tested |
| 7 | frontend/src/test/fetchMock.ts:7 | `unanswered` is module-level and drained only in `afterEach`; a late request is blamed on the next test; duplicates `unhandled` | Order-dependent infrastructure |
| 8 | backend/tests/test_library.py:698 | The `older_database` fixture swaps only `db.engine`/`db.SessionLocal`; `assistant.py` and `cache.py` imported `SessionLocal` by name, so startup pruning and summary/chat saves still use the shared test database | Test checks less than it claims |
| 9 | backend/tests/test_upload.py:65 | The first-pages test dropped the 15,000-character bound and only checks that the last line is missing; sending 39,000 characters passes | Regression: weakened |
| 10 | backend/tests/test_summary.py:211 | In the private-address case, `downloads == 0` cannot detect repeated attempts, because the address check sends no request | Weak |

Observation for the report: findings 4, 5, 6, and 9 are regressions caused by round 1's
own fixes. Removing brittle CSS-class checks (and a vacuous bound) without replacing
them with an equivalent behavioral check left behavior untested.
