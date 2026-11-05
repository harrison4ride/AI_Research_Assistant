# Final review G3: backend summary, chat, LLM service, and Claude Code CLI tests (verbatim reviewer report)

Reviewer: fresh-context Claude Code subagent, read-only, with the prompt in
`prompts/G3.txt` (the initial review's prompt plus the new helpers and one sentence on
expected failures). Suite: tag `hw2-round2`. 65 tool calls, about 368k tokens,
44 minutes. Its load test (16 CPU-bound processes,
about 21:43 to 21:54) overlapped the serial mutation run; see `evaluation.md` for how
the mutation timeouts were rechecked.

---

I've finished the review; nothing in the repository was changed. The four files have 113 test functions (167 collected cases). All pass, with 2 expected failures (known bugs). 104 tests are OK, 9 are not: 5 WEAK, 2 BRITTLE, 2 REDUNDANT, and none WRONG or FLAKY. I confirmed each weakness by running an in-memory mutant against the whole backend suite (553 passed, 5 expected failures as the baseline). A control mutant was caught by 11 tests; each mutant named below passed the entire suite.

## 1. Counts

| File | Test functions | Parametrized | Collected | OK | WEAK | WRONG | REDUNDANT | BRITTLE | FLAKY |
|---|---|---|---|---|---|---|---|---|---|
| test_summary.py | 23 | 3 functions, 6 cases | 26 | 21 | 1 | 0 | 0 | 1 | 0 |
| test_chat.py | 23 | 2 functions, 8 cases | 29 | 20 | 2 | 0 | 1 | 0 | 0 |
| test_llm_service.py | 46 | 9 functions, 47 cases | 84 | 43 | 2 | 0 | 0 | 1 | 0 |
| test_claude_code_cli.py | 21 | 3 functions, 10 cases | 28 | 20 | 0 | 0 | 1 | 0 | 0 |
| **Total** | **113** | 17 functions, 71 cases | 167 | 104 | 5 | 0 | 2 | 2 | 0 |

## 2. Findings

