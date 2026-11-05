# Test review rubric (used in every phase)

The oracle is the app's **intended behavior**, never its current output:

1. HW1 requirements F1 to F5 and their acceptance criteria (`docs/REQUIREMENTS.md`, `hw1.pdf`)
2. Behavior the app documents for users: README, INSTALL.md, UI text
3. Intent stated in code comments and docstrings (for example "saving a paper that
   is already saved returns the existing entry", "unsaved papers are deleted after
   7 days without being opened")

Each test gets exactly one primary category.

| Category | Meaning | Example |
|----------|---------|---------|
| OK | Checks intended behavior with correct inputs, correct expected values, and an assertion that would fail if that behavior broke | Save the same paper twice; assert the second call returns 200 and the same id |
| WEAK | Checks the right behavior, but the assertion would still pass under a plausible bug | Only `status_code == 200`; only `is not None` or `len(x) > 0`; a mock was called, arguments unchecked |
| WRONG | The expectation contradicts intended behavior, the inputs make the check meaningless, or the test passes for the wrong reason | Asserts a bug's output as correct; asserts on the mock's return value instead of the app's |
| REDUNDANT | Same behavior, same kind of input, and same assertions as another test; adds no detection power | Two tests that save one paper and check the same fields |
| BRITTLE | Checks an implementation detail that is not part of any requirement, so a correct refactor would break it | Exact prompt wording; private helper's internal call order |
| FLAKY | The outcome depends on network, wall-clock time, test order, the machine's `.env`, the real `claude` CLI, or sleeps | Calls live arXiv; relies on another test's database rows |

Additional checks per suite:

- **Missing tests**: requirement-level behaviors and error paths no test exercises
  (listed against F1 to F5 and the main error-handling paths).
- **Failing tests**: each one is triaged as **APP BUG** (the app violates intended
  behavior; recorded as BUG-n with the detecting tests) or **TEST BUG** (the test's
  expectation or setup is wrong). Evidence for the call is written down.
- **Isolation**: whether tests can touch the user's real data (`backend/data`), the
  real LLM, or the network; whether the suite runs from a clean clone.

Classification is done by reading every test against the oracle. Borderline cases
are noted with the reason.
