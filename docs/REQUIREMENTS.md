# Requirements (from HW1 spec)

Source: `hw1.pdf` — "Homework 1: Build an AI Research Assistant with a Coding Agent".
Due Oct 10, 11:59 PM. App = 60% of grade, reflection report = 40%.

## Functional requirements

| ID | Requirement | Acceptance criteria |
|----|-------------|---------------------|
| F1 | Search for research papers | User enters keywords/topic; app queries a public paper-search API; each result shows **title, authors, publication year, abstract, link** (when available). |
| F2 | Save papers to a local library | User selects search results and saves them to a **local database**. Saved papers **survive app restart and page refresh**. User can **browse** saved papers. |
| F3 | Upload PDF papers | User uploads a PDF; it is added to the local database; app **extracts title, authors, year, abstract** and renders the paper like a search result. |
| F4 | Summarize papers with an LLM | User selects a paper and asks an LLM for a summary. The summary must be **based on the paper's content**, not just title/metadata. |
| F5 | Ask questions about a paper | User asks natural-language questions about a selected paper (problem addressed, main idea, datasets, limitations, comparison with baselines, ...). |

## Required components

- [ ] Graphical user interface
- [ ] Frontend and backend logic
- [ ] Integration with at least one external API (paper search)
- [ ] Local database to store and retrieve papers
- [ ] PDF upload and processing
- [ ] LLM API integration for summarization and Q&A

## Constraints

- Any language / framework / database / LLM.
- Not production quality — a reasonably functional end-to-end system.
- Testing is not the focus of HW1 (HW2 will add tests).
- **Never commit API keys, passwords, or other credentials.**
- Use the coding agent throughout development (planning, setup, implementation,
  integration, debugging, refactoring, deployment) — not just for a skeleton.

## Submission deliverables

1. **GitHub repository** — complete source, README with setup + run instructions,
   description of major features, dependency/config files. A reader should
   understand the structure and be able to run it.
2. **Demo video** showing: (1) searching for a paper, (2) saving a paper to the
   library, (3) uploading a PDF, (4) generating a summary, (5) asking at least one question.
3. **Reflection report** discussing:
   1. Which coding agent was used and how.
   2. Where the agent was particularly useful.
   3. Where it produced incorrect/incomplete/unsatisfactory code, what happened, and
      how it was addressed — **with screenshots** of prompts, agent output, and corrections.
   4. How much agent-generated code needed inspection / modification / debugging.
   5. Lessons about communicating with and controlling a coding agent.
