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

## M4: LLM Summaries and Q&A (F4, F5)

**Built:** Claude integration through the official `anthropic` SDK
(`claude-opus-5`, adaptive thinking, `effort` from `.env`, server-side refusal
fallbacks via `fallbacks: "default"`). The paper's full text goes in the system
prompt behind a prompt-cache breakpoint, so the summary and every Q&A turn share
one cached prefix. `POST /api/papers/{id}/summary` and
`POST /api/papers/{id}/chat` stream newline-delimited JSON (`meta`, `text`,
`reset`, `done`, `error`); results are saved only after a complete answer.
Q&A history is persisted per paper. Uploads use structured output
(`messages.parse`) to read metadata from the first pages. The UI has a Summary
panel, a chat panel with the assignment's five example questions, and a notice
when no API key is configured.

**How it was verified without an API key:** a local fake Messages API
(SSE replay) exercised normal answers, refusals, a mid-stream fallback switch,
and structured output. The recorded request bodies confirmed identical system
blocks across calls (cache-friendly), the fallback beta header, and that a
refused turn is left out of later history. **A real API call still needs a key.**

**Decision change:** the original plan included an OpenAI-compatible provider.
It was dropped in favor of one Claude integration (the Claude API guidance
advises against OpenAI-compatible shims), and `PLAN.md` was updated.

**Found during verification (before review):** the fake LLM returned another
paper's metadata. The title check correctly rejected the title, but the
authors and year were still merged. The merge is now all-or-nothing.
A stray file `backend/--app-dir` also got staged: the fake server took
`sys.argv[1]` as its log path. It was removed before commit.

**`/code-review high` findings (9) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | `messages.parse()` raises `ValidationError` on truncated or refused JSON, so the upload returned 500 and left an orphaned PDF | Fixed: catch everything in extraction; store the file only after metadata is final |
| 2 | Missing credentials raise `TypeError` (not `AnthropicError`), so the stream dropped instead of saying "set ANTHROPIC_API_KEY" | Fixed: detect and map to a clear message |
| 3 | Unexpected errors mid-stream (e.g. a DB error during save) dropped the connection with no error event | Fixed: catch-all sends an in-band `error` event |
| 4 | "Key set" check ignored the SDK's other credential sources (`ANTHROPIC_AUTH_TOKEN`, `ant` profile) | Fixed: `credentials_available()` mirrors the SDK lookup |
| 5 | Upload waited on a 90 s LLM call with 2 retries, up to ~5 min | Fixed: 45 s, no retries; heuristics take over |
| 6 | SQLite foreign keys were never enabled, so `ON DELETE CASCADE` did nothing and orphan chat rows were possible | Fixed: `PRAGMA foreign_keys=ON` per connection |
| 7 | A failed *regeneration* hid the saved summary behind partial text | Fixed: show the saved summary plus the error |
| 8 | Markdown link renderer passed react-markdown's `node` prop to `<a>`, and the components map was rebuilt per delta | Fixed |
| 9 | Chat auto-scroll yanked the user to the bottom while they reread history | Fixed: only follow when already at the bottom |

**Takeaway:** the happy path worked on the first try. Every finding concerns
*failure* paths (missing key, truncated output, concurrent delete), which a demo
never exercises and which an SDK's exception hierarchy does not fully cover.

## M5: Production Mode, Deployment, README

**Built:** FastAPI serves the built UI, so `make start` runs everything as one
process on :8000. Also added a `Makefile` (`install`, `dev`, `backend`, `frontend`,
`build`, `start`), a two-stage `Dockerfile` with `.dockerignore`, and a README
covering features, architecture, setup, configuration, the API, data flow, and
known limitations.

**Verified:** a Playwright run of the five demo-video steps (search, save, upload,
summary, question) against the production server (summaries and answers came from
the fake LLM). `make dev` start and stop were checked, along with the routing
behavior below. **Not verified:** the Dockerfile, because Docker was not installed.
The README says so.

