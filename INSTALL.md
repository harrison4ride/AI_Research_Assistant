# Installation Guide

This guide lists everything the AI Research Assistant needs and how to install it.
The fastest path is the setup script, which checks the requirements, installs the
packages, and creates the configuration file:

```bash
git clone https://github.com/harrison4ride/AI_Research_Assistant.git
cd AI_Research_Assistant
./scripts/setup.sh
make dev
```

Then open <http://localhost:5173>.

Run every command in this guide from the **project folder**, the folder that
contains this file. The code blocks contain only commands, so you can paste them
into any shell.

## Supported Platforms

| Platform | Status |
|----------|--------|
| macOS (Apple Silicon) | Tested (macOS 27, arm64) |
| macOS (Intel), Linux | Expected to work: the same tools and packages exist there. Not tested. |
| Windows | Use WSL 2 (Ubuntu) and follow the Linux steps. Not tested. The setup script and `make` need a Unix shell. |

## Required Software

Install these tools first. The setup script checks each one and tells you what is
missing.

| Tool | Version | Used for | How to install | Check |
|------|---------|----------|----------------|-------|
| [uv](https://docs.astral.sh/uv/) | Recent release (tested with 0.11.17) | Provides Python 3.11 and installs the backend packages | `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `brew install uv` | `uv --version` |
| [Node.js](https://nodejs.org) | 20.19 or later in the 20.x line, or 22.12 or later (tested with 22.22.0) | Builds and serves the frontend | Installer from nodejs.org, `brew install node`, or `nvm install 22` | `node --version` |
| npm | Comes with Node.js (tested with 10.9.4) | Installs the frontend packages | Included with Node.js | `npm --version` |
| git | Any | Cloning the repository | `xcode-select --install` (macOS) or `sudo apt install git` | `git --version` |
| make | Any (optional) | The `make dev` / `make start` shortcuts | `xcode-select --install` (macOS) or `sudo apt install make` | `make --version` |

The Node.js range comes from Vite 8, which requires `^20.19.0 || >=22.12.0`.
Node.js 21 and Node.js 22.0 to 22.11 are not supported. With Homebrew, prefer
`brew install node`: the versioned `node@22` formula does not put `node` on your
PATH unless you also run `brew link --overwrite node@22`.

You do **not** need to install these separately:

- **Python 3.11.** uv uses a Python 3.11 that is already installed, or downloads
  one if there is none (the version is pinned in `backend/.python-version`). uv
  never changes a system Python: the packages go into `backend/.venv`.
- **A database server.** The app uses SQLite, which is built into Python. The
  database is a single file, `backend/data/app.db`, created on first start.
- **PDF libraries.** PyMuPDF ships prebuilt wheels that include everything it needs.

## Accounts and API Keys

| Key | Required? | What it enables | Where to get it |
|-----|-----------|-----------------|-----------------|
| `ANTHROPIC_API_KEY` | Required for summaries and Q&A | Paper summaries (F4), questions about a paper (F5), and reading metadata from uploaded PDFs | <https://console.anthropic.com/> (API usage is billed by Anthropic) |
| `OPENALEX_EMAIL` | Optional | Puts OpenAlex searches in its "polite pool" | Any email address you own |
| `OPENALEX_API_KEY` | Optional | Raises OpenAlex's free daily quota | <https://openalex.org/settings/api> |

Without an Anthropic key, search, the library, and PDF upload still work. The paper
page then shows a notice and disables the Summary and Q&A buttons.

## What Gets Installed

The project's packages install inside the project folder. uv and npm also keep
download caches in your home directory, shared with your other projects.

| Location | Contents | Size (approx.) |
|----------|----------|----------------|
| `backend/.venv/` | Python packages | 130 MB |
| `frontend/node_modules/` | JavaScript packages | 90 MB |
| `backend/data/` | Created at runtime: the SQLite database and stored PDFs | Grows with your library |
| `~/.local/share/uv/python/` | Python 3.11, only if uv had to download it | 85 MB |
| `~/.cache/uv/` | uv's package download cache | 100 MB |
| `~/.npm/` | npm's package download cache | 30 MB |

### Backend Packages (Python)

Exact versions are locked in `backend/uv.lock`; `uv sync --locked` installs exactly these.

| Package | Locked version | Purpose |
|---------|----------------|---------|
| fastapi | 0.142.2 | Web framework for the `/api` endpoints |
| uvicorn[standard] | 0.54.0 | Web server that runs the app |
| pydantic-settings | 2.15.0 | Reads and validates the settings in `.env` |
| python-dotenv | 1.2.4 | Parses `.env`; the setup script also uses it to save your API key |
| sqlalchemy | 2.1.4 | Database access for the SQLite library |
| httpx | 0.28.1 | Calls arXiv and OpenAlex, downloads open-access PDFs |
| python-multipart | 0.0.32 | Parses PDF uploads |
| pymupdf | 1.28.2 | Extracts text and layout from PDFs |
| anthropic | 1.12.0 | Official client for the Claude API |

### Frontend Packages (JavaScript)

Exact versions are locked in `frontend/package-lock.json`; `npm ci` installs exactly these.

| Package | Locked version | Purpose |
|---------|----------------|---------|
| react, react-dom | 19.3.0 | User interface |
| react-markdown | 10.1.0 | Renders the model's Markdown answers |
| remark-gfm | 4.0.1 | Tables and lists in those answers |
| vite | 8.3.3 | Development server and production build (dev only) |
| @vitejs/plugin-react | 6.1.2 | React support for Vite (dev only) |
| typescript | 6.0.3 | Type checking during the build (dev only) |
| oxlint | 1.87.0 | Linter, `npm run lint` (dev only) |
| @types/react, @types/react-dom, @types/node | 19.3.0, 19.3.0, 24.19.1 | Type definitions (dev only) |

## Environment Variables

Settings live in one `.env` file in the project root. The setup script creates it
from `.env.example` with owner-only permissions, because it holds your API key.
`.env` is git-ignored; never commit it. A variable set in your shell overrides the
same variable in `.env`, unless the shell variable is empty. Earlier versions also
read `backend/.env`; that file is now ignored, and the app warns if it exists.

Write one `NAME=value` per line, for example `ANTHROPIC_API_KEY=sk-ant-...`. Restart
the backend after changing `.env`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | none | Claude API key (see above) |
| `ANTHROPIC_BASE_URL` | Anthropic API | Alternative API endpoint, such as a proxy |
| `LLM_MODEL` | `claude-opus-5` | Claude model used for summaries, answers, and metadata |
| `LLM_EFFORT` | `medium` | How much the model thinks: `low`, `medium`, `high`, `xhigh`, `max` |
| `LLM_MAX_TOKENS` | `32000` | Upper limit on thinking plus answer tokens per response |
| `LLM_MAX_PAPER_CHARS` | `400000` | Paper text sent to the model, about 100K tokens; longer papers are cut off |
| `LLM_HISTORY_MESSAGES` | `20` | Earlier Q&A messages sent with each new question |
| `LLM_EXTRACT_METADATA` | `true` | Let Claude read an uploaded PDF's first pages for title, authors, year, and abstract |
| `OPENALEX_EMAIL`, `OPENALEX_API_KEY` | none | Optional OpenAlex identification and quota (see above) |
| `MAX_PDF_MB` | `50` | Size limit for uploaded and downloaded PDFs |
| `DATA_DIR` | `backend/data` | Where the database and PDFs are stored; relative paths are resolved against `backend/` |
| `SERVE_FRONTEND` | `true` | Whether the backend also serves the built UI; `make dev` sets it to `false` |
| `FRONTEND_DIST` | `frontend/dist` | The built UI that the backend serves; relative paths are resolved against `backend/` |

An invalid value (for example `LLM_EFFORT=fast`, or `LLM_MAX_TOKENS=0`) stops the
backend at startup with a message naming the setting and its allowed values. The
setup script and `./scripts/setup.sh --check` both test for this.

## Network Access

The app needs outbound HTTPS (port 443), plus plain HTTP (port 80) for the few
publisher PDF links that use it. Locally it listens on port **8000** (backend)
and, in development, port **5173** (frontend).

| Host | Used for |
|------|----------|
| `export.arxiv.org`, `arxiv.org` | arXiv search, metadata lookup, PDF downloads |
| `api.openalex.org` | OpenAlex search |
| `api.anthropic.com` | Summaries, answers, PDF metadata extraction |
| Publisher and repository sites | Open-access PDFs linked from OpenAlex results |
| `registry.npmjs.org` | JavaScript packages (setup only) |
| `files.pythonhosted.org` | Python packages (setup only) |
| `astral.sh`, `releases.astral.sh` | The uv installer and uv's Python downloads (setup only) |
| `github.com`, `*.githubusercontent.com` | Fallback source for uv's Python downloads (setup only) |

## Setup Script Reference

| Command | What it does |
|---------|--------------|
| `./scripts/setup.sh` | Checks the tools, installs the packages, creates and checks `.env`, and asks for the API key |
| `./scripts/setup.sh --check` | Only reports whether the packages match the lockfiles, `.env` is valid, and credentials are found; changes nothing |
| `./scripts/setup.sh --no-prompt` | Same as the first, but never asks questions (for automation) |
| `make install` | Same as `./scripts/setup.sh` |
| `make check` | Same as `./scripts/setup.sh --check` |

What the full run does, in order:

1. Checks for uv, Node.js (version range above), npm, and make. If uv is missing and
   you are at a terminal, it offers to install it with the official installer (into
   `~/.local/bin`, no sudo). Node.js you install yourself.
2. Runs `uv sync --locked` in `backend/`. This provides Python 3.11 and installs the
   locked Python packages into `backend/.venv`.
3. Runs `npm ci` in `frontend/`, which installs the locked JavaScript packages into
   `frontend/node_modules`.
4. Creates `.env` from `.env.example` if it does not exist (an existing `.env` is
   never replaced), then validates every value with the app's own settings loader.
5. If the app would find no Anthropic credentials (an API key in `.env` or the shell,
   `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile), asks for a key with hidden
   input (press Enter to skip) and saves it to `.env`. Only the key's format is
   checked, not whether Anthropic accepts it; the first summary shows that.

The script is safe to run again, for example after pulling new changes.

## Manual Setup

The same steps without the script:

```bash
(cd backend && uv sync --locked)
(cd frontend && npm ci)
cp .env.example .env
chmod 600 .env
```

Then open `.env` in an editor and set `ANTHROPIC_API_KEY`.

## Running the App

Stop either mode with Ctrl+C in the terminal where it runs.

### Development (Live Reload)

With make:

```bash
make dev
```

Without make, use two terminals. In the first:

```bash
(cd backend && SERVE_FRONTEND=false uv run uvicorn app.main:app --reload --port 8000)
```

In the second, first `cd` into the project folder, then:

```bash
(cd frontend && npm run dev)
```

Open <http://localhost:5173>. The frontend forwards `/api` requests to the backend.

### Single Server

With make:

```bash
make start
```

Without make:

```bash
(cd frontend && npm run build) && (cd backend && uv run uvicorn app.main:app --port 8000)
```

Open <http://localhost:8000>.

## Verify the Installation

1. Run `./scripts/setup.sh --check`. It should end with "Everything required is in
   place."
2. Start the app and open <http://localhost:8000/api/health>. It should show
   `{"status":"ok"}`.
3. In the UI, search for "attention is all you need". Results should appear within a
   few seconds.
4. Save a paper, open it, and click **Generate summary**. If the API key is missing
   or wrong, the panel says so.

## Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `uv: command not found` right after installing uv | Open a new terminal, or run `export PATH="$HOME/.local/bin:$PATH"`. |
| Setup says Node.js is not supported, or Vite fails with an engine error | Install a supported Node.js (`brew install node`, or `nvm install 22`) and run the script again. |
| Setup says `node --version` failed | A version manager (nvm, asdf, nodenv) is active with no version selected; select one, for example `nvm use 22`. |
| `uv sync` says "The lockfile at uv.lock needs to be updated" | `backend/pyproject.toml` was changed without updating the lockfile. Undo the change with `git checkout backend/pyproject.toml`, or run `uv lock` in `backend/`. |
| `uv sync` says it is "Unable to find lockfile" or cannot parse it | Your uv is too old (before 0.4); run `uv self update` or `brew upgrade uv`. |
| `npm ci` fails because `package.json` and `package-lock.json` are not in sync | One of them was edited; restore both with `git checkout frontend/package.json frontend/package-lock.json`. |
| "Address already in use" on port 8000, or Vite reports "Port 5173 is already in use" | Another process holds the port. Find it with `lsof -i :8000` (or `:5173`) and stop it. |
| UI shows "Cannot reach the backend" | The backend is not running, or crashed at startup; check its terminal output. |
| Paper page says no API key is configured | Set `ANTHROPIC_API_KEY` in `.env` and restart the backend. |
| Summary fails with "API key is missing or invalid" | The key is wrong or revoked; create a new one in the Anthropic Console and update `.env`. |
| OpenAlex search reports a rate limit | Set `OPENALEX_API_KEY` in `.env`, or search arXiv. |
| Backend stops at startup with a "validation error for Settings" | A value in `.env` is invalid; the message names the setting and its allowed values. |

## Uninstall or Reset

From the project folder, these commands remove, in order: the installed packages
and build output; your library (saved papers, summaries, chat history, and stored
PDFs, which cannot be recovered); and your settings and API key.

```bash
rm -rf backend/.venv frontend/node_modules frontend/dist
rm -rf backend/data
rm -f .env
```

Optionally, free the shared download caches (this also affects your other projects):

```bash
uv cache clean
npm cache clean --force
```

If uv downloaded Python 3.11 for this project, `uv python uninstall 3.11` removes it
from `~/.local/share/uv/python`.
