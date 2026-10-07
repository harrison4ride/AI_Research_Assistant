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

