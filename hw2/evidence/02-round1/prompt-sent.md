# Round 1 prompt (sent verbatim to a fresh-context Claude Code subagent)

Date: 2026-11-04. Strategy: **requirements + review findings + coverage report**.
The agent gets the curated feedback in `feedback-round1.md` (copied here). That file
states intended behavior for every problem but deliberately does not list the
application bugs the review found; those are reserved for round 2's execution
feedback. The agent never sees the held-out faults or the mutation results.

```text
You are working in the repository at
/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant. Work only inside
this directory, except for reading the feedback file named below.

Operating constraints from the repository owner:
- Do not commit, push, or create branches; leave your changes in the working tree.
- Do not modify, move, or delete anything in demo/ (personal recordings).
- The owner may be running the app on ports 8000 and 5173. Do not stop those
  processes; if you need to start servers, use other ports.

Task from the repository owner (round 1 of improving the test suite):

The automated tests in backend/tests, frontend/src (*.test.ts, *.test.tsx), and
frontend/e2e were evaluated against the application's intended behavior. They all
pass, but the evaluation found weak, wrong, brittle, redundant, and flaky tests,
and important behavior that no test checks. The feedback is in
/private/tmp/claude-501/-Users-hongxiangzhang-Documents-593-demo/a3b69e76-b3cf-4951-98bc-3c2b2be9df6d/scratchpad/round1-input/feedback-round1.md.
Read it first.

1. The requirements and documented behavior are the source of truth:
   docs/REQUIREMENTS.md, README.md, INSTALL.md, and intent stated in code
   comments. Never change an expected value only to match what the code
   currently does.
2. Fix the tests listed in section 2 of the feedback: strengthen weak
   assertions, correct wrong tests, make brittle tests check behavior instead of
   implementation details, make flaky tests deterministic, and delete or
   repurpose redundant ones. Fix the test-infrastructure problems in section 2.6.
3. Add tests for the untested behavior in sections 3 and 4, starting with
   requirement-level behavior and error handling. Prefer fewer, stronger tests:
   each new test should fail if the behavior it names broke.
4. Do not modify application code. If a correct test fails because the
   application does not behave as intended, keep the test, mark it as an
   expected failure (pytest.mark.xfail(strict=True, reason=...) or Vitest's
   it.fails) and report it as a suspected application bug with your evidence.
5. Run all three suites (make test) and report: what you changed for each
   feedback item, items you did not address and why, test counts before and
   after, the results of the last run, and every suspected application bug.
```
