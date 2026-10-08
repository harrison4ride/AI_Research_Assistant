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

## Follow-Up: Claude Code as the Default LLM Provider

**Request:** the user asked for a default option that uses the Claude Code installed on
the machine instead of requiring an Anthropic API key.

**Research first (3-agent workflow, no model calls):** two agents read the Claude Code
and Agent SDK docs; a third installed `claude-agent-sdk` 0.2.164 in a scratch
environment and read its source plus the installed CLI's `--help`. The installed source
was treated as ground truth, and it overturned several documentation-based assumptions:

- The Python Agent SDK bundles its own 235 MB Claude Code (2.1.292) and prefers it
  over the user's installed 2.1.293.
- It passes the system prompt as a command-line argument: a 400K-character paper with
  non-ASCII text fails with "Argument list too long" (tested: ARG_MAX is 1 MiB).
- In non-interactive mode an exported `ANTHROPIC_API_KEY` silently overrides the
  user's Claude Code login.
- `--tools ""` does not remove MCP tools, and `@path` in a prompt is expanded into the
  file's contents unless the message is marked `client_composed`.
- One docs summary claimed `allowed_tools=[]` disables tools and that
  `claude auth status` returns `authenticated`; the source showed neither is true.

**Design:** call the local `claude` CLI directly (`backend/app/services/claude_code.py`)
instead of the SDK: no 235 MB dependency, and full control over each point above.
The paper goes in a temp file (`--system-prompt-file`); the prompt goes over stdin as
a `client_composed` message; tools, MCP, settings, CLAUDE.md, hooks, slash commands and
saved sessions are off (`--safe-mode`, `--strict-mcp-config`, `--setting-sources ""`,
and more); `ANTHROPIC_API_KEY` is removed from the child environment; it runs in a
fresh temp folder (the prompt file sits outside its working directory) in its own
process group.

**Real probes:** the first two probes (tiny prompts) failed with "You've reached your
Fable limit": the user's Claude Code default model was Claude Fable 5.1, and its usage
limit was reached. That is why the provider defaults to `CLAUDE_CODE_MODEL=opus` and turns usage-limit
errors into a clear message. With `opus`, the probes confirmed streaming, the lockdown
(`tools=[]`, no MCP, no slash commands, no session files), and that `@/etc/hosts`
stayed literal. A real upload, summary, and two follow-up questions on a 24-page paper
then worked; the second question read 25,482 tokens from cache.

**Agent mistake during testing:** the test server failed to bind port 8000 because
the user's own server was already running there. The agent did not notice the bind error, so
its test requests went to the user's server and wrote a test paper, summary, and chat
into the user's real library. Its `pkill -f "uvicorn app.main:app"` then also stopped
the user's server. The agent removed exactly those test records (matched by PDF hash and
timestamps) and now tests on a dedicated port, checks that the port is free, and stops only
the process it started.

**Found by a fake `claude` script (failure paths):** a timeout took 30 s instead of 2 s,
because killing the CLI left a helper process holding its output pipes. The fix runs the CLI in its own
process group and kills the whole group. A double period in the usage-limit message
was also fixed.

**Verification workflow (4 auditors + 4 skeptics, fake CLI except 3 tiny real calls):**
27 findings, 26 confirmed, 1 refuted. The important ones:

| Confirmed problem | Fix |
|-------------------|-----|
| Claude Code adds the user's **account email** and environment details (cwd, OS, shell, date) to every request; no flag removes it. Answers were rendered with remote images allowed, so a malicious PDF could try to make the model leak the email in an image URL | The UI never loads images from model output (rendered as text), a CSP `img-src 'self'` backs that up, and the prompt tells the model never to repeat account or environment details. Docs now state this limit instead of claiming a "plain text model" |
| Chat history was flattened with plain `<user>`/`<assistant>` tags, so paper text quoted in an old answer could close the transcript and pose as the user's new question | Random per-request boundary tags; the transcript is marked as context only |
| The read loop ended only at stdout EOF: a helper holding the pipe made a finished answer wait for the timeout, or be discarded | Stop at the `result` event; poll for the CLI's exit (asyncio's `wait()` also waits for pipes); then SIGTERM, then SIGKILL, for the whole process group |
| macOS returns EPERM (not ESRCH) for a zombie-only process group, which masked cancellations | Handled |
| `stdin` writes had no deadline and broke on large payloads; unexpected field types or a >16 MB line raised exceptions that made **PDF uploads return 500** | Background writer, `ensure_ascii=False`, type-checked event parsing, oversized lines skipped, metadata extraction never raises |
| Each call left an empty scratch-folder tree in `/tmp` | `CLAUDE_CODE_TMPDIR` points into the run's temp folder |
| No minimum version, although the lockdown flags need Claude Code 2.1.248+ | Version check in the status, with an update hint |
| A wrong `CLAUDE_CODE_PATH` was reported as "not installed"; relative paths broke | Specific hint; relative paths anchored like `DATA_DIR` |
| Docs and hints: "rechecks within 30 seconds" was false; `.env` hints omitted "restart the backend"; backticks shown literally | The page rechecks when you return to the tab; hints fixed; `code` rendered |

