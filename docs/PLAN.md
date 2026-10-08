# Implementation Plan

## Architecture

```
 Browser (React + Vite + TS): search page, library page, and the reader
   (sections | PDF rendered with react-pdf | Q&A)
        │  /api/*  (JSON; summaries and answers stream as newline-delimited JSON)
        ▼
 FastAPI backend (Python 3.11)
   ├── search service ──► OpenAlex API (default), arXiv API       (F1)
   │     10-minute result cache; arXiv spacing and cooldown
   ├── library (SQLAlchemy) ──► SQLite  data/app.db               (F2)
   │     saved and unsaved papers; services/cache.py prunes unsaved ones
   ├── PDF service (PyMuPDF) ──► data/pdfs/*.pdf                  (F3)
   │     text, metadata, section outline; downloads only from public addresses
   └── LLM service ──► local Claude Code CLI (default)            (F4, F5)
                       or Anthropic Claude API; model chosen in the model menu
```

### Key Design Decisions

- **Search sources:** OpenAlex is the default (no key, broad coverage across
  publishers, open-access PDF links when they exist). arXiv is the second source (no
  key, always has a PDF, so the full text is available). OpenAlex became the default
  in M6 because it answers fast and arXiv limits all calls from one IP address. arXiv
  asks for one request at a time, 3 s apart, and `backend/app/services/arxiv.py` keeps
  that spacing. After HTTP 429 or 503, it pauses arXiv for 60 to 600 s, following
  `Retry-After` (in seconds) when present. After a timeout, it pauses arXiv for 60 s.
  `GET /api/search` reuses results for 10 minutes (at most 256 cached result pages).
  When an arXiv search fails, the search page offers a "Search OpenAlex instead"
  button. Semantic Scholar was considered but returns HTTP 429 without an API key.
  Google Scholar has no API, and its `robots.txt` disallows `/scholar`.
- **Content-based LLM answers (F4/F5):** every paper gets a `full_text` column.
  Uploaded PDFs are parsed on upload. For a search result, the backend downloads and
  parses its open-access PDF the first time the reader opens the paper
  (`POST /api/papers/{id}/fulltext`). The summary, Q&A, and outline endpoints also
  fetch it if that was never tried. The LLM prompt contains the full text, cut off at
  `LLM_MAX_PAPER_CHARS`, so summaries and answers draw on the paper body. If no PDF is
  obtainable, the app falls back to the abstract, says so in the UI, and offers an
  "Attach PDF" button.
- **Reader:** clicking a search result (its title or the "Read" button) calls
  `POST /api/papers/open`. That stores the paper as an unsaved paper
  (`in_library = false`) unless it is already in the library, and the reader opens at
  `#/paper/{id}`. Library papers and uploads open in the same reader
  (`frontend/src/pages/PaperPage.tsx`). The left column has the Sections, Summary, and
  Details tabs. The center shows the PDF with react-pdf (PDF.js), loaded lazily, with
  zoom; only pages near the viewport are rendered. Without a PDF, the center shows the
  abstract. The right column holds Q&A. "Save to library"
  (`POST /api/papers/{id}/save`) adds the paper to the library and keeps its summary,
  chat, and section outline.
- **Unsaved papers and pruning:** unsaved papers stay out of the library
  (`GET /api/papers` lists only papers with `in_library = true`). Opening one records
  `last_opened_at`. `prune_cached_papers()` in `backend/app/services/cache.py` deletes
  unsaved papers not opened for `CACHED_PAPER_DAYS` (default 7), with their chat. It
  also deletes the PDF file when no other paper uses it. Pruning runs at startup and
  every 12 hours (the lifespan task in `backend/app/main.py`). `GET /api/config`
  returns `cached_paper_days`, and the Details tab of an unsaved paper shows it.
- **Section outline:** `GET /api/papers/{id}/outline` reads the sections, with page
  numbers, from the PDF's bookmarks (when there are at least 3) or else from detected
  headings, and stores them. Clicking a section jumps to it in the PDF, and the section
  being read is highlighted. "Summarize sections"
  (`POST /api/papers/{id}/outline/summaries`) writes one sentence per section only when
  the user clicks it, and it needs the full text. When the PDF has no detectable
  headings, "Summarize sections" asks the model to name the sections, and the app
  locates them in the PDF.
- **PDF download safety:** PDF links come from search metadata, so
  `backend/app/services/fulltext.py` treats them as untrusted. It downloads only over
  http(s) from hosts whose addresses are all public, and it checks every redirect (at
  most 5) the same way. It connects to the checked IP address and keeps the real host
  name for the `Host` header and TLS, so a second DNS answer cannot swap in a private
  address. Downloads larger than `MAX_PDF_MB` are refused.
