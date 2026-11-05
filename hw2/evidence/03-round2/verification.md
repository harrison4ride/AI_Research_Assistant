# Experiments that check the code review's findings and one equivalence claim (verbatim)

The `/code-review` of round 2's changes (`code-review-raw.md`) made claims that need an
experiment to confirm. I gave them, plus one of the round 2 agent's "equivalent mutant"
claims from my random sample (V7), to a fresh-context Claude Code subagent. It worked in
its own scratch worktree at tag `hw2-round2`, undid every change, and left the worktree
clean. 73 tool calls, about 222k tokens, 21 minutes.

| Item | Claim checked | Verdict |
|------|---------------|---------|
| V1 | code review #2 | CONFIRMED |
| V2 | code review #3 | CONFIRMED |
| V3 | code review #4 | CONFIRMED |
| V4 | code review #6 | CONFIRMED |
| V5 | code review #7 | CONFIRMED |
| V6 | code review #8 | CONFIRMED with a correction |
| V7 | agent's claim that `_page_lines` mutant 21 is equivalent | REFUTED (edge case) |
| V8 | code review #9 | CONFIRMED |

Code review #1 (the stuttering arXiv message) I confirmed by reading `arxiv.py:94` and
`arxiv.py:161`; the test passing at `hw2-round2` shows the app produces that text. #5 is a
disputed owner decision, and #10 (duplicated padding logic) needs no experiment.

---

## Verification report: HW2 round-2 test-suite claims V1 to V8 (worktree `.../scratchpad/wt-verify-r2`, tag hw2-round2)

Six claims are confirmed and one is confirmed with a correction (V6). V7 is refuted, but only through a constructed edge case. Every experiment was undone, the temporary test file was deleted, and the pytest caches my runs created were removed. No servers, network, real LLM or Playwright were used. The scaled timeout check in V3 used an in-process `socket.socketpair()`, not a port. I also ran the whole backend suite once, for V6.

### V1: `test_an_empty_answer_cut_off_at_the_length_limit_is_an_error`
- **Change** (`llm.py`, `_stream_claude_code`, right after `settings = get_settings()`):
  ```
  +    raise LlmError("Claude Code not found")
  ```
- **Command:** `cd backend && uv run pytest "tests/test_llm_service.py::test_an_empty_answer_cut_off_at_the_length_limit_is_an_error" -q -rxX`
- **Result:** `XFAIL ... 1 xfailed`. Rerunning with `--runxfail` shows the failure is wrapped as `StillBroken`, with `{'claude-code': 'Claude Code not found'} != {'claude-code': 'The model returned an empty answer. Try again.'}`.
- **Stronger variant:** I also fixed the real bug in both providers (empty check moved before the cut-off note) and kept the unrelated raise.
  - It is still `XFAIL`, and the only differing item is `{'claude-code': 'Claude Code not found'}`.
  - Control (the fix alone): `[XPASS(strict)] ... 1 failed`.
  - So an unrelated error alone counts as the known bug and hides a complete fix.
- **Cause:** test lines 384-385 catch every `LlmError` and store `str(error)`. The only check is the comparison at lines 387-388.
- **Verdict: CONFIRMED.**

### V2: `test_a_malformed_pdf_link_is_recorded_and_the_abstract_is_used`
- **Change 1, port only** (`_check_public`):
  ```
  -    port = parts.port or (443 if parts.scheme == "https" else 80)
  +    try:
  +        port = parts.port or (443 if parts.scheme == "https" else 80)
  +    except ValueError as exc:
  +        raise httpx.ConnectError(f"Invalid port in {url}") from exc
  ```
  - Result: `XFAIL`.
  - `--runxfail` shows the failure moved to `http://[::1/bert.pdf`: `assert 500 == 200` at test line 339. The port URL, first in the loop, now passes all three checks.
- **Change 2:** also wrap `urlsplit(url)` the same way.
  - Result: `[XPASS(strict)] ... 1 failed`. Both failures are recorded as "The PDF could not be downloaded."