**`/code-review high` after the workflow fixes (9 findings), all fixed:** an old CLI without
`auth status --json` was reported as ready (the version is now checked first, and a
non-zero exit means not ready); the metadata-extraction prompt lacked the
untrusted-input and privacy rules; a model-written link with a query string could
still carry data out on a click (now shown as text with the full URL); "not logged in"
was cached for 10 s (now 3 s) and every tab focus could start two CLI processes (now
only while unavailable, debounced, with one shared check); uploads waited on Claude
Code even when it was logged out (now gated on the status, 45 s limit); an exported
`ANTHROPIC_BASE_URL` would have routed the user's login to that endpoint (now removed
for the child); a finished answer waited up to ~9 s for the CLI to exit (shutdown now
runs in the background); a stale `/config` response could overwrite a newer one.

## M6: Reader, Section Outline, Model Menu

**Request:** the user pointed out that questions could only be asked about saved
papers, and asked for clicking a search result to open an in-app page with the PDF,
the paper's structure with one-sentence summaries on the left, and Q&A on the right;
then for switching models. The user chose section summaries **on click** (not
automatic) and the **same reader for library papers**.

**Built:**
- Papers opened from search are stored as unsaved (`in_library = false`), so Q&A
  works at once; saving keeps the chat and outline. Unsaved papers not opened for
  `CACHED_PAPER_DAYS` are pruned (at startup and every 12 hours).
- The section outline comes from PDF bookmarks or detected headings (including
  ACL-style split numbers). "Summarize sections" asks the model for one sentence each.
- The 3-column reader uses react-pdf (lazy-loaded), with section jumps and an
  active-section highlight.
- A model menu (Opus, Sonnet, Haiku, Fable, Claude Code default; or the API models)
  is validated server-side before anything reaches the CLI or API.
- OpenAlex became the default search source.

**Mid-milestone discussion: arXiv.** Searches started failing with 429 and 503
after a day of tests and verification agents had all queried arXiv from one IP
address (each backend process has its own 3 s throttle). arXiv's status page showed
the API up, so the limit was per-IP. The user asked about Google Scholar instead.
It has no API, its `robots.txt` disallows `/scholar`, and it shows snippets instead of
abstracts, so OpenAlex (0.35 s, official API) became the default. The app also got
an arXiv cooldown that honors `Retry-After`, a 10-minute search cache, and a
"Search OpenAlex instead" button.

**Verification workflow (4 auditors + 4 skeptics, fake CLI):** 43 findings, all
confirmed. The most significant:

| Confirmed problem | Fix |
|-------------------|-----|
| react-pdf's default Suspense mode hid the whole viewer whenever a page loaded, and a PDF load error **blanked the entire app** | `suspense={false}` on Document and Page, plus an error boundary around the lazy viewer |
| Page offsets were measured from `<body>`, not the PDF scroller, so jumps overshot by ~180 px and the highlight lagged | `.pdf-scroll` is positioned; offsets are now relative to it |
| Bookmark positions came out mirrored for explicit (non-LaTeX) destinations, and `/Fit` jumped to the page bottom | Positions read according to the destination kind |
| A model reply that skipped one section shifted every later summary onto the wrong heading | Summaries keyed by section number; incomplete replies are rejected, keeping the old ones |
| Section titles from untrusted PDFs went into the prompt as the user's own words | Passed as a JSON data block marked as paper content; titles and outline size capped |
| A PDF link (or redirect) could make the backend request localhost or LAN addresses | Only http(s) to public addresses, re-checked on every redirect |
| Model-named headings with "fi"/"fl" ligatures were never located; the paper title matched before the real heading | Ligature-normalized, number-stripped matching ranked heading > prefix > mention |
| Outline extraction was O(n²) and bookmark lists unbounded (a crafted PDF yielded a 31 MB outline) | Per-page joining; at most 120 entries and 200 characters per title; outline column deferred |
| A PDF replaced, or the paper deleted, during a minutes-long summary call gave stale data or a 500 | Re-check after the call (404 or 409); per-paper lock for outline extraction |
| "Saved" date and library order used the first-opened time | New `saved_at` column (backfilled) |
| The layout broke between 1100 and 1250 px; a section click in the stacked layout scrolled off-screen; zoom lost the reading place; "Back" after a direct load left the app | All fixed |
| Docs: pruning only ran at startup, Node message blamed Vite, model and verification wording outdated | Fixed |