| file::test_name | category | reason (with line numbers) | how to fix it |
|---|---|---|---|
| test_summary.py::test_regenerating_replaces_the_summary | WEAK | L136-145 checks only the summary text and model. Two plausible bugs pass the whole suite: keeping the old `summary_created_at`, or keeping the old `summary_context` (assistant.py:146-147). The Summary tab shows both (SummaryPanel.tsx:64-67; README:22 says summaries show which model wrote them and whether the full text or only the abstract was used). | Assert the second `summary_created_at` is later than the first. Add a case: summary from the abstract, attach a PDF, regenerate, expect `summary_context == "full_text"`. |
| test_summary.py::test_a_pdf_longer_than_the_page_limit_is_reported_as_cut_off (known bug) | BRITTLE | L214 requires the words "cut off" in the prompt's source note, but README:87-89 only requires that the prompt tells the model. I applied a correct fix in memory that worded the note "Only the first 300 of the PDF's pages were extracted…". The test stayed an expected failure, so the strict xfail hides that fix. The same fix worded with "cut off" turns it into XPASS. The UI check (L213) is right, and today the test fails only because of the named bug. | Keep L213. Replace L214 with a check that doesn't depend on wording, e.g. the note must no longer be `"Full text extracted from the PDF (302 pages)."`. Or use one shared cut-off note for both truncation cases and assert it. |
| test_chat.py::test_questions_about_an_unsaved_paper_work_and_are_kept_when_it_is_saved | REDUNDANT | L138-150 duplicates test_library.py::test_saving_an_opened_paper_keeps_its_summary_section_summaries_and_conversation[reader] (test_library.py:750-781). Both open an unsaved result, ask a question, save it from the reader, and assert status 200, the same id, the library list and the stored Q&A. The library test also checks the summary and the outline. | Delete it, or make it add something: e.g. ask again after saving and assert the earlier turn reaches the model. |
| test_chat.py::test_conversations_are_kept_per_paper | WEAK | L234-241 asks only about the first paper and checks history lengths. The history query sent to the model (assistant.py:169-171) never runs with two papers. Removing its paper filter passes the whole suite, so a question about paper B would carry paper A's conversation (README:23, "saved per paper"). L240 checks only a length. | Ask about the second paper too and assert `fake_llm.calls[-1].messages` holds only that question. Compare contents, not lengths. |
| test_chat.py::test_clear_conversation | WEAK | L244-253 uses a single paper. Removing the paper filter from the delete (assistant.py:260) wipes every paper's conversation and still passes the whole suite. | Give a second paper a conversation and assert it is unchanged after clearing the first. |
| test_llm_service.py::test_the_source_note_mentions_the_page_count_only_when_it_is_known | BRITTLE | L74's only assertion is the exact prompt sentence "Full text extracted from the PDF.". The page count in the note is documented nowhere, so any rewording fails the test. The bug it targets ("(None pages)") can be caught without pinning the sentence. | Assert `"None" not in note` and that the note mentions no page count. |
| test_llm_service.py::test_instructions_treat_the_paper_as_data_and_protect_privacy | WEAK | L112-113 checks two substrings of the `INSTRUCTIONS` constant. README:97-99 and INSTALL.md:69-71 promise the model is told not to repeat the email and environment details (directory, OS, shell). Deleting ", or details about their computer (paths, operating system, shell)" (llm.py:47-48) passes the whole suite. The test also pins exact wording and reads the constant instead of the prompt actually sent. | Assert each documented rule (paper is data; no email; no paths/OS/shell; no images/HTML) appears in `context().system_text` and in the metadata system prompt, ideally through one shared constant. |
| test_llm_service.py::test_configured_default_model_is_added_to_the_menu | WEAK | L143-144 checks only the first menu entry and that the `.env` model resolves. If the `.env` model replaces the whole menu (llm.py:240 without `*choices`), the whole suite still passes, yet the menu would offer one model and "sonnet" would get a 422. README:47-49 and INSTALL.md:171 say such a model is added to the menu. | Assert the full list (the `.env` entry, then the five standard ones) and that `resolve_model("sonnet") == "sonnet"`. |
| test_claude_code_cli.py::test_status_is_cached_briefly | REDUNDANT | L223-227 (two back-to-back status checks, two CLI calls) is fully covered by test_not_ready_is_rechecked_after_3_seconds_and_ready_after_30, L250-252, which asserts a ready result is reused 29.9 s later with no new call. | Delete it. |

Notes on tests I kept OK:
- **Prompt-wording pins** inside otherwise sound tests break on a rewording, not on a behavior change:
  - test_summary L193
  - test_llm_service L85-86, L107-108, L177-181, L499-503, L598, L625-627
  - test_claude_code_cli L75 and L81 (temp file and folder names)
- **Misleading name:** test_summary_when_claude_code_is_not_installed (L343-350) actually tests a `CLAUDE_CODE_PATH` that points at a missing file, as conftest sets it. The real "not installed" hint is never checked end to end.
- **Loose count:** test_incomplete_section_summaries_are_rejected (L612) matches `skipped \d of 2`, so a wrong count in the user-facing message would pass.
- **Partly checks its fake:** in test_restarted_answer_discards_the_earlier_text, the saved text is discarded by `FakeLLM` (fake_llm.py:76-78), not the app. It still catches real router bugs: dropping or reordering the `reset` event, or saving the concatenated stream instead of the final text. The provider's own discard logic is tested in test_api_fallback_restarts_the_answer.
- **Timing:** test_leaving_while_an_answer_streams… and test_a_hanging_cli_is_stopped_at_the_timeout use real time, but with wide margins. Both passed 25 of 25 runs, 10 of them under 16 busy loops on 8 cores.
- **Other known-bug test:** test_an_empty_answer_cut_off_at_the_length_limit_is_an_error turns into XPASS when the plausible fix is applied, so it fails only because of the bug it names.

## 3. Missing tests
Each item below was either never executed by the whole suite, or a mutant of it passed the whole suite.

