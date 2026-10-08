# AI Research Assistant

A web app for finding, organizing, and understanding research papers. You can search
OpenAlex and arXiv, read any result in the app's reader, save papers to a local
library, and upload your own PDFs. Claude can summarize a paper, summarize each of its
sections, and answer questions about it. Summaries and answers are based on the
paper's full text when its PDF is available, and on its abstract otherwise. By default
Claude runs through the Claude Code installed on your machine, with your own Claude
Code login, so no API key is needed.

Built for Homework 1, "Build an AI Research Assistant with a Coding Agent", with
Claude Code as the coding agent. The development record, including every
code-review finding and its fix, is in [docs/DEVLOG.md](docs/DEVLOG.md).

## Features

| # | Feature | What it does |
|---|---------|--------------|
| F1 | **Search papers** | Search by keywords or topic on **OpenAlex** (the default: fast, all publishers, including arXiv) or **arXiv**. Each result shows title, authors, year, venue, abstract, DOI, and links to the paper page and PDF. "Read" (or the title) opens it in the reader. "Load more" pages through results. If an arXiv search fails, "Search OpenAlex instead" runs the same query on OpenAlex. |
| F2 | **Local library** | Save any result with one click. Papers live in a local SQLite database, so they survive page refreshes and restarts. The Library page lists, filters (by title, author, or abstract), opens, and removes papers. Saving the same paper from both sources keeps one entry when their DOI or arXiv id matches. |
| F3 | **PDF upload** | Upload a PDF on the Library page (button or drag and drop). The app extracts the full text and the **title, authors, year, and abstract**, adds the paper to the library, and opens it in the reader. Metadata comes from arXiv when the PDF carries an arXiv id, otherwise from Claude reading the first pages, otherwise from layout heuristics. You can correct any field with "Edit details" in the reader's **Details** tab. |
| F4 | **Summaries** | "Generate summary" streams a structured summary (TL;DR, problem, approach, key results, setup, limitations) written from the paper's **full text**. Summaries are saved and show which model wrote them and whether the full text or only the abstract was available. |
| F5 | **Questions and answers** | Ask anything about the selected paper, or click one of the example questions (problem, main idea, datasets, limitations, baselines). Answers stream in, cite sections where possible, and the conversation is saved per paper. |

**The reader.** Clicking a search result's title or its **Read** button opens the
paper in a three-column reader without adding it to the library. Library papers and
uploads open in the same reader:

- **Left:** three tabs. **Sections** lists the paper's sections with page numbers,
  read from the PDF's bookmarks or detected headings; it needs the paper's PDF. Click
  a section to jump to it in the PDF. The section you are reading is highlighted.
  **Summarize sections** adds a one-sentence summary to each section when you click
  it. If the app finds no headings, **Summarize sections** has the model name the
  sections, and the app then looks for them in the PDF. **Summary** holds the full summary (F4). **Details** shows the
  paper's metadata, an **Edit details** button, and when the paper was saved or first
  opened.
- **Center:** the PDF itself, rendered in the page with react-pdf (PDF.js). It has
  zoom, **Fit width**, a page counter, and **Open PDF** (opens a new tab). PDF.js
  loads only when you open a paper that has a PDF, and only pages near the view are
  rendered, so long papers stay fast. A paper without a PDF shows its abstract here.
- **Right:** questions and answers (F5).
- **Header:** **Save to library** for an unsaved paper, or "✓ In library" and
  **Remove** for a library paper. A link opens the paper's source page. The **model
  menu** applies to section summaries, the summary, and answers. With the Claude Code
  provider it offers Opus, Sonnet, Haiku, Fable, and "Claude Code default". With the
  API provider it offers Claude Opus 5, Claude Sonnet 5, Claude Haiku 4.5, and Claude
  Fable 5.1. `CLAUDE_CODE_MODEL` / `LLM_MODEL` set the menu's default (and the model
  that reads uploaded PDFs' metadata). A default outside these lists appears in the
  menu with "(from .env)" after its name. Each result shows which model wrote it, and
  the browser remembers your choice.

An unsaved paper (one opened from search but not saved) stays out of the library. If
you save it later, it keeps its summary, section summaries, and conversation. Unsaved
papers that have not been opened for `CACHED_PAPER_DAYS` days (default 7) are deleted,
with their conversation and their PDF (unless another paper uses the same file). The
backend checks at startup and every 12 hours. The **Details** tab of an unsaved paper
shows this limit.

