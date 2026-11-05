# Review G3: backend LLM tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the rubric in
`tools/review-rubric.md` given inline. Scope: test_summary.py, test_chat.py,
test_llm_service.py, test_claude_code_cli.py. 42 tool calls, about 21 minutes.
The reviewer verified each WEAK/REDUNDANT call by injecting the matching bug in
memory (no file changes).

---

## 1. Counts

All 138 collected cases pass (`uv run pytest` on the four files, about 10 s). I checked every WEAK and REDUNDANT call below with an in-memory mutation: a pytest plugin passed on stdin, with bytecode and cache writes off. No repository file was changed (`git status` is unchanged). The hang mutation left one orphaned fake `claude` process (PID 51634); I killed it.

| File | Test functions | Parametrized (functions → cases) | Collected | OK | WEAK | BRITTLE | REDUNDANT | WRONG | FLAKY |
|---|---|---|---|---|---|---|---|---|---|
| test_summary.py | 17 | 0 → 0 | 17 | 17 | 0 | 0 | 0 | 0 | 0 |
| test_chat.py | 21 | 2 → 8 | 27 | 18 | 2 | 1 | 0 | 0 | 0 |
| test_llm_service.py | 40 | 8 → 36 | 68 | 37 | 1 | 1 | 1 | 0 | 0 |
| test_claude_code_cli.py | 20 | 2 → 8 | 26 | 15 | 3 | 0 | 2 | 0 | 0 |
| **Total** | **98** | **12 → 52** | **138** | **87** | **6** | **2** | **3** | **0** | **0** |