**Agent mistakes found while fixing (test-confirmed):** the first version of
`locate_headings` matched the paper's own title on page 1 before the numbered heading;
and after the reading-position fix, a leftover 0.02-page tolerance still highlighted
"4.1" right after jumping to "4 Experiments". Both were found by re-running the UI
check after the fix rather than assuming it worked.

**`/code-review high` after the workflow fixes (10 findings), all fixed:**

| # | Finding | Fix |
|---|---------|-----|
| 1 | Pruning selected stale unsaved papers, then deleted them by id: a paper saved or reopened in between was still deleted | The DELETE repeats the staleness conditions; the PDF is removed only if a row was deleted (tested by reopening a paper between select and delete) |
| 2 | The address check resolved the PDF host, then httpx resolved it again, so a DNS answer that changed in between (rebinding) could still reach a private address | The download connects to the vetted IP, with the original `Host` header and TLS server name |
| 3 | Searches queued behind arXiv's 3 s throttle sent their request even after the one before them had started a cooldown | The cooldown is re-checked after acquiring the throttle lock (3 concurrent searches during a 429 now make 1 call) |
| 4 | The search cache lowercased queries, but OpenAlex treats uppercase `AND`/`OR`/`NOT` as operators | Case preserved; only whitespace is collapsed |
| 5 | "Back" counted hash changes, so after a reload, or after browser back and forward, it could leave the app | Each history entry stores its depth in `history.state`, which survives reloads and back/forward |
| 6 | Every scroll event re-rendered the whole reader, including the PDF and the chat | Position updates at most once per frame and only on change; the viewer, chat, and summary panels are memoized |
| 7 | Rendered PDF pages were never released, so a long paper kept every page canvas in memory | Only pages near the viewport keep a canvas (4 of 12 at the end of ResNet); unloaded pages keep their measured height, so scrolling does not jump |
| 8 | The outline-summary request read the whole PDF before the minutes-long model call and held it in memory | The PDF is read after the call, when headings are located |
| 9 | A failed outline load left its error on screen after a later load succeeded | Cleared on success |
| 10 | While a paper loaded, the top navigation kept the previous paper's Search/Library state | The state is tied to the paper id; no tab is marked until the paper loads |

**Tests after the fixes:** the reader, section-jump, and navigation UI checks in
headless Chrome (fake Claude CLI, isolated port and data folder) and a backend
script covering open-without-save, model validation, outline summaries,
pruning under a race, the search cache key, and the arXiv cooldown race all passed,
with no browser console errors.

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
| Follow-up: Claude Code provider | 26 confirmed by workflow + 9 from `/code-review` | 35 | 0 |
| M6 Reader and model menu | 43 confirmed by workflow + 10 from `/code-review` | 53 | 0 |

Recurring pattern: the first implementation of each milestone passed its
happy-path test. The review then found problems on unusual inputs (Unicode,
ligatures, nulls), under concurrency (delete mid-download, stale responses),
on failure paths (missing key, truncated output), and in deployment details.


## Fix: "The Page Won't Open" (User Report)

**Report:** after running the setup script, the user could not open the app.

**Diagnosis:** nothing was listening on ports 8000 or 5173, so the servers were
not running. Starting `make dev` showed two more problems in headless Chrome:

- Vite bound only the IPv6 loopback `[::1]:5173` (its default `localhost` host on
  macOS), while the backend bound only IPv4 `127.0.0.1:8000`. So
  <http://127.0.0.1:5173> was refused, even though <http://localhost:5173> worked.
- In development mode, <http://localhost:8000> returned a bare JSON 404, which
  looks like a broken app.

**Fix:** Vite now binds `127.0.0.1`, like the backend, and port 8000 shows a page
that explains where the app is. INSTALL.md gained two troubleshooting rows.

**`/code-review high` findings (6) and resolution:**

| # | Finding | Action |
|---|---------|--------|
| 1 | **Regression from this fix:** with Vite on `127.0.0.1`, `strictPort` no longer notices another program on `[::1]:5173`, and browsers would open *that* program at `localhost:5173` | Fixed: a Vite plugin probes `[::1]:5173` and refuses to start if it is taken (tested with a dummy listener) |
| 2 | The "not built yet, run make start" hint was wrong when `FRONTEND_DIST` points elsewhere | Fixed: the hint names the checked directory and `FRONTEND_DIST` |
| 3 | A `dist` folder without `index.html` or `assets/` crashed startup or returned 500 | Fixed: requires both; otherwise the hint page shows (tested with 4 bad folders) |
| 4 | INSTALL.md row blamed development mode for every "API server" page | Fixed: covers both cases |
| 5 | "Keep the terminal open... `make dev`" confused readers using two terminals | Fixed wording |
| 6 | Dev URL markup duplicated | Fixed: one constant |

**Takeaway:** the first fix for a networking bug introduced a subtler
networking bug, and the review caught it before commit.
