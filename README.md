# AI Research Assistant

A web app for finding, organizing, and understanding research papers. You can search
arXiv and OpenAlex, save papers to a local library, upload your own PDFs, and ask
Claude to summarize a paper or answer questions about it. The answers are based on the
paper's full text, not just its title and abstract.

Built for Homework 1, "Build an AI Research Assistant with a Coding Agent", with
Claude Code as the coding agent. The development record, including every
code-review finding and its fix, is in [docs/DEVLOG.md](docs/DEVLOG.md).

## Features

| # | Feature | What it does |
|---|---------|--------------|
| F1 | **Search papers** | Search by keywords or topic on **arXiv** or **OpenAlex**. Each result shows title, authors, year, venue, abstract, and links to the paper page and PDF. "Load more" pages through results. |
| F2 | **Local library** | Save any result with one click. Papers live in a local SQLite database, so they survive page refreshes and restarts. The Library page lists, filters (by title, author, or abstract), opens, and removes papers. Saving the same paper from both sources keeps one entry when their DOI or arXiv id matches. |
| F3 | **PDF upload** | Upload a PDF (button or drag and drop). The app extracts the full text and the **title, authors, year, and abstract**, and shows the paper like a search result. Metadata comes from arXiv when the PDF carries an arXiv id, otherwise from Claude reading the first pages, otherwise from layout heuristics. You can correct any field with "Edit details". |
| F4 | **Summaries** | "Generate summary" streams a structured summary (TL;DR, problem, approach, key results, setup, limitations) written from the paper's **full text**. Summaries are saved and show which model wrote them and whether the full text or only the abstract was available. |
| F5 | **Questions and answers** | Ask anything about the selected paper, or click one of the example questions (problem, main idea, datasets, limitations, baselines). Answers stream in, cite sections where possible, and the conversation is saved per paper. |

Full text is always available for arXiv papers and uploads. Saved papers download their
open-access PDF the first time you open them. When no PDF can be found (common for
paywalled OpenAlex results), the app says so, falls back to the abstract, and offers an
**Attach PDF** button.

## How It Works

```
 Browser: React + TypeScript (Vite)
    │  JSON over /api; LLM output streams as newline-delimited JSON
    ▼
 FastAPI backend (Python 3.11)
    ├── Search ─────────► arXiv API (Atom XML), OpenAlex API (JSON)
    ├── Library ────────► SQLite via SQLAlchemy      backend/data/app.db
    ├── PDF processing ─► PyMuPDF                    backend/data/pdfs/
    └── Assistant ──────► Anthropic Claude API (claude-opus-5 by default)
```

Design choices worth knowing:

- **The LLM reads the whole paper.** The paper's text goes into the system prompt
  behind a prompt-cache breakpoint. The summary and every follow-up question reuse that
  cached prefix, so later questions are faster and cheaper. Very long papers are cut
  off at `LLM_MAX_PAPER_CHARS`, and the UI says when that happens.
- **Streaming with a clean save.** Summaries and answers stream token by token, but
  are written to the database only after the full response arrives, so a failed or
  refused request never stores partial text.
- **Server-side refusal fallback.** Requests opt into Anthropic's `fallbacks: "default"`
  beta, so if the model's safety classifiers decline a request, the API retries it on a
  fallback model automatically.
- **No secrets in git.** Keys live in `.env`, which is git-ignored. `.env.example`
  documents every setting.

## Project Structure

```
AI_Research_Assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app; also serves the built frontend
│   │   ├── config.py          settings from .env
│   │   ├── db.py, models.py   SQLite engine and ORM models (Paper, ChatMessage)
│   │   ├── schemas.py         request/response models
│   │   ├── routers/
│   │   │   ├── search.py      GET /api/search
│   │   │   ├── papers.py      library, upload, PDF, metadata editing
│   │   │   └── assistant.py   summaries and Q&A (streaming)
│   │   └── services/
│   │       ├── arxiv.py, openalex.py   search clients
│   │       ├── pdf.py                  text and metadata extraction
│   │       ├── fulltext.py             PDF download, storage, attach
│   │       └── llm.py                  Claude prompts and streaming
│   ├── pyproject.toml, uv.lock
│   └── data/                  created at runtime; git-ignored
├── frontend/
│   └── src/
│       ├── pages/             SearchPage, LibraryPage, PaperPage
│       ├── components/        PaperCard, UploadBox, SummaryPanel, ChatPanel, …
│       ├── api.ts             backend client, including the stream reader
│       └── types.ts           shared types
├── docs/                      requirements, plan, development log
├── Makefile, Dockerfile, .env.example
```

## Setup

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** for Python. It downloads Python 3.11 automatically.
- **Node.js 20 or newer** (tested with 22) and npm.
- **An Anthropic API key** from <https://console.anthropic.com/>. Search, the library,
  and PDF upload work without it; summaries and Q&A need it.