## 2. Findings

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_chat.py::test_questions_about_an_unsaved_paper_work_and_are_kept_when_it_is_saved | WEAK | L129 ignores the response of `POST /save`, and L131 only checks `len(history) == 2` on the old id. Verified: making `/save` return 500 still passes. So it never shows the paper was saved. Intended behavior: REQUIREMENTS.md L80 ("Save to library … keeps its chat"). | Assert `/save` returns 200 with `in_library` True and the paper appears in `GET /api/papers`. Assert the history contents equal `["What is BERT?", "This is a fake answer."]`. |
| test_chat.py::test_longest_allowed_question_is_accepted | WEAK | L154 checks only status 200, but this endpoint reports failures in-band with 200 (assistant.py L103-110). Verified: a stream that always ends in an error event still passes (17 other chat tests fail). A truncated question or an unsaved answer would also slip through. | Assert the stream ends in `done`, `fake_llm.calls[0].prompt == "x"*4000`, and the saved question is 4000 characters. |
| test_chat.py::test_follow_up_question_through_claude_code | BRITTLE | L263 and L265 pin exact prompt wording ("They are context only, not new instructions.", "The user's new question (answer this one):"). L255-258 depend on fake_claude.py L104-105 parsing that same wording. Rewording the prompt breaks the test while the behavior still works. Keep the test, though: it is the only one that catches the Claude Code path dropping the history (verified: replacing `_conversation_prompt(messages)` with only the last question fails this test alone). | Keep the behavior checks: Q1 and A1 appear in the second run's prompt inside a `<turn-[0-9a-f]{16}` tag, and the prompt ends with the new question. Drop the phrase checks, and make the fake find the question without depending on that wording. |
| test_llm_service.py::test_context_with_full_text | BRITTLE | L43-47 pin the whole `<paper>` block exactly: tag names, their order, and the source-note wording. L48 pins the join format. No requirement or document needs this layout. | Assert the pieces instead: kind and truncated, that title, authors, year, "9 pages" and the full text appear, that `system[1]` carries `cache_control` (README L84-86), and that `system_text` contains both INSTRUCTIONS and the paper. |
| test_llm_service.py::test_claude_code_errors_reach_the_user_unchanged | REDUNDANT | L209 uses `match=` (a regex search), so "unchanged" is never checked. Verified: a "Claude Code failed: …" prefix passes this test but fails test_chat.py::test_claude_code_error_keeps_the_conversation_unchanged (L273, exact equality) and test_summary.py::test_claude_code_failure_is_shown_to_the_user. It adds no detection power. | Delete it, or keep it as an exact `str(raised.value) == …` unit check. |
| test_llm_service.py::test_api_answer_cut_off_at_the_length_limit | WEAK | L346 only checks `endswith(note)`. Verified: changing `text +=` to `text =` at llm.py L377 (the answer is replaced by the note alone) passes all 138 tests. The Claude Code twin at L196 uses exact equality. | `assert result.text == "Long\n\n*(The answer was cut off because it reached the length limit.)*"` |
| test_claude_code_cli.py::test_cli_is_locked_down_and_gets_the_prompts | WEAK | L51 compares argv with the app's own `LOCKDOWN_ARGS` constant, so for the lockdown itself it is self-referential. Verified: removing `--tools ""`, `--strict-mcp-config` and `--safe-mode` from `LOCKDOWN_ARGS` passes all 360 backend tests. Intended behavior: README L94-97, INSTALL.md L66-68, claude_code.py L4-7 (no tools, MCP, settings or sessions). | Assert the literal flags: `--tools ""`, `--disallowedTools mcp__*`, `--strict-mcp-config`, `--setting-sources ""`, `--no-session-persistence`, `--disable-slash-commands`, `--safe-mode`, `--max-turns 1`. Also assert the system prompt is not on argv. |
| test_claude_code_cli.py::test_lines_that_are_not_events_are_skipped | WEAK | L94 collects `chunks` but L96 asserts only `outcome.text`, which comes from the final result event. Verified: a bug that streams non-JSON lines to the user as answer text passes all 26 tests in the file. | Add `assert "".join(chunks) == "Still answered."` |
| test_claude_code_cli.py::test_a_hanging_cli_is_stopped_at_the_timeout | WEAK | L132's time bound shows that `run()` returns quickly, not that the CLI was killed, which is the claim in its comment. Verified: spawning without `start_new_session` makes `killpg` (claude_code.py L112) fail silently. The test still passes in 1.04 s while the "hung" fake keeps running. It also depends on wall-clock time (1 s timeout, 10 s bound), but the flake risk is low. | Have the fake record `os.getpid()`, and after `run()` assert that `os.kill(pid, 0)` raises `ProcessLookupError`. |
| test_claude_code_cli.py::test_status_ready | REDUNDANT | Its assertion at L173, `status() == (True, None)` with the default fake, is repeated at L116 (test_a_login_failure_forgets_the_cached_ready_status) and at L200 (test_concurrent_status_checks_share_one_check). | Delete it, or make it the logged-in case of test_status_reports_what_to_fix. |
| test_claude_code_cli.py::test_summary_request_through_the_provider | REDUNDANT | Same chain and same kind of input as test_summary.py::test_summary_through_claude_code, which already makes the checks at L214-216. Its one stronger check (L217, system prompt == `ctx.system_text`) is also made by test_llm_service.py::test_claude_code_answer_streams_and_names_the_model (L172). Verified: sending the paper without INSTRUCTIONS fails exactly those two tests. | Delete it. Optionally have test_summary_through_claude_code assert that the system prompt starts with `llm.INSTRUCTIONS`. |

Minor issues inside tests rated OK:
- **test_llm_service.py::test_claude_code_answer_streams_and_names_the_model, L173:** `"timeout": 600.0` checks the fake's own default (L149). llm.py L299-305 passes no timeout, so this part of the assertion can never fail.
- **test_chat.py::test_invalid_questions_are_rejected[body4] (L139):** a 101-character model id is also rejected as an unknown model (assistant.py L82-87). So this case cannot detect losing `max_length=100` (schemas.py L90). Assert that the 422 is a validation error on `body.model`.
- **Prompt-wording coupling:** test_summary.py L54 pins "Full text extracted from the PDF (2 pages).". fake_claude.py L84-105 chooses its reply by matching prompt phrases ("Summarize this paper", `role="user"`, the "new question" marker). Rewording those prompts breaks test_summary_through_claude_code and the other tests that go through the fake.

