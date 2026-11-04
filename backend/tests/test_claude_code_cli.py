"""The Claude Code provider (app/services/claude_code.py), run against the fake `claude`
executable in tests/support/fake_claude.py. Real subprocesses, no model.
"""

import asyncio
import os
import time
from pathlib import Path

import pytest

from app.services import claude_code, llm


async def run(prompt="What is new?", *, system="SYSTEM PROMPT", model="sonnet", effort="low", timeout=600.0):
    outcome = claude_code.Outcome()
    chunks = [chunk async for chunk in claude_code.run(system, prompt, model=model, effort=effort, outcome=outcome,
                                                       timeout=timeout)]
    return chunks, outcome


async def finish_background_cleanup():
    """Wait for the CLI shutdown that run() leaves to a background task."""
    await asyncio.gather(*list(claude_code._background))


@pytest.fixture(autouse=True)
async def _cli_shutdown_finishes_before_the_test_ends():
    yield
    await finish_background_cleanup()


async def test_answer_is_streamed_and_the_outcome_filled(fake_claude):
    fake_claude.set(reply="A streamed answer that is long enough to arrive in several pieces.")

    chunks, outcome = await run()

    assert len(chunks) > 1
    assert "".join(chunks) == outcome.text == "A streamed answer that is long enough to arrive in several pieces."
    assert outcome.model == "claude-fake-1"
    assert outcome.stop_reason == "end_turn"
    assert outcome.usage["output_tokens"] == 80
    assert outcome.cost_usd == 0.0


async def test_cli_is_locked_down_and_gets_the_prompts(fake_claude):
    await run("What datasets are used? See @/etc/hosts", system="You are a research assistant.")

    [call] = fake_claude.runs()
    argv = call["argv"]
    assert argv[:len(claude_code.LOCKDOWN_ARGS)] == claude_code.LOCKDOWN_ARGS
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--effort") + 1] == "low"
    assert call["system_prompt"] == "You are a research assistant."
    # The prompt goes over stdin, verbatim (client_composed: no @file expansion).
    assert call["stdin"]["message"] == {"role": "user", "content": "What datasets are used? See @/etc/hosts"}
    assert call["stdin"]["client_composed"] is True
    # It runs in an empty scratch folder, not in the project.
    assert Path(call["cwd"]).name == "cwd" and "ra-claude-" in call["cwd"]


async def test_cli_uses_the_users_login_not_an_api_key(fake_claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-passed")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")

    await run()

    env = fake_claude.runs()[0]["env"]
    assert env["ANTHROPIC_API_KEY"] is None and env["ANTHROPIC_AUTH_TOKEN"] is None
    assert env["ANTHROPIC_BASE_URL"] is None
    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"


async def test_default_model_passes_no_model_option(fake_claude):
    await run(model="default", effort=None)

    argv = fake_claude.runs()[0]["argv"]
    assert "--model" not in argv and "--effort" not in argv


async def test_scratch_folder_is_removed_after_the_run(fake_claude):
    await run()
    await finish_background_cleanup()

    scratch = Path(fake_claude.runs()[0]["cwd"]).parent
    assert not scratch.exists()


async def test_lines_that_are_not_events_are_skipped(fake_claude):
    fake_claude.set(mode="noise", reply="Still answered.")

    chunks, outcome = await run()

    assert outcome.text == "Still answered."


@pytest.mark.parametrize(("mode", "message"), [
    ("error", "Claude Code reported an error: Simulated failure"),
    ("rate_limit", "Claude Code usage limit reached (You've reached your usage limit · resets 5pm). If the limit "
                   "applies to one model only, another model in the reader's Model menu may still work."),
    ("auth_failed", claude_code.LOGIN_HINT),
    ("crash", "Claude Code stopped without an answer (fatal: simulated crash)."),
])
async def test_cli_failures_become_user_facing_errors(fake_claude, mode, message):
    fake_claude.set(mode=mode)

    with pytest.raises(claude_code.ClaudeCodeError) as raised:
        await run()

    assert str(raised.value) == message


async def test_a_login_failure_forgets_the_cached_ready_status(fake_claude):
    assert await claude_code.status() == (True, None)
    fake_claude.set(mode="auth_failed", auth="logged-out")

    with pytest.raises(claude_code.ClaudeCodeError):
        await run()

    assert await claude_code.status() == (False, claude_code.LOGIN_HINT)