- **Metadata extraction from uploads (F3):** an arXiv-ID lookup → LLM
  extraction from the first pages → font-size/regex heuristics, in that order of
  preference; the user can edit fields afterwards.
- **LLM:** two providers. The default Claude Code provider (`LLM_PROVIDER=claude-code`)
  runs the locally installed Claude Code CLI with the user's own login, so no API key is
  needed. It is locked down to answering from the paper: no tools, MCP, settings, or
  saved sessions. The API provider (`LLM_PROVIDER=api`) uses Claude (`claude-opus-5` by
  default, set by `LLM_MODEL`) through the official `anthropic` SDK, with streaming,
  adaptive thinking, and server-side refusal fallbacks. The paper sits in the system
  prompt behind a prompt-cache breakpoint, so the summary and every follow-up question
  reuse it. An OpenAI-compatible provider was planned at first but dropped; both
  providers reach Claude.
- **Model menu:** the reader header has a model menu for section summaries, the
  summary, and Q&A. The Claude Code provider offers `opus`, `sonnet`, `haiku`, `fable`,
  and `default`; the API provider offers `claude-opus-5`, `claude-sonnet-5`,
  `claude-haiku-4-5`, and `claude-fable-5-1`. `CLAUDE_CODE_MODEL` (Claude Code
  provider) or `LLM_MODEL` (API provider) sets the default, and the menu always
  includes it. The backend accepts only these ids and answers 422 for any other
  (`resolve_model()` in `backend/app/services/llm.py`). Arbitrary text therefore never
  reaches the `claude` command line or the Anthropic API. The browser remembers the
  choice in `localStorage`.
- **Model output safety:** Claude Code adds the user's account email and environment
  details to its context, and no flag removes them. The prompts tell the model never to
  repeat them. `frontend/src/components/Markdown.tsx` never loads images from model
  output, and it shows links that carry a query string as plain text with the full URL.
  The Content-Security-Policy in `frontend/index.html` allows images only from the app
  itself and from `data:` or `blob:` URLs.
- **Persistence:** SQLite file under `backend/data/` (git-ignored; `DATA_DIR` changes
  the location). Summaries, Q&A history, and section outlines with their one-sentence
  summaries are stored too, so they survive restarts. Unsaved papers share the `papers`
  table, marked `in_library = false`.
- **Secrets:** read from `.env` (git-ignored); `.env.example` documents the variables.
- **Deployment:** `npm run build` produces static assets that FastAPI serves, so the
  whole app runs as one process on one port.
- **Environment setup:** `scripts/setup.sh` checks the required tools (uv, Node.js
  22.13 or later, npm), installs the locked packages, and creates and validates `.env`.
  It also checks the language model: that Claude Code is installed and logged in, or,
  for the API provider, that Anthropic credentials are found. PDF.js 6, used by the
  reader, sets the Node.js minimum. `INSTALL.md` documents every requirement. A
  Dockerfile was tried in M5 and removed (see DEVLOG).

## Milestones

Each milestone: implement → manual verification → `/code-review` on the diff →
fix findings → commit. Review outcomes are logged in `docs/DEVLOG.md`.

| Milestone | Scope | Requirements |
|-----------|-------|--------------|
| M0 | Requirements + plan docs, backend/frontend scaffold, health endpoint, dev proxy, `.gitignore`, `.env.example` | infra |
| M1 | Paper search: arXiv + OpenAlex clients, `/api/search`, search UI with result cards | F1 |
| M2 | SQLite library: paper model, save / list / get / delete endpoints, library UI, de-duplication | F2 |
| M3 | PDF upload + processing: upload endpoint, PDF storage, text + metadata extraction, full-text fetch for saved search papers, editable metadata | F3 |
| M4 | LLM: Claude integration, streamed summary, streamed Q&A chat with persisted history, LLM-assisted metadata extraction | F4, F5 |
| M5 | README, INSTALL.md + setup script, single-process production build, end-to-end verification | submission |
| M6 | Reader for every paper: search results open without saving (`POST /api/papers/open`), and library papers use the same reader; section outline with one-sentence summaries on click, PDF viewer (react-pdf), Q&A; unsaved papers pruned after `CACHED_PAPER_DAYS`; model menu for section summaries, the summary, and Q&A; OpenAlex as the default search source; arXiv rate-limit handling and a 10-minute search cache; PDF downloads only from public addresses | F1-F5 usability |