The app rejects an upload when it cannot extract text (for example, a scanned PDF), so
every upload has its text. A search result downloads its PDF the first time
you open it. arXiv results always have a PDF link, and OpenAlex results have one when
OpenAlex knows an open-access copy. When no PDF can be found (common for paywalled
OpenAlex results), the app says so, falls back to the abstract, and offers an
**Attach PDF** button.

## How It Works

```
 Browser: React + TypeScript (Vite); the reader shows PDFs with PDF.js (react-pdf)
    │  JSON and PDFs over /api; LLM output streams as newline-delimited JSON
    ▼
 FastAPI backend (Python 3.11)
    ├── Search ─────────► OpenAlex API (JSON, default), arXiv API (Atom XML)
    ├── Library ────────► SQLite via SQLAlchemy      backend/data/app.db
    ├── PDF download ───► open-access PDF links (public addresses only)
    ├── PDF processing ─► PyMuPDF: text, metadata,   backend/data/pdfs/
    │                     section outline
    └── Assistant ──────► local Claude Code CLI (default, your login)
                          or Anthropic Claude API (LLM_PROVIDER=api)
```

Design choices worth knowing:

- **The LLM reads the whole paper.** The paper's text goes into the system prompt
  behind a prompt-cache breakpoint. The summary, the section summaries, and every
  question reuse that cached prefix when they use the same model, so later requests
  are faster and cheaper. Very long papers are cut off at `LLM_MAX_PAPER_CHARS`. The
  prompt tells the model when that happens, and the **Summary** tab shows a note when
  you generate a summary.
- **Streaming with a clean save.** Summaries and answers stream token by token, but
  are written to the database only after the full response arrives, so a failed or
  refused request never stores partial text.
- **Two ways to reach Claude.** With the Claude Code provider
  (`LLM_PROVIDER=claude-code`, the default), the backend runs the local `claude` CLI
  locked down to answering from the paper. It allows no tools, no MCP servers, no
  CLAUDE.md or settings, and no saved sessions. Prompts are passed verbatim, and the
  paper goes in a file instead of on the command line. Claude Code still adds your
  account email and basic environment details to its context, and the model is told
  never to repeat them. With the API provider (`LLM_PROVIDER=api`), the backend calls
  the Anthropic API. For models whose id starts with `claude-opus-5` or
  `claude-fable-5` (Claude Opus 5 and Claude Fable 5.1 in the menu), it opts into the
  `fallbacks: "default"` beta. The API then retries a request declined by the safety
  classifiers on a fallback model. The backend accepts only the model ids in the model
  menu (HTTP 422 otherwise), so no other text reaches the `claude` command line or the
  API.
- **PDF downloads reach only public addresses.** PDF links come from search
  metadata, so the backend downloads only http(s) links whose host resolves to public
  addresses. It checks every redirect again (at most 5) and connects to the checked
  IP address, so a second DNS answer cannot point it at a private one.
- **Model output loads nothing by itself.** Summaries and answers render as Markdown,
  and raw HTML in them is ignored. The UI never loads images from model output. A link
  whose address has a query string appears as plain text with its full address. The
  Content-Security-Policy in `frontend/index.html` allows images only from the app
  itself (and `data:` and `blob:` URLs).
- **No secrets in git.** Keys live in `.env`, which is git-ignored. `.env.example`
  documents every setting.

## Project Structure