- **Reverse check** (fix only the IPv6 case): `XFAIL`, now failing on the `:99999` URL.
- **Side note:** the `known_bug` reason says `urlsplit()` raises in both cases. For `:99999`, `urlsplit` succeeds and `parts.port` raises "Port out of range 0-65535" (fulltext.py line 67). Only the IPv6 link raises inside `urlsplit` ("Invalid IPv6 URL", line 64).
- **Verdict: CONFIRMED.** Fixing either link alone is invisible.

### V3: `test_a_pdf_download_cannot_hang_forever`
- **Change:**
  ```
  -  "GET", pinned, timeout=60.0, follow_redirects=False,
  +  "GET", pinned, follow_redirects=False,
  ```
  I also added a temporary print of `request.extensions["timeout"]` in the test.
- **Result:**
  - Before: `{'connect': 60.0, 'read': 60.0, 'write': 60.0, 'pool': 60.0}`.
  - After: `{'connect': 20.0, 'read': 20.0, 'write': 20.0, 'pool': 20.0}`, from `http.py` line 23 (`timeout=20.0`). The test reports `1 passed`, and all of `test_fulltext.py` reports `43 passed, 2 xfailed`.
  - Contrast: `timeout=None` makes the values `None`, giving `1 failed`. That explicit disabling is the only change this assertion catches.
- **Timeouts are per read, not per download:**
  - In httpcore 1.0.9, `_async/http11.py` lines 196-219 loop over the body, and each `self._network_stream.read(..., timeout=read)` call is separate.
  - In `_backends/anyio.py` lines 25-35, each read is wrapped in `with anyio.fail_after(timeout)`, so the timer restarts on every read.
  - Scaled check through httpx's real HTTP/1.1 stack over an in-process `socketpair` (same 19:60 ratio):
    - one byte every 0.19 s with `timeout=0.6`: `OK: 12 bytes in 2.35s`
    - control with a 1.0 s gap: `ReadTimeout after 0.60s`
- **A host sending one byte every 19 s:**
  - `_download` (fulltext.py lines 134-158) keeps reading in the loop at lines 151-157 until end of file or `size > limit` (lines 154-155).
  - The limit is `max_pdf_mb` (line 135), 50 MB by default (config.py line 33). There is no overall deadline anywhere around `_download` (called at line 188).
  - So neither the 60 s nor the 20 s read timeout ever fires. The download runs until the host stops or 52,428,800 bytes × 19 s, about 31.6 years. Up to 6 hops are allowed.
  - The whole time, `paper_lock` (line 174) is held. Other requests for that paper (papers.py lines 301 and 365, assistant.py line 66) wait behind it.
- **Docs:** README.md lines 106-109 and INSTALL.md lines 215-218 promise only public addresses and at most 5 redirects. INSTALL.md line 182 gives the 50 MB size limit. Neither file promises a time limit for downloads. Their only time limits concern arXiv, the search cache, and the Claude Code status recheck.
- **Verdict: CONFIRMED** (all three parts).

### V4: `fetchMock.ts` late-request check (`mock.ended` / `takeLateRequests`)
- **How Vitest 5.1.0 orders this:** `clearModuleMocks`, which runs `restoreAllMocks` and then `unstubAllGlobals`, is called from `onBeforeTryTask`. That is the start of the next test (`node_modules/vitest/dist/chunks/index.CZzC1gGg.js` lines 8376-8378 and 8460-8466).
- **Temporary file** `frontend/src/zzLateRequest.test.ts` (now deleted). Command: `cd frontend && npx vitest run src/zzLateRequest.test.ts`.
- **Run 1.** In each pair, test A registers a mock, calls `getHealth()`, then schedules `listPapers()` (GET /api/papers, unmocked).
  - **A1 → B1** (B1 mocks first, then waits 50 ms): the request reached B1's mock.
    - `B1 calls: [ 'GET /api/papers' ]`
    - `FAIL ... B1 ... Error: The app sent a request that the test did not mock: GET /api/papers` (setup.ts line 32)
    - A1 passed and is not mentioned.
  - **A2 → B2** (B2 waits 50 ms before mocking): the request went to the real fetch and was rejected with "Network error: cannot reach the backend." Nothing reported it, and B2 passed.
  - **A3 → B3** (a 0 ms timer): it also reached B3's mock, so B3 failed the same way.
  - Totals: `Tests 2 failed | 4 passed`. The "sent after the test … had ended" message never appeared.
