# Development log

A per-milestone record of what the coding agent (Claude Code) built, what the
`/code-review` pass found, and what was changed in response. Raw material for the
reflection report.

## M0 — Scaffold

**Built:** requirements/plan docs; FastAPI backend skeleton (uv, Python 3.11) with
`/api/health`; React + Vite + TS frontend with hash router, app shell, and dev proxy
`/api → :8000`; root `.gitignore` and `.env.example`.

**`/code-review high` findings (9) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | `.gitignore` covered `.env` / `*.env` but not `.env.local`, `.env.production` → a key could be committed | Fixed: added `.env.*` (keeping `!.env.example`) |
| 2 | Relative `DATA_DIR` resolved against the launch CWD → DB could land outside the ignored `backend/data/` | Fixed: validator anchors relative paths to `backend/` |
| 3 | Health check ran once; "backend unreachable" banner never cleared | Fixed: retry every 3 s until healthy, cancel on unmount |
| 4 | `apiFetch` called `res.json()` on any 2xx → raw `SyntaxError` on HTML/empty bodies | Fixed: content-type check, network errors wrapped in `ApiError` |
| 5 | Router ignored trailing slashes / unknown hashes silently | Fixed: normalise and rewrite to canonical hash |
| 6 | FastAPI 422 `detail` arrays were dropped from error messages | Fixed: format `loc: msg` list |
| 7 | `.env.example` documented nothing | Fixed (will grow each milestone) |
| 8 | CORS middleware unnecessary (dev proxy + same-origin prod) and its list-typed env var was a parse trap | Removed |
| 9 | Unused `navigate` export | Removed |

