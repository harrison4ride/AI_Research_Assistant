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