- **Run 2,** to see whether the check ever fires:
  - **C1:** a request sent one microtask after unmount (during setup.ts's `cleanup()`) is caught correctly: `FAIL src/zzLateRequest.test.ts ... Error: The app sent a request that no test mocked: GET /api/papers (sent after the test “C1 …” had ended)` (setup.ts line 40).
  - **E1** (last test in the file, 5 ms timer): it logged `global fetch is the mock of E1` after `afterAll` had already run, so it was recorded but never reported.
- **Verdict: CONFIRMED.** The check works only for requests sent in microtasks between A's afterEach and the start of the next test.

### V5: `test_a_link_that_is_not_http_is_refused_with_a_true_reason`
- **Change:**
  - add `class UnsupportedLink(UnsafeUrl)`
  - `_check_public` raises it when the scheme is not http or https
  - `except UnsupportedLink: error = "Only web links can be downloaded."`, placed before `except UnsafeUrl`
- **Result:** `XFAIL`, with `StillBroken: assert 'http' in 'only web links can be downloaded.'` (test line 317). The rest of `test_fulltext.py` reports `43 passed, 2 xfailed`, so the fix breaks nothing else.
- **With "Only http and https links can be downloaded.":** `[XPASS(strict)] ... 1 failed`.
- **Verdict: CONFIRMED.**

### V6: `test_a_result_that_another_request_stores_at_the_same_moment_is_not_stored_twice`
- **The test:** line 178 has the competing request store `in_library=endpoint == "/api/papers"`, the same value the endpoint under test would set. A save racing an open is never set up.
  - In papers.py, the promotion is at lines 122-124 inside `reuse()`. The race path, `except IntegrityError` → `return reuse(existing)`, is at lines 137-143.
- **M2, minimal and race path only:**
  ```
  def reuse(existing, promote: bool = True)
  ...if not existing.in_library and promote:
  ...return reuse(existing, promote=False)
  ```
  - Target test: `2 passed`. `test_library.py`: `96 passed`. Whole backend suite: `553 passed, 5 xfailed`. **Nothing fails.**
  - To show it is a real bug: I temporarily changed the competitor to an open (`in_library=False`). With M2: `FAILED ...[save]`, `assert False is ('/api/papers' == '/api/papers')`. With the original code: `2 passed`.
- **M1** (promotion removed from `reuse()` entirely): the target test still reports `2 passed`, but other tests catch it with `2 failed, 94 passed`:
  - `test_saving_an_opened_paper_from_search_keeps_its_id_and_conversation`
  - `test_saving_an_opened_paper_keeps_its_summary_section_summaries_and_conversation[search page]`
- **Correction to "cannot fail":** M3, where the race path wrongly promotes on open, gives `FAILED ...[open]`. The assertion catches a wrong write, just not a missing promotion.
- **Verdict: CONFIRMED** on the substance, with that correction.

### V7: `continue` → `break` in `pdf._page_lines`
- **Setup:** PyMuPDF and MuPDF 1.28.2, PDFs built in memory.
- **Probe 1, rotation at 90° and 30°:** 12 layouts (rotated text between lines, inline mid-line, a stamp drawn first, one or separate text objects, `Td`/`T*` lines, `insert_text(rotate=90)`, `TextWriter` morph). All gave `mixed-dir blocks=0`.
- **Probe 2, tolerance:** a line tilted by δ under a horizontal line stays in the same block for δ ≤ 2.5° and gets its own block from 2.6° on. The app treats a line as rotated only above about 8.1° (`abs(dir[0]-1) > 0.01`). So rotated text placed directly after horizontal text always gets its own block, and the claim holds for that case.
- **Probe 3, gradual drift:** lines at 0, 2, 4, 6, 8, 10, 8, 6, 4, 2, 0° (12 pt apart), followed by bold "2 Method", form **one block**. Its 10° line (`dir0=0.9848`, rotated for the app) comes before six lines the app treats as horizontal, including the heading.
- **Observable difference:** a PDF with the headings "1 Introduction", this fan plus "2 Method", and "3 Results". Both runs used identical bytes (sha256 `aa6d4396409f9a4e…`). The change was line 291:
  ```
  -                continue
  +                break
  ```

  | | original (`continue`) | mutant (`break`) |
  |---|---|---|
  | `extract_outline` | `1 Introduction`, `2 Method`, `3 Results` | `1 Introduction`, `3 Results` |
  | `locate_headings` | `[(1, 0.052…), (1, 0.345…), (1, 0.481…)]` | `[(1, 0.052…), None, (1, 0.481…)]` |

- **Verdict: REFUTED.** The mutant is not equivalent. In practice the case is narrow: it needs a direction that drifts in steps of 2.5° or less within one block, and no direct 30° or 90° placement produced it.

### V8: `test_the_text_is_every_page_in_order_separated_by_blank_lines`
- **The test**, lines 44-47:
  ```
  pymupdf.open(stream=data, filetype="pdf")
  [page.get_text().strip() for page in doc]
  assert pdf.extract(data).text == "\n\n".join(pages)
  ```
- **The app**, pdf.py:
  - line 159: `pymupdf.open(stream=data, filetype="pdf")`
  - line 167: `doc[i].get_text("text")` for up to 300 pages
  - line 168: `"\n\n".join(p.strip() for p in pages).strip()`
- `get_text()` defaults to `option='text'` (`pymupdf.utils.get_text` signature), so the calls are identical.
- The only differences are the 300-page cap and the outer `.strip()`, and the 2-page sample exercises neither.
- So the test pins only the wiring (separator, order, all pages). It cannot catch wrong text, because both sides share PyMuPDF's output.
- An independent oracle already exists in `tests/support/pdfs.py` (`BODY_MARKER`, `SAMPLE_SECTIONS`, `SAMPLE_TEXT_END`). It is used, for example, by `test_extract_the_sample_paper` at line 39.
- **Verdict: CONFIRMED.**

### Summary

| item | verdict | one-line reason |
|---|---|---|
| V1 | CONFIRMED | An unrelated "Claude Code not found" `LlmError` still gives XFAIL, even with the real bug fully fixed. |
| V2 | CONFIRMED | Fixing only one malformed link stays XFAIL; fixing both gives XPASS(strict). |
| V3 | CONFIRMED | Without `timeout=60.0` the test passes on the client's 20 s default; timeouts are per read; nothing limits a trickling host; the docs promise no time limit. |
| V4 | CONFIRMED | Late requests on a timer (even 0 ms) are blamed on the next test or hit the real fetch unreported; the check fires only in a microtask window, and late requests after the last test are never reported. |
| V5 | CONFIRMED | The correct "Only web links…" fix stays XFAIL; only wording that contains "http" gives XPASS(strict). |
| V6 | CONFIRMED (with correction) | Dropping the promotion on the save-races-open path passes every backend test; the assertion only catches a wrong write (promoting on open). |
| V7 | REFUTED (edge case) | MuPDF splits blocks only when direction changes by more than about 2.56°; a gradual fan puts a 10° line before horizontal ones, and `break` then drops "2 Method". |
| V8 | CONFIRMED | The expected value repeats pdf.py lines 159, 167 and 168 with the same PyMuPDF calls. |

### Final `git status --porcelain`
```
(no output)
```