- **F4 summaries:** regenerating refreshes the timestamp, and switches the label from abstract to full text after a PDF is attached (assistant.py:144-147).
- **F5 questions:**
  - The model's history is limited to this paper (assistant.py:169-171).
  - Clearing affects only this paper (assistant.py:260).
  - The race where a paper is deleted between the check and the commit while an answer is saved (assistant.py:188-191) never runs.
- **Model menu and settings (README "Switch models", INSTALL settings table):**
  - The menu keeps its standard entries when the `.env` default isn't one of them (llm.py:239-240).
  - `LLM_EFFORT` (llm.py:303, 344) and `LLM_MAX_TOKENS` (llm.py:338) are only tested at their defaults; hard-coding `"medium"` or `32000` passes.
  - `CLAUDE_CODE_MODEL` for upload metadata (llm.py:459) is only tested at its default; hard-coding `"opus"` passes.
  - `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` reaching the API client (llm.py:106-113) never run, because the client is always faked.
- **Claude Code robustness (claude_code.py docstrings; DEVLOG:373, 384, 386):**
  - Returning at the result event even when output stays open: removing the `break` at claude_code.py:403 passes, because the fake CLI always closes its output right away.
  - Signalling the whole process group: `os.kill` instead of `os.killpg` (claude_code.py:112) passes, because the fake never starts a helper process.
  - Escalating to SIGKILL when SIGTERM is ignored (claude_code.py:146-147) never runs.
  - The overall deadline while the CLI keeps streaming (claude_code.py:369-371) never runs.
  - Skipping an over-long output line (claude_code.py:376-378) never runs.
  - The temp folder is removed when the CLI can't start (claude_code.py:412-414): disabling it passes, because the test checks only the message.
  - An error result with an `errors` list and no text (claude_code.py:275-277) never runs.
  - The real "not installed" hint is never shown in a summary or answer stream (INSTALL.md:341).
- **Section summaries (assistant.py; covered by other files, not these four):** the 422 when the outline is unavailable (L213), the 422 when there are no headings and no PDF (L218), and the 409 when the PDF can't be read (L233-234) never run.

## 4. Possible application bugs
1. **The 300-page cap is never disclosed (confirmed; this is the expected failure in test_summary).** `pdf.extract` reads at most 300 pages (pdf.py:39, 167) but reports the whole PDF's page count (pdf.py:194). I measured a 302-page PDF: page count 302, text ends at page 300, 48,190 characters, which is under the 400,000-character limit. So nothing is marked truncated, and the model is told "Full text extracted from the PDF (302 pages)." This contradicts README:84-89 ("The LLM reads the whole paper … The prompt tells the model when that happens, and the Summary tab shows a note"). The note in SummaryPanel.tsx:46-48 never appears, answers to questions are misinformed the same way, and README's Known Limitations never mention the cap.
2. **An empty answer that hit the length limit is saved as just the cut-off note (confirmed; this is the expected failure in test_llm_service).** Both providers append the note before the empty-answer check (llm.py:320-324 and 375-379), so that check can never fire for a length-limited answer. The save then overwrites a previous good summary with only that note (assistant.py:144). This contradicts the code's own intent (it raises "The model returned an empty answer. Try again.") and README:90-92 (a failed request never stores partial text). Moving the check ahead of the note fixes it.
3. **Nothing else found.** No passing test asserts behavior contrary to the docs. The WEAK rows are unguarded regressions, not current bugs: the paper filters (assistant.py:170, 260) and the menu merge (llm.py:240) are correct today.

**Side effects of this review:**
- **CPU load:** from about 21:43 to 21:54 I ran 16 CPU-bound processes for the load test, while a `mutmut run` (PID 84358, in `scratchpad/wt-hw2-round2`) was running. Any mutant it marked as timed out in that window may be an artifact of my load.
- **Leftover temp folder:** the cleanup mutant left one folder, `/var/folders/bq/k59xwpfd7wj7lshsmd43f7zw0000gn/T/ra-claude-5e5w486g`, holding `system-prompt.md` and an empty `cwd/`. Because the review was read-only, I didn't delete it.