**Takeaway:** the agent's first-pass scaffold was functional but the review caught a
real secret-leak risk (#1) that the scaffold step didn't consider.

## M1: Paper Search (F1)

**Built:** arXiv client (Atom XML) and OpenAlex client (JSON, abstract rebuilt
from its inverted index); `GET /api/search?q&source&page&per_page`; search page
with source picker, example queries, result cards (title, authors, year, venue,
abstract, links, DOI), "Load more" paging, and session persistence.

**Design iteration before review:** the first arXiv query (`all:w1 AND all:w2`)
returned **zero** results for "attention is all you need" because arXiv drops
stopwords and an AND clause on a dropped word matches nothing. The agent tested
three query strategies against live arXiv and settled on
`ti:"phrase" OR abs:"phrase" OR (AND of title/abstract keywords minus stopwords)`.
The agent also caught that "Load more" could append duplicates and produce React key clashes.

**`/code-review high` findings (10) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | HTML tag-stripping regex `<[^>]+>` deleted real text: `p < 0.05 when n > 30` became `p 30` | Fixed: only strip real tags (letter right after `<`) |
| 2 | arXiv error feeds (HTTP 200 + error entry) were filtered out, so a bad query showed "Showing 0 of 1 results" | Fixed: detect and surface as HTTP 400 with arXiv's message |
| 3 | Punctuation-only query (`???`) built `ti:"" OR abs:""` | Fixed: return empty result set |
| 4 | "Load more" never disappeared on empty / duplicate pages or past the backend's page cap | Fixed: `exhausted` flag + `MAX_PAGE` |
| 5 | `paperKey` fell back to title, so two `(untitled)` papers collided | Fixed: fall back to URL/DOI, and dedupe page 1 too |
| 6 | arXiv throttle measured 3 s from *send* not *finish*; concurrent callers raced | Fixed: serialize requests, stamp after completion |
| 7 | New `httpx.AsyncClient` per request, so no connection reuse | Fixed: one pooled client, closed in app lifespan |
| 8 | Raw httpx exception text (`[Errno 8] nodename…`) shown to users | Fixed: log details server-side, show a friendly message |
| 9 | Source label hard-coded in two places | Fixed: shared `SOURCE_LABEL` |
| 10 | Page size defined in both `api.ts` and `SearchPage` | Fixed: single constant |

**Takeaway:** findings #1 and #2 were real, silent data bugs that the
happy-path manual test did not reveal. Both only show up on unusual inputs.

## M2: Local Library (F2)

**Built:** SQLAlchemy `Paper` model on SQLite (`backend/data/app.db`);
`GET/POST /api/papers`, `GET/DELETE /api/papers/{id}`, `GET /api/papers/keys`;
per-result "Save to library" button with saved state; Library page with filter,
open, and remove; paper detail page. A small `init_db` helper adds new nullable
columns so later milestones don't require deleting the database.

**Verified:** the Playwright script saved 2 papers, reloaded the page, filtered,
restarted the backend (data persisted), opened a detail page, deleted a paper,
and opened an unknown id.

**Self-caught before review:** the linter flagged a `setState` call inside an
effect on the detail page. The fix remounts the page per paper id with `key`.

**`/code-review high` findings (10) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | SQLite drops timezone; `created_at` serialized without `Z`, so "Saved at" showed hours off | Fixed: `UTCDateTime` TypeDecorator re-attaches UTC |
| 2 | Author filter ran `ILIKE` on JSON text, where `ü` is stored as `ü`, so "Müller" never matched | Fixed: Unicode-aware filtering in Python; JSON stored with `ensure_ascii=False` |
| 3 | SQLite `lower()` is ASCII-only, so "über" did not match "Über" | Fixed: `casefold()` + NFKC normalization |
| 4 | Saved-keys response could overwrite a save made while it was in flight | Fixed: merge instead of replace |
| 5 | In-flight list request could resurrect a just-deleted paper | Fixed: track deleted ids |
| 6 | Filter input allowed more than 200 chars, causing a backend 422 | Fixed: `maxLength={200}` |
| 7 | Column-migration helper silently skipped NOT NULL columns, so the first insert would fail | Fixed: fail fast at startup with a clear message |
| 8 | Same paper saved from arXiv and from OpenAlex created two rows | Fixed: dedupe on DOI and arXiv id vs. arXiv DataCite DOI |
| 9 | Saved-key format duplicated by hand | Fixed: shared `sourceKey()` |
| 10 | `err instanceof Error ? …` copied 6 times | Fixed: `errorMessage()` helper |

**Takeaway:** findings 1–3 are SQLite-specific behaviors (timezone and
ASCII-only `lower()`) that look correct in a quick English-only test. The
reviewer reproduced each one against a scratch database before reporting it.

## M3: PDF Upload and Processing (F3)

**Built:** PyMuPDF text extraction with best-effort metadata (largest-font title,
author lines between title and "Abstract", abstract section, venue-aware year);
arXiv-id detection on page 1 with an authoritative metadata lookup;
`POST /api/papers/upload`, `POST /api/papers/{id}/fulltext` (download an
open-access PDF), `POST /api/papers/{id}/pdf` (attach a PDF), `GET /api/papers/{id}/pdf`,
`PATCH /api/papers/{id}`; upload box (button + drag & drop), full-text status
panel, and metadata edit form.

**Heuristic tuning against 5 real PDFs** (2 ACL, 3 arXiv):

- The abstract ran into page-1 footnotes, so footnote and venue patterns now end it.
- The most-frequent-year rule picked *cited* years (BERT got 2018, FLARE got
  2022), so years next to venue words ("Proceedings of NAACL-HLT 2019") now take priority.
- LoRA's small-caps title had no spaces in the PDF text layer ("LORA:LOW-RANKADAPTATION…").
  The arXiv lookup fixes this case.

**Test-script bug (mine, not the app's):** Playwright's `text=Open` selector
matched the "OpenAlex" badge, so the test never navigated. Opening the page
directly and tracing network calls showed the app was fine.

**`/code-review high` findings (10) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | `PATCH {"authors": null}` stored NULL, so **every** later library list returned 500 | Fixed: null maps to `[]` |
| 2 | Author list capped at 200, so large-collaboration papers could not be edited | Raised to 10 000 |
| 3 | PDF ligatures (`ﬃ`) broke the arXiv title check, so correct metadata was discarded | Fixed: NFKC normalization, Unicode-aware comparison |
| 4 | A *cited* arXiv id on page 1 set the year, even when its metadata was rejected | Fixed: prefer the margin stamp (`[cs.CL]`); no year from unverified ids |
| 5 | Full-text fetch returned a stale paper snapshot that overwrote edits made during the download | Fixed: merge only full-text fields |
| 6 | Deleting a paper mid-download caused a 500 and left an orphaned PDF | Fixed: existence checks, `StaleDataError` handling, file cleanup |
| 7 | 50 MB hashing and file writes ran on the event loop | Fixed: moved to a thread pool |
| 8 | The "upload the PDF" hint created a *duplicate* entry | Fixed: new "Attach PDF" endpoint and button on the existing paper |
| 9 | Frontend hard-coded the 50 MB limit | Removed; the backend is the single source of truth |
| 10 | Per-paper lock dict grew without bound | Fixed: reference-counted locks |

**Found while verifying the fixes:** SQLite reused a deleted paper's id, so a
stale link could open a *different* paper. Fixed with `sqlite_autoincrement`.

**Takeaway:** the agent's heuristics looked right on the happy path. Testing
against real PDFs and an adversarial review both found failures
(ligatures, cited ids, nulls) that a demo would not reveal.

