# Requirements

Source: `hw1.pdf`, "Homework 1: Build an AI Research Assistant with a Coding Agent"
(the course handout, which is not committed to this repository).
Due Oct 10, 11:59 PM. Weight: 10% of the final course grade. The app is 60% of the
homework grade and the reflection report is 40%. The last section lists requirements
the user added during development.

## Functional Requirements

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| F1 | Search for research papers | User enters keywords/topic; app queries a public paper-search API; each result shows **title, authors, publication year, abstract, link** (when available). |
| F2 | Save papers to a local library | User selects search results and saves them to a **local database**. Saved papers **survive app restart and page refresh**. User can **browse** saved papers. |
| F3 | Upload PDF papers | User uploads a PDF; it is added to the local database; app **extracts title, authors, year, abstract** and renders the paper like a search result. |
| F4 | Summarize papers with an LLM | User selects a paper and asks an LLM for a summary. The summary must be **based on the paper's content**, not just title/metadata. |
| F5 | Ask questions about a paper | User asks natural-language questions about a selected paper (problem addressed, main idea, datasets, limitations, comparison with baselines, ...). |

## Required Components

Each item names where the app meets it.

- [x] Graphical user interface: the React app in `frontend/src` (search page, library
  page, and reader).
- [x] Frontend and backend logic: the React frontend and the FastAPI backend in
  `backend/app`, connected through the JSON API under `/api`.
- [x] Integration with at least one external API for paper search or related
  functionality: OpenAlex (the default) and arXiv, behind `GET /api/search`
  (`backend/app/services/openalex.py`, `backend/app/services/arxiv.py`).
- [x] Local database to store and retrieve papers: SQLite through SQLAlchemy
  (`backend/app/db.py`, `backend/app/models.py`), in `backend/data/app.db` by default.
- [x] PDF upload and processing: `POST /api/papers/upload` stores the PDF and extracts
  its text with PyMuPDF (`backend/app/services/pdf.py`). The title, authors, year, and
  abstract come from arXiv, the model, or layout heuristics, in that order.
- [x] Integration with an LLM API to summarize papers and answer user questions:
  Claude, through `backend/app/services/llm.py` (`POST /api/papers/{id}/summary` and
  `POST /api/papers/{id}/chat`). The API provider (`LLM_PROVIDER=api`) calls the
  Anthropic API. The default Claude Code provider reaches Claude through the local
  `claude` CLI and the user's login.

## Constraints

- Any language / framework / database / LLM.
- The app does not need to be production quality. It should be a reasonably
  functional end-to-end system.
- Testing is not the main focus of HW1 (HW2 will add tests).
- **Never commit API keys, passwords, or other credentials.**
- Use the coding agent throughout development (planning, setup, implementation,
  integration, debugging, refactoring, deployment), beyond generating an initial code
  skeleton.
- The student remains responsible for the final application: understand its major
  components and verify that agent-generated code behaves correctly.

## Submission Deliverables

1. **GitHub repository:** complete source code, a README with setup and run
   instructions, a description of the major features, and any necessary dependency and
   configuration files. Someone following the README should understand how the app is
   structured and how to run it.
2. **Demo video** showing: (1) searching for a paper, (2) saving a paper to the
   library, (3) uploading a PDF, (4) generating a summary, (5) asking at least one question.
3. **Reflection report** discussing:
   1. Which coding agent was used and how.
   2. Where the agent was particularly useful.
   3. Where it produced incorrect/incomplete/unsatisfactory code, what happened, and
      how it was addressed. Include **screenshots** that show the prompts, the agent's
      reasoning or intermediate output when visible, the code it proposed, and the
      follow-up corrections.
   4. How much agent-generated code needed inspection / modification / debugging.
   5. Lessons about communicating with and controlling a coding agent.

## Requirements Added During Development

The user added these requirements while the app was being built.

| Requirement | How the app meets it |
|-------------|----------------------|
| Use the Claude Code installed on the machine by default, with no API key | The Claude Code provider (`LLM_PROVIDER=claude-code`, the default) runs the local `claude` CLI with the user's own login (`backend/app/services/claude_code.py`). The API provider (`LLM_PROVIDER=api`) remains available. |
| No Docker; set up the required libraries and environment with a script, and document them | `scripts/setup.sh` checks the tools, installs the locked packages, and creates and validates `.env`. `INSTALL.md` documents every requirement. The M5 Dockerfile was removed because Docker was not installed, so it could not be tested. |
| Open a search result in the app without saving it: the PDF, the paper's sections with one-sentence summaries, and Q&A | Clicking a result's title or "Read" calls `POST /api/papers/open` and opens the reader with an unsaved paper. "Save to library" (`POST /api/papers/{id}/save`) keeps its chat and section outline. |
| Section summaries only on click | "Summarize sections" (`POST /api/papers/{id}/outline/summaries`) writes them only when clicked. |
| The same reader for library papers | Library papers, uploads, and unsaved papers all open in `frontend/src/pages/PaperPage.tsx`. |
| Switch models | The model menu in the reader header. Claude Code provider: `opus`, `sonnet`, `haiku`, `fable`, `default`. API provider: `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5-1`. The backend rejects other ids with 422. |
| Keep unsaved papers for 7 days | `CACHED_PAPER_DAYS` defaults to 7. Unsaved papers not opened for that long are deleted at startup and every 12 hours. |