```
AI_Research_Assistant/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app; prunes unsaved papers; serves the built frontend
│   │   ├── config.py          settings from .env
│   │   ├── db.py, models.py   SQLite engine and ORM models (Paper, ChatMessage)
│   │   ├── schemas.py         request/response models
│   │   ├── routers/
│   │   │   ├── search.py      GET /api/search, with a 10-minute result cache
│   │   │   ├── papers.py      library, open and save, upload, PDF, outline, metadata editing
│   │   │   └── assistant.py   /api/config, summaries and Q&A (streaming), section summaries
│   │   └── services/
│   │       ├── arxiv.py, openalex.py   search clients (arXiv: 3 s spacing, cooldown)
│   │       ├── http.py                 shared HTTP client
│   │       ├── pdf.py                  text, metadata, and section outline extraction
│   │       ├── fulltext.py             PDF download (public addresses only), storage, attach
│   │       ├── cache.py                deletes unsaved papers not opened for CACHED_PAPER_DAYS
│   │       ├── llm.py                  Claude prompts, streaming, model menu, provider choice
│   │       └── claude_code.py          runs the local Claude Code CLI
│   ├── pyproject.toml, uv.lock
│   └── data/                  created at runtime; git-ignored
├── frontend/
│   ├── index.html             page shell, with the Content-Security-Policy
│   └── src/
│       ├── pages/             SearchPage, LibraryPage, PaperPage (the reader)
│       ├── components/        PdfViewer, SectionsPanel, ModelSelect, SummaryPanel,
│       │                      ChatPanel, PaperCard, UploadBox, …
│       ├── api.ts             backend client, including the stream reader
│       ├── router.ts          hash routes: #/search, #/library, #/paper/{id}
│       ├── useLlmStream.ts    state of one streamed summary or answer
│       ├── useModelChoice.ts  the model menu choice, kept in localStorage
│       └── types.ts           shared types
├── scripts/setup.sh           checks requirements and installs everything
├── docs/                      requirements, plan, development log
├── INSTALL.md                 detailed installation guide
└── Makefile, .env.example
```

## Setup

Full requirements, version notes, and troubleshooting are in **[INSTALL.md](INSTALL.md)**.

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** for Python. It uses an installed Python 3.11 or
  downloads one.
- **Node.js 22.13 or later** (tested with 22.22) and npm.
- **For summaries, section summaries, and Q&A:**
  [Claude Code](https://claude.com/claude-code), installed and logged in (the
  default), or an Anthropic API key with `LLM_PROVIDER=api`. Search, the library, PDF
  upload, and the reader's PDF view and section list work without either.

### Install

```bash
git clone https://github.com/harrison4ride/AI_Research_Assistant.git
cd AI_Research_Assistant
./scripts/setup.sh
```

The script checks the tools above, installs the locked Python and JavaScript
packages inside the project folder, creates and validates `.env`, and checks that
Claude Code is installed and logged in. (With `LLM_PROVIDER=api` it asks for your API
key instead, with hidden input.)
It is safe to run again. `./scripts/setup.sh --check` only reports what is installed.

### Run (Development)

```bash
make dev
```

This starts the API on port 8000 and the UI on **<http://localhost:5173>** (open
this one). The UI forwards `/api` calls to the backend. Both reload on code changes;
Ctrl+C stops both. To run them in separate terminals, use `make backend` and
`make frontend`.

### Run (Single Process)

```bash
make start
```

This builds the frontend and serves the UI and the API together on
**<http://localhost:8000>**. INSTALL.md lists the equivalent commands for machines
without `make`.

## Configuration