**`/code-review high` findings (10) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | `docker run --env-file .env` lets a local `DATA_DIR` move data out of the volume | Fixed: README passes `-e DATA_DIR=/data` |
| 2 | My `/api/{path}` catch-all turned 405s into 404s and broke trailing-slash redirects | Fixed: removed it; serve `/`, `/favicon.svg`, and mount only `/assets` |
| 3 | `trap 'kill 0'` in `make dev` signals the whole process group | Fixed (see below) |
| 4 | `index.html` could be browser-cached after a rebuild, pointing at deleted asset hashes | Fixed: `Cache-Control: no-cache` on `/` |
| 5 | Docker `--env-file` keeps quotes, so a quoted key breaks auth in the container | Documented in the README |
| 6 | HEAD/OPTIONS and bare `/api` fell through to the static mount (non-JSON 404) | Fixed by #2 |
| 7 | uv download cache was left inside the image | Fixed: `uv sync --no-cache` |
| 8 | Unpinned `uv:latest` image | Fixed: pinned `0.11.17` (tag verified on GHCR) |
| 9 | Dev backend also served a stale `dist/` on :8000 | Fixed: `SERVE_FRONTEND=false` in dev targets |
| 10 | `make install` used `npm install`, which can rewrite the lockfile | Fixed: `npm ci` |

**Finding #3 proved itself during verification:** sending TERM to `make dev`
from the agent's non-interactive shell killed *that shell*, because it shared
make's process group. The fix sends signals only to the two server jobs (each started with `exec`),
and a rerun confirmed both servers stop while the caller survives.

**Takeaway:** in this milestone the reviewer mostly caught *operational* issues
(caching, signals, container configuration) rather than logic bugs. These problems
appear only after deployment, which is why they are easy to miss.

## M5 Follow-Up: Docker Removed, Setup Script and INSTALL.md

**What happened:** in M5 the agent (Claude Code) added a Dockerfile as the
"deployment config", although it had confirmed at the start of the session that
Docker was **not installed**. The Dockerfile could never be built or tested; the
README could only say "not verified", and 4 of the 10 M5 review findings were
spent on it. The user challenged this and clarified that "configure deployment"
means the libraries and environment the app needs. The Dockerfile,
`.dockerignore`, and the README's Docker section (including the Docker caveats from
M5 findings 1 and 5) were removed.

**Built instead:** `scripts/setup.sh` and `INSTALL.md`.

- The script checks uv and Node.js (the exact range Vite 8 accepts), runs
  `uv sync --locked` and `npm ci`, creates `.env` with mode 600, checks every
  `.env` value by loading the backend, and asks for the API key with hidden input.
  `--check` reports without changing anything. It is written for macOS's bash 3.2.
- `INSTALL.md` covers supported platforms, required tools with versions, every
  locked package, all environment variables, network hosts, manual setup, running
  without `make`, verification, troubleshooting, and uninstalling.

**Agent mistakes during testing (test harness, not the app):** piping the API key
into the script before the prompt appeared looked like a failed save, because
`read -s` discards typed-ahead input by design; `expect` fixed the test. A blank exit
code came from zsh lacking bash's `PIPESTATUS`.

**Verification workflow:** four independent auditors (fact-check against code
and lockfiles, script stress test, a newcomer following the guide literally at a
path with spaces, and cross-document consistency), each followed by a skeptic that
tried to refute every finding. 31 findings, 29 confirmed, 2 uncertain.

