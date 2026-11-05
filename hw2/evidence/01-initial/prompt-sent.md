# P1 prompt (sent verbatim to a fresh-context Claude Code subagent)

Date: 2026-11-04. Agent: Claude Code subagent (general-purpose), started with no
conversation history. The "Task" block is the student-approved prompt from
`PLAN.md` (P1), unchanged. The lines before and after it are operational
constraints for the shared machine; they do not describe what to test.

```text
You are working in the repository at
/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant. Work only inside
this directory.

Operating constraints from the repository owner:
- Do not commit, push, or create branches; leave your changes in the working tree.
- Do not modify, move, or delete anything in demo/ (personal recordings).
- The owner may be running the app on ports 8000 and 5173. Do not stop those
  processes; if you need to start servers, use other ports.

Task from the repository owner:

Examine the AI Research Assistant application in this repository (FastAPI
backend in backend/, React + TypeScript frontend in frontend/) and generate an
initial automated test suite for it.

Cover the main functionality: searching for papers, saving papers to the
library, uploading PDFs and extracting their metadata, generating summaries,
and asking questions about a paper. Include normal use cases, edge cases, and
error handling.

Use pytest for the backend and Vitest with React Testing Library for the
frontend. Add Playwright end-to-end tests if you think they are useful. Every
test must run with a single command and contain assertions that check the
application's expected behavior. Tests must not call the real LLM, which costs
money. Do not modify application code; if something cannot be tested without a
change, say so instead. Run the tests and report the results.

When you finish, reply with: the files you created or changed, the commands to
run the tests, the test counts and results of your last run, and anything you
could not test.
```