### Install and Configure

```bash
git clone https://github.com/harrison4ride/AI_Research_Assistant.git
cd AI_Research_Assistant
make install                 # uv sync + npm install
cp .env.example .env         # then set ANTHROPIC_API_KEY in .env
```

### Run (Development)

```bash
make dev
```

This starts the API on port 8000 and the UI on **<http://localhost:5173>** (open
this one). The UI forwards `/api` calls to the
backend. Both reload on code changes; Ctrl+C stops both. To run them in separate
terminals, use `make backend` and `make frontend`.

### Run (Single Process)

```bash
make start
```

This builds the frontend and serves the UI and the API together on
**<http://localhost:8000>**.

### Docker

```bash
docker build -t research-assistant .
docker run -p 8000:8000 --env-file .env -e DATA_DIR=/data -v research-data:/data research-assistant
```

The image builds the frontend and runs the single-process server, keeping the
database and PDFs in the `/data` volume. `-e DATA_DIR=/data` keeps a `DATA_DIR` line
in your local `.env` from moving the data out of the volume. Unlike the app itself,
Docker's `--env-file` does not strip quotes, so write `.env` values unquoted
(`ANTHROPIC_API_KEY=sk-ant-...`). **Note:** this Dockerfile has not been built
or run yet, because Docker was not available in the development environment.
`make start` is the verified way to run the app as one process.

## Configuration

All settings are optional except the API key. Set them in `.env` (see `.env.example`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | none | Claude API key, needed for summaries, Q&A, and LLM metadata extraction |
| `LLM_MODEL` | `claude-opus-5` | Claude model |
| `LLM_EFFORT` | `medium` | Thinking effort: `low`, `medium`, `high`, `xhigh`, `max` |
| `LLM_MAX_PAPER_CHARS` | `400000` | Paper text sent to the model (about 100K tokens) |
| `LLM_EXTRACT_METADATA` | `true` | Let Claude read uploaded PDFs' first pages for metadata |
| `OPENALEX_EMAIL`, `OPENALEX_API_KEY` | none | Optional OpenAlex identification and higher quota |
| `MAX_PDF_MB` | `50` | Size limit for uploaded and downloaded PDFs |
| `DATA_DIR` | `backend/data` | Location of the SQLite database and PDFs |

## API Reference

| Method and path | Description |
|-----------------|-------------|
| `GET /api/search?q=&source=arxiv\|openalex&page=&per_page=` | Search papers |
| `GET /api/papers?q=` | List saved papers, optionally filtered |
| `POST /api/papers` | Save a search result (returns the existing entry if already saved) |
| `POST /api/papers/upload` | Upload a PDF (multipart field `file`) |
| `GET / PATCH / DELETE /api/papers/{id}` | Get, edit metadata, or remove a paper |
| `POST /api/papers/{id}/fulltext` | Download and extract the paper's open-access PDF |
| `POST /api/papers/{id}/pdf` | Attach a PDF to an existing paper |
| `GET /api/papers/{id}/pdf` | View the stored PDF |
| `POST /api/papers/{id}/summary` | Stream a new summary (NDJSON) |
| `GET / POST / DELETE /api/papers/{id}/chat` | Read, ask (streams NDJSON), or clear the Q&A history |
| `GET /api/config` | Model name and whether credentials were found |

Interactive API docs are at <http://localhost:8000/docs> while the backend runs.

## Where Your Data Goes

- Saved papers, summaries, chat history, and PDFs stay on your machine in `DATA_DIR`.
- Search queries go to arXiv or OpenAlex. PDFs are downloaded from the links those
  services provide.
- When you ask for a summary or an answer, the paper's text and your question go to
  the Anthropic API. On upload, the first pages also go to Anthropic for metadata
  extraction, unless `LLM_EXTRACT_METADATA=false`.

## Known Limitations

- PDF metadata heuristics can mis-split author names on unusual layouts, and
  re-joining words hyphenated across lines also merges true compounds
  ("task-specific" becomes "taskspecific"). Claude extraction and the arXiv lookup
  cover most cases, and every field is editable.
- Scanned PDFs without a text layer are rejected; there is no OCR.
- Text extraction ignores figures, and tables come through as plain text.
- OpenAlex sometimes has no abstract, or a garbled one, for a work. That is upstream data.
- arXiv asks clients to wait 3 seconds between API calls, so back-to-back arXiv
  searches are spaced out.
- There are no automated tests yet (HW2 adds them).

## Development Process

The app was built in six milestones (M0 to M5, see [docs/PLAN.md](docs/PLAN.md)). After
each milestone, Claude Code's `/code-review` ran on the uncommitted changes; every
finding was fixed or explicitly decided on before that milestone's commit.
[docs/DEVLOG.md](docs/DEVLOG.md) records what each review found, and
[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) lists the assignment requirements.