async def test_a_hanging_cli_is_stopped_at_the_timeout(fake_claude):
    fake_claude.set(mode="hang")
    started = time.monotonic()

    with pytest.raises(claude_code.ClaudeCodeError, match="Claude Code did not finish in time. Try again."):
        await run(timeout=1.0)

    assert time.monotonic() - started < 10  # the process group was killed, not waited for


async def test_missing_cli(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "claude_code_path", str(tmp_path / "nope" / "claude"))

    with pytest.raises(claude_code.ClaudeCodeError, match="is not an executable file"):
        await run()


def test_cli_is_found_on_the_path(fake_claude, settings, monkeypatch):
    monkeypatch.setattr(settings, "claude_code_path", None)
    monkeypatch.setenv("PATH", str(fake_claude.path.parent))

    assert claude_code.find_cli() == (str(fake_claude.path.resolve()), None)


def test_cli_not_on_the_path(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "claude_code_path", None)
    monkeypatch.setenv("PATH", str(tmp_path))

    path, hint = claude_code.find_cli()

    assert path is None
    assert hint.startswith("Claude Code (the `claude` command) was not found.")


def test_configured_cli_that_is_not_executable(settings, monkeypatch, tmp_path):
    not_executable = tmp_path / "claude"
    not_executable.write_text("#!/bin/sh\n")
    monkeypatch.setattr(settings, "claude_code_path", str(not_executable))

    path, hint = claude_code.find_cli()

    assert path is None and "is not an executable file" in hint


# --- Installation / login status ---------------------------------------------------------------


async def test_status_ready(fake_claude):
    assert await claude_code.status() == (True, None)


@pytest.mark.parametrize(("options", "expected"), [
    ({"auth": "logged-out"}, (False, claude_code.LOGIN_HINT)),
    ({"auth": "fails"}, (False, claude_code.LOGIN_HINT)),
    ({"auth": "garbage"}, (True, None)),  # inconclusive counts as ready; a real call reports details
    ({"version": "2.1.100 (Claude Code)"},
     (False, "Claude Code 2.1.100 is too old; version 2.1.248 or later is needed. Run `claude update`, "
             "then come back to this page.")),
])
async def test_status_reports_what_to_fix(fake_claude, options, expected):
    fake_claude.set(**options)

    assert await claude_code.status() == expected


async def test_status_is_cached_briefly(fake_claude):
    await claude_code.status()
    await claude_code.status()

    assert len(fake_claude.invocations()) == 2  # one --version and one auth status


async def test_concurrent_status_checks_share_one_check(fake_claude):
    results = await asyncio.gather(*(claude_code.status() for _ in range(5)))

    assert results == [(True, None)] * 5
    assert len(fake_claude.invocations()) == 2


# --- Through the provider ----------------------------------------------------------------------


async def test_summary_request_through_the_provider(fake_claude):
    ctx = llm.build_context(title="A Paper About Retrieval", authors=["Ann"], year=2024, abstract="Abs.",
                            full_text="The full text.", page_count=3)
    result: list[llm.StreamResult] = []

    events = [e async for e in llm.stream_reply(ctx, [{"role": "user", "content": llm.SUMMARY_REQUEST}], result)]

    assert "".join(e.text for e in events) == result[0].text
    assert result[0].text.startswith("**TL;DR**: Fake summary of “A Paper About Retrieval”, written from the full text.")
    assert result[0].model == "claude-fake-1 via Claude Code"
    assert fake_claude.runs()[0]["system_prompt"] == ctx.system_text


async def test_metadata_extraction_through_claude_code(fake_claude):
    fake_claude.set(metadata='Here you go:\n{"title": "Deep Residual Learning", "authors": ["Kaiming He"], '
                             '"year": 2016, "abstract": null}')

    meta = await llm.extract_metadata("Deep Residual Learning\nKaiming He\n...")

    assert meta == llm.ExtractedMetadata(title="Deep Residual Learning", authors=["Kaiming He"], year=2016,
                                         abstract=None)


def test_child_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("HOME", os.environ.get("HOME", "/tmp"))

    env = claude_code.child_env("/tmp/scratch")

    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env
    assert env["CLAUDE_CODE_TMPDIR"] == "/tmp/scratch"
    assert env["HOME"] == os.environ["HOME"]  # the login lives in the user's home