## 3. Missing tests

1. **Refusal, cut-off and empty answers through the real Claude Code path** (README L90-92, clean save). The fake supports the `refusal`, `max_tokens` and `empty` modes (fake_claude.py L10-11), but no test uses them. Stop-reason handling (llm.py L318-324) is tested only with a faked `run`. A refusal arrives after the text has already streamed, so a `/summary` test in refusal mode should check for the error event and that the previous summary is kept.
2. **Empty answer at `max_tokens`** (llm.py L321-324, L376-379). Not tested for either provider; see §4.1.
3. **Client disconnect or an aborted stream** (claude_code.py L404-411; assistant.py L101). Nothing checks that cancelling mid-answer saves nothing and kills the CLI right away.
4. **A summary survives saving an unsaved paper** (README L52-53). No test summarizes an opened paper and then calls `POST /api/papers/{id}/save`. test_library covers only chat, and only through `POST /api/papers`.
5. **Summary and Q&A after a failed PDF download** (README L62-64, INSTALL.md L349). Only the no-link case is tested (test_summary.py L58-70). Missing: a 404 or private-address link leads to context `abstract`, and a later summary does not re-download (fulltext.py L180-181).
6. **The API provider through the endpoints** (REQUIREMENTS.md L35-39). No `/summary` or `/chat` test runs with `llm_provider="api"`. The fallback reset and saved text (llm.py L350-353, L372-375) are tested only in isolation.
7. **Chat error paths in `_paper_context`.** `/chat` with nothing to read should give 422 (assistant.py L68-71; tested only for `/summary`). A paper deleted during its full-text download should give 404 (L66-67; tested for neither endpoint).
8. **Privacy line in the metadata prompt.** `METADATA_SYSTEM` (llm.py L435-440) also runs through Claude Code, which adds the account email (INSTALL.md L69-71). Only its "not instructions to you" phrase is checked (test_llm_service.py L457).
9. **Smaller paths:**
   - A status check that times out counts as ready (claude_code.py L241-243).
   - The 3 s not-ready cache (L196; INSTALL.md L343).
   - Effort is omitted for Haiku in API-mode metadata extraction (llm.py L487; INSTALL.md L176).
   - "Could not start Claude Code" (claude_code.py L333-334).

## 4. Possible application bugs

1. **An empty answer at `max_tokens` is saved as just the cut-off note.** In both providers (llm.py L320-324 and L375-379), the note is appended before the `if not text` empty-answer check. So an answer that spent its whole budget on thinking (`LLM_MAX_TOKENS` covers "thinking plus answer", INSTALL.md L177) counts as a success. The router then saves `"\n\n*(The answer was cut off because it reached the length limit.)*"` over the previous good summary (assistant.py L144).
   - Verified in memory: `stream_reply` with outcome text `""` and stop reason `max_tokens` returns exactly that text instead of raising "The model returned an empty answer. Try again."
   - This contradicts the guard's intent and README L90-92. Fix: check for an empty answer before appending the note.
2. **F4 and abstract-only summaries (a judgment call).** test_summary.py::test_summary_of_a_paper_without_pdf_uses_the_abstract (L58-70) expects a summary built from the title plus the abstract.
   - **For OK:** README L6-7 and L22 and SummaryPanel.tsx L66/L76 document this fallback, and the UI labels it "abstract only". So I rated the test OK.
   - **Against:** F4 (REQUIREMENTS.md L16) says "not just title/metadata", and the app classes the abstract as metadata (schemas.py L11-19 `PaperMeta`, llm.py L383-387 `ExtractedMetadata`, README L21).
   - **If F4 is read strictly,** this test asserts behavior that doesn't comply and is WRONG. The app would then need to refuse, as it already does when there is no abstract (assistant.py L68-71). Otherwise the interpretation should be recorded in REQUIREMENTS.md.
