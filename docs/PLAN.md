# Implementation plan

## Architecture

```
 Browser (React + Vite + TS)
        │  /api/*  (JSON, streamed text for LLM output)
        ▼
 FastAPI backend (Python 3.11)
   ├── search service ──► arXiv API, OpenAlex API        (F1)
   ├── library (SQLAlchemy) ──► SQLite  data/app.db      (F2)
   ├── PDF service (PyMuPDF) ──► data/pdfs/*.pdf         (F3)
   └── LLM service ──► Anthropic Claude API               (F4, F5)
```

### Key design decisions

- **Search sources:** arXiv (no key, always has a PDF → full text available) and
  OpenAlex (no key, broad cross-publisher coverage, open-access PDF links when they exist).
  Semantic Scholar was considered but returns HTTP 429 without an API key.
- **Content-based LLM answers (F4/F5):** every paper gets a `full_text` column.
  Uploaded PDFs are parsed on upload; saved search results have their open-access
  PDF downloaded and parsed on demand. The LLM prompt contains the full text
  (truncated to a configurable limit), so summaries/answers are grounded in the
  paper body, not just metadata. If no PDF is obtainable the app falls back to the
  abstract and says so explicitly in the UI.
- **Metadata extraction from uploads (F3):** an arXiv-ID lookup → LLM
  extraction from the first pages → font-size/regex heuristics, in that order of
  preference; the user can edit fields afterwards.
- **LLM:** Claude (`claude-opus-5` by default, set by `LLM_MODEL`) through the
  official `anthropic` SDK, with streaming, adaptive thinking, and server-side
  refusal fallbacks. The paper sits in the system prompt behind a prompt-cache
  breakpoint, so the summary and every follow-up question reuse it. An
  OpenAI-compatible provider was planned at first, but was dropped to keep a
  single, well-supported integration.
- **Persistence:** SQLite file under `backend/data/` (git-ignored). Summaries and
  Q&A history are stored too, so they survive restarts.
- **Secrets:** read from `.env` (git-ignored); `.env.example` documents the variables.
- **Deployment:** `npm run build` produces static assets that FastAPI serves, so the
  whole app runs as one process on one port.

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
| M5 | README, single-process production build, deployment config, end-to-end verification | submission |