| Confirmed problem | Fix |
|-------------------|-----|
| Code blocks had trailing `# comments`. macOS's interactive zsh does not treat `#` as a comment, so pasting failed, and in the Uninstall block the comment words became extra `rm -rf` arguments | No inline comments in any code block; explanations moved to prose |
| `brew install node@22` (keg-only) does not put `node` on PATH, so setup kept failing | Recommend `brew install node` or nvm; explain `node@22` linking |
| Troubleshooting blamed "lockfile needs updating" on an old uv; the real cause is an edited `pyproject.toml` (tested uv 0.3.5–0.11.17) | Split into two accurate rows |
| Vite silently moved to port 5174 when 5173 was busy, so the documented URL reached another app | `strictPort: true`; Vite now fails with "Port 5173 is already in use" |
| A broken `node`/`npm`/`uv` aborted the script under `set -e` or passed as "✓ npm " | Guarded version probes with clear messages |
| Key detection hand-parsed `.env` and misread CRLF, `export`, spaces around `=`, and inline comments; the prompt could append a duplicate key line | Ask the app's own settings loader; save with `python-dotenv` (now a direct dependency) |
| `--check` passed after an interrupted install or with an invalid `.env` value | `--check` loads the backend and runs `npm ls` |
| An exported `CDPATH` corrupted the script's root path | `CDPATH='' cd ... >/dev/null` |
| An unreadable `.env` asked for the key, then crashed and lost it | Check permissions first, with a clear message |
| Run commands left the shell in `backend/` or `frontend/` | Subshells `(cd x && ...)`; "run from the project folder" |
| Docs said uv always downloads Python; it uses an installed 3.11 first | Reworded |
| Four settings (`LLM_MAX_TOKENS`, `LLM_HISTORY_MESSAGES`, `ANTHROPIC_BASE_URL`, `FRONTEND_DIST`) undocumented; a second `backend/.env` silently overrode the root `.env` | Documented all settings; `config.py` reads only the root `.env` |
| Network host list was wrong for a firewall allow-list; uv/npm caches unmentioned; smaller wording errors | Corrected |

**Uncertain, not changed:** an unreadable `.env` is unlikely in practice (now
handled anyway), and `make dev` ignores a SIGINT sent only to make's PID (Ctrl+C
in the terminal and SIGTERM both stop it; the docs say to use Ctrl+C).

**`/code-review high` after the workflow fixes (9 more findings), all fixed:**

| # | Finding | Fix |
|---|---------|-----|
| 1 | The script's key check ignored `ANTHROPIC_AUTH_TOKEN` and `ant` login profiles, which the app accepts | Reuse the app's `credentials_available()` |
| 2 | An empty `ANTHROPIC_API_KEY` exported in the shell overrode `.env`, so a saved key was reported as "could not save" | `env_ignore_empty=True` in the settings |
| 3 | A `backend/.env` from the old config would be silently ignored | Warning in the script and at backend startup |
| 4 | `--check` claimed to change nothing but created `DATA_DIR` by importing the app | Validate only the settings; nothing is created |
| 5 | Saving the key replaced a symlinked `.env` with a regular file | `follow_symlinks=True` |
| 6 | After installing uv, only `~/.local/bin` was added to PATH | Also `$XDG_BIN_HOME` and `$UV_INSTALL_DIR` |
| 7 | Numeric settings accepted nonsense (`LLM_HISTORY_MESSAGES=-1` sent the whole history) | Range constraints in `config.py` |
| 8 | `--check` could not detect packages drifting from `uv.lock` | `uv sync --locked --check` |
| 9 | Failures imported the app twice to print the error | Capture the output once |

**Takeaway:** install documentation is easy to get *plausibly* wrong. Several
errors (keg-only Homebrew formulas, zsh comment handling, Vite's port fallback,
uv's Python preference) were only caught because the agents actually ran the
steps instead of reading them.

## Summary Across Milestones

| Milestone | Review findings | Fixed | Documented, not changed |
|-----------|-----------------|-------|-------------------------|
| M0 Scaffold | 9 | 9 | 0 |
| M1 Search | 10 | 10 | 0 |
| M2 Library | 10 | 10 | 0 |
| M3 PDF upload | 10 | 10 | 0 |
| M4 LLM | 9 | 9 | 0 |
| M5 Deployment | 10 | 9 | 1 (Docker quoting; Docker later removed) |
| M5 follow-up (setup script) | 29 confirmed by workflow + 9 from `/code-review` | 38 | 0 |

Recurring pattern: the first implementation of each milestone passed its
happy-path test. The review then found problems on unusual inputs (Unicode,
ligatures, nulls), under concurrency (delete mid-download, stale responses),
on failure paths (missing key, truncated output), and in deployment details.

