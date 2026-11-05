# Round 2 prompt (sent verbatim to a fresh-context Claude Code subagent)

Date: 2026-11-04. Strategy: **execution feedback and owner decisions**: the owner's answers about the suspected bugs, a code review of round 1's changes with each claim checked by running the tests, a parallel test run, and serial mutation testing of the backend (`feedback-round2.md`, with the 619 surviving mutants in `mutation-survivors.md` beside it).

```text

You are working in the repository at
/Users/hongxiangzhang/Documents/593-demo/AI_Research_Assistant. Work only inside
this directory, except for reading the feedback file named below.

Operating constraints from the repository owner:
- Do not commit, push, or create branches; leave your changes in the working tree.
- Do not modify, move, or delete anything in demo/ (personal recordings).
- The owner may be running the app on ports 8000 and 5173. Do not stop those
  processes; if you need to start servers, use other ports.

Task from the repository owner (round 2 of improving the test suite):

The test suite was improved once already and is committed. It was then run in a
clean checkout and measured. The feedback from those runs is in
/private/tmp/claude-501/-Users-hongxiangzhang-Documents-593-demo/a3b69e76-b3cf-4951-98bc-3c2b2be9df6d/scratchpad/round2-input/feedback-round2.md.
Read it first. It has three parts: the owner's decisions about the suspected
application bugs, a code review of the previous round's changes (each claim
checked by running the tests), and mutation testing of the backend, which lists
code changes that no test notices.

1. Apply the owner's decisions in section 1. Keep exactly one clear expected
   failure per confirmed bug, and turn the item the owner declared intended into
   a normal test.
2. Fix every problem in section 2. Where an earlier fix deleted a check, replace
   it with a check of the same behavior; do not just restore an implementation
   detail.
3. For the surviving mutants in section 3, add or strengthen tests so that the
   behavior each mutant breaks is checked. Assert observable behavior that a
   user or caller relies on; do not write tests that only target one mutant's
   exact code. If a mutant cannot change any observable behavior (an equivalent
   mutant), say so instead of testing it.
4. Do not modify application code, and never weaken an expectation to make a
   test pass.
5. Run all three suites (make test) and report: what you changed for each
   feedback item, mutants you judged equivalent and why, test counts before and
   after, and the results of the last run.
```