Settings live in `.env` in the project root; `.env.example` lists every one. None is
required with the default Claude Code provider. The main ones choose the provider
(`LLM_PROVIDER`, default `claude-code`) and the model menu's default
(`CLAUDE_CODE_MODEL`, default `opus`, or `LLM_MODEL` with the API provider, default
`claude-opus-5`). Others set the thinking effort (`LLM_EFFORT`, default `medium`), size
limits, how long an unsaved paper is kept without being opened (`CACHED_PAPER_DAYS`,
default 7 days), and the data folder (`DATA_DIR`). See
[INSTALL.md § Environment Variables](INSTALL.md#environment-variables) for the full table.

## API Reference

| Method and path | Description |
|-----------------|-------------|
| `GET /api/search?q=&source=openalex\|arxiv&page=&per_page=` | Search papers. `source` defaults to `openalex`, and `per_page` to 10 (at most 50). Results are cached for 10 minutes. |
| `GET /api/papers?q=` | List the library's papers, optionally filtered |
| `GET /api/papers/keys` | Source, external id, and id of each library paper that has an external id (the search page uses it to mark saved results) |
| `POST /api/papers` | Save a search result to the library. If the paper is already stored, it returns the existing entry and moves an unsaved one into the library. |
| `POST /api/papers/open` | Open a search result in the reader without saving it |
| `POST /api/papers/{id}/save` | Add an unsaved paper to the library; it keeps its summary, section summaries, and chat |
| `POST /api/papers/upload` | Upload a PDF (multipart field `file`) |
| `GET / PATCH / DELETE /api/papers/{id}` | Get, edit metadata, or remove a paper. A GET of an unsaved paper counts as opening it and restarts its `CACHED_PAPER_DAYS` count. |
| `POST /api/papers/{id}/fulltext?retry=` | Download and extract the paper's open-access PDF. `retry=true` tries again after an earlier attempt failed. |
| `POST /api/papers/{id}/pdf` | Attach a PDF to an existing paper |
| `GET /api/papers/{id}/pdf` | View the stored PDF |
| `GET /api/papers/{id}/outline` | The paper's sections (with summaries once generated) |
| `POST /api/papers/{id}/outline/summaries` | Write one-sentence section summaries (body: `{"model"}`) |
| `POST /api/papers/{id}/summary?model=` | Stream a new summary (NDJSON) |
| `GET / POST / DELETE /api/papers/{id}/chat` | Read, ask (body: `{"question", "model"}`; streams NDJSON), or clear the Q&A history |
| `GET /api/config` | LLM provider, the model menu and its default, whether summaries and Q&A can run (and how to fix it if not), and `cached_paper_days` (how many days an unsaved paper is kept without being opened) |
| `GET /api/health` | Health check; returns `{"status": "ok"}` while the backend runs. The UI polls it until the backend answers. |

Interactive API docs are at <http://localhost:8000/docs> while the backend runs.

## Where Your Data Goes

- Papers, summaries, section summaries, chat history, and PDFs stay on your machine
  in `DATA_DIR`. Unsaved papers are stored there too, until they are deleted after
  `CACHED_PAPER_DAYS` days without being opened.
- Search queries go to OpenAlex or arXiv. OpenAlex also receives `OPENALEX_EMAIL` and
  `OPENALEX_API_KEY` when you set them. PDFs are downloaded from the links those
  services provide, and only from public http(s) addresses.
- When you ask for a summary, section summaries, or an answer, the paper's text goes
  to Anthropic. A question also sends the question itself and up to
  `LLM_HISTORY_MESSAGES` earlier Q&A messages. Requests go through your Claude Code
  login by default, or the Anthropic API with `LLM_PROVIDER=api`. The Claude Code
  provider also sends your account email and basic environment details.
- On upload, a PDF whose first page carries an arXiv id is looked up on arXiv. If it
  has no arXiv id or the lookup finds no matching paper, the first pages go to Anthropic for
  metadata extraction, unless `LLM_EXTRACT_METADATA=false`.

## Known Limitations

- PDF metadata heuristics can mis-split author names on unusual layouts, and
  re-joining words hyphenated across lines also merges true compounds
  ("task-specific" becomes "taskspecific"). Claude extraction and the arXiv lookup
  cover most cases, and every field is editable.
- Scanned PDFs without a text layer are rejected; there is no OCR.
- Text extraction ignores figures, and tables come through as plain text.
- The section outline comes from the PDF's bookmarks when it has at least three.
  Otherwise the app looks for bold or large headings that are numbered or have a
  common name, such as Introduction or References. Both ways leave out
  sub-subsections (such as 3.2.1). Heading detection stops at References, so
  appendices after it are missing. When the model names the sections (no headings
  found), a section the app cannot find in the PDF has no page number.
- OpenAlex sometimes has no abstract, or a garbled one, for a work. That is upstream data.
- arXiv asks clients to wait 3 seconds between API calls and rate-limits everything
  from one IP address. The app keeps 3 seconds between its arXiv calls. After HTTP 429
  or 503, or a timeout, it pauses arXiv calls for 60 seconds, or longer when arXiv's
  `Retry-After` header asks (at most 10 minutes). During a pause, searches fail at
  once with a message, and uploads skip the arXiv metadata lookup. Repeated searches
  within 10 minutes reuse earlier results.
- There are no automated tests yet (HW2 adds them).

## Development Process

The app was built in seven milestones (M0 to M6, see [docs/PLAN.md](docs/PLAN.md)). After
each milestone, Claude Code's `/code-review` ran on the uncommitted changes; every
finding was fixed or explicitly decided on before that milestone's commit. Follow-up
changes replaced Docker with `scripts/setup.sh` and INSTALL.md, fixed dev-server
reachability on 127.0.0.1, and added the Claude Code provider as the default. The setup
script, the Claude Code provider, and M6 also went through a multi-agent verification
workflow before `/code-review`. After M6, the default `CACHED_PAPER_DAYS` went from 30
to 7 days. [docs/DEVLOG.md](docs/DEVLOG.md) records what each review found, and
[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) lists the assignment requirements.
