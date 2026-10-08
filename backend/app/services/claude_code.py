"""Run the locally installed Claude Code CLI (`claude`) as a text model.

This is the default LLM provider: it uses the user's own Claude Code login, so
no API key is needed. The CLI is locked down: no tools, no MCP servers, no
CLAUDE.md / settings / hooks / skills, no saved session, prompts delivered
verbatim (no `@file` expansion), and our own system prompt instead of Claude
Code's coding-assistant prompt.

What cannot be switched off: Claude Code still adds a short context block with
the user's account email, the working directory, OS, shell, and the date. The
prompts tell the model never to repeat these, and the UI never loads remote
images, so model output cannot send them anywhere on its own.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

# --print, --input-format stream-json with `client_composed`, --system-prompt-file
# and --safe-mode all exist from this version on.
MIN_VERSION = (2, 1, 248)

INSTALL_HINT = (
    "Install Claude Code (https://claude.com/claude-code) and log in by running `claude` once, "
    "or set `LLM_PROVIDER=api` and `ANTHROPIC_API_KEY` in .env and restart the backend."
)
LOGIN_HINT = "Claude Code is installed but not logged in. Run `claude auth login` in a terminal, then come back to this page."

# Flags that turn Claude Code into a text model (see the module docstring).
LOCKDOWN_ARGS = [
    "--print",
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
    "--input-format", "stream-json",
    "--tools", "",
    "--disallowedTools", "mcp__*",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--no-session-persistence",
    "--disable-slash-commands",
    "--safe-mode",
    "--max-turns", "1",
]


class ClaudeCodeError(Exception):
    """A user-facing explanation of why the Claude Code call failed."""


# --- Locating the CLI and its environment -------------------------------------


def find_cli() -> tuple[str | None, str | None]:
    """(absolute path to `claude`, or None with a hint explaining what is wrong)."""
    configured = get_settings().claude_code_path
    if not configured:
        found = shutil.which("claude")
        return (str(Path(found).resolve()), None) if found else (
            None, "Claude Code (the `claude` command) was not found. " + INSTALL_HINT)
    # A bare command name is looked up on PATH; anything else is a file path.
    candidate = shutil.which(configured) if "/" not in configured else configured
    path = Path(candidate).expanduser() if candidate else None
    if path and path.is_file() and os.access(path, os.X_OK):
        return str(path.resolve()), None
    return None, (
        f"`CLAUDE_CODE_PATH` in .env is set to `{configured}`, which is not an executable file. "
        "Fix or remove it, then restart the backend."
    )


def child_env(tmpdir: str | None = None) -> dict[str, str]:
    """The user's environment, minus variables that would bypass their Claude Code login."""
    env = dict(os.environ)
    # In non-interactive mode Claude Code prefers an API key from the environment
    # over the user's login; this provider must use the login. ANTHROPIC_BASE_URL
    # is the api provider's setting and must not redirect the login elsewhere.
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE"):
        env.pop(name, None)
    env.update(
        CLAUDE_CODE_DISABLE_CLAUDE_MDS="1",
        CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
        ENABLE_CLAUDEAI_MCP_SERVERS="false",
    )
    if tmpdir:
        # Keep the CLI's scratch files inside our temp folder so they are removed with it.
        env["CLAUDE_CODE_TMPDIR"] = tmpdir
    return env


# --- Process helpers -----------------------------------------------------------


def _signal_group(proc: asyncio.subprocess.Process, sig: int) -> bool:
    """Signal the CLI's whole process group. False if no member is left."""
    try:
        os.killpg(proc.pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        # macOS reports EPERM, not ESRCH, when only an unreaped zombie remains.
        return False


async def _wait(proc: asyncio.subprocess.Process, seconds: float) -> None:
    with suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), seconds)


async def _exited(proc: asyncio.subprocess.Process, seconds: float) -> None:
    """Wait up to `seconds` for the CLI itself to exit.

    Polls returncode because proc.wait() also waits for the output pipes to
    close, which a leftover helper process can hold open.
    """
    deadline = time.monotonic() + seconds
    while proc.returncode is None and time.monotonic() < deadline:
        await asyncio.sleep(0.05)


async def _stop(proc: asyncio.subprocess.Process, grace: float) -> None:
    """Let the CLI exit on its own for `grace` seconds, then end its whole group.

    The CLI runs in its own process group (start_new_session=True), so helper
    processes are reached even after the CLI itself has exited. SIGTERM comes
    first so the CLI is not killed in the middle of writing its own files.
    """
    if grace > 0:
        await _exited(proc, grace)
    if _signal_group(proc, signal.SIGTERM):
        await _wait(proc, 2.0)
        if _signal_group(proc, signal.SIGKILL):
            await _wait(proc, 2.0)


# Background clean-up tasks; kept referenced so they are not garbage-collected.
_background: set[asyncio.Task[None]] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _finish(
    proc: asyncio.subprocess.Process, tmp: str, *tasks: asyncio.Task[None], grace: float
) -> None:
    """Stop the CLI (and its helpers), end the I/O tasks, and delete the temp folder."""
    try:
        tasks[0].cancel()  # stdin writer
        await _stop(proc, grace)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _version_tuple(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in match.groups()) if match else None


async def _capture(*args: str, timeout: float) -> tuple[int | None, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=child_env(), start_new_session=True,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    finally:
        await _stop(proc, grace=0)
    return proc.returncode, out


# --- Login status ----------------------------------------------------------------

_status_cache: tuple[float, bool, str | None] | None = None
_status_task: asyncio.Task[tuple[bool, str | None]] | None = None
_READY_TTL = 30.0
_NOT_READY_TTL = 3.0  # short, so a fresh `claude auth login` shows up quickly


async def status() -> tuple[bool, str | None]:
    """(ready, hint). Reads local state only; sends no prompt.

    Results are cached briefly, and concurrent callers share one check. A check
    that is merely inconclusive (slow, or odd output with exit code 0) counts as
    ready: the real request then reports its own, more specific error.
    """
    global _status_task
    now = time.monotonic()
    if _status_cache:
        checked_at, ready, hint = _status_cache
        if now - checked_at < (_READY_TTL if ready else _NOT_READY_TTL):
            return ready, hint
    if _status_task is None or _status_task.done():
        _status_task = asyncio.create_task(_check_status())
    return await asyncio.shield(_status_task)


async def _check_status() -> tuple[bool, str | None]:
    global _status_cache
    cli, hint = find_cli()
    result: tuple[bool, str | None] = (False, hint)
    if cli:
        try:
            (_, version_out), (code, auth_out) = await asyncio.gather(
                _capture(cli, "--version", timeout=8),
                _capture(cli, "auth", "status", "--json", timeout=8),
            )
            version = _version_tuple(version_out.decode(errors="replace"))
            if version and version < MIN_VERSION:
                needed = ".".join(map(str, MIN_VERSION))
                result = (False, f"Claude Code {'.'.join(map(str, version))} is too old; version {needed} or later "
                                 "is needed. Run `claude update`, then come back to this page.")
            elif code != 0:
                result = (False, LOGIN_HINT)
            else:
                try:
                    info = json.loads(auth_out or b"{}")
                except ValueError:
                    info = {}
                logged_out = isinstance(info, dict) and info.get("loggedIn") is False
                result = (False, LOGIN_HINT) if logged_out else (True, None)
        except (OSError, asyncio.TimeoutError) as exc:
            log.warning("Checking Claude Code failed (treated as ready): %r", exc)
            result = (True, None)
    _status_cache = (time.monotonic(), *result)
    return result


def forget_status() -> None:
    """Drop the cached status (e.g. after a run reports a login problem)."""
    global _status_cache
    _status_cache = None


# --- Running a prompt -------------------------------------------------------------


@dataclass
class Outcome:
    text: str = ""
    model: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _error_message(event: dict[str, Any], assistant_error: str | None) -> str:
    errors = event.get("errors")
    detail = (_as_str(event.get("result")) or "").strip() or (
        "; ".join(map(str, errors)) if isinstance(errors, list) else "")
    detail = detail.rstrip(".")
    if assistant_error == "authentication_failed":
        return LOGIN_HINT
    if assistant_error == "rate_limit":
        return (f"Claude Code usage limit reached ({detail or 'try again later'}). You can also set "
                "`CLAUDE_CODE_MODEL` to another model in .env and restart the backend.")
    return f"Claude Code reported an error: {detail or _as_str(event.get('subtype')) or 'unknown error'}"


async def run(
    system_prompt: str,
    prompt: str,
    *,
    model: str | None,
    effort: str | None,
    outcome: Outcome,
    timeout: float = 600.0,
) -> AsyncIterator[str]:
    """Stream the answer's text deltas; fill `outcome` when the run completes.

    Raises ClaudeCodeError, with a user-facing message, on any failure.
    """
    cli, hint = find_cli()
    if cli is None:
        raise ClaudeCodeError(hint)

    # The temp folder holds the prompt file, the CLI's empty working folder, and
    # its scratch files. Until the CLI starts, run() deletes it on failure;
    # after that, _finish always deletes it.
    tmp = tempfile.mkdtemp(prefix="ra-claude-")
    started = False
    try:
        # The CLI runs in an empty folder; the prompt file (the paper can be
        # ~400K characters, too long for an argument) sits next to it.
        workdir = Path(tmp, "cwd")
        workdir.mkdir()
        prompt_file = Path(tmp, "system-prompt.md")
        prompt_file.write_text(system_prompt, encoding="utf-8")
        args = [cli, *LOCKDOWN_ARGS, "--system-prompt-file", str(prompt_file)]
        if model and model != "default":
            args += ["--model", model]
        if effort:
            args += ["--effort", effort]

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env=child_env(tmp),
                limit=16 * 1024 * 1024,  # one stream-json line can carry the whole answer
                start_new_session=True,  # own process group, so _stop reaches helpers
            )
        except OSError as exc:
            raise ClaudeCodeError(f"Could not start Claude Code: {exc}") from exc
        started = True

        stderr_tail = ""

        async def drain_stderr() -> None:
            nonlocal stderr_tail
            assert proc.stderr is not None
            while chunk := await proc.stderr.read(65536):
                stderr_tail = (stderr_tail + chunk.decode(errors="replace"))[-4000:]

        # client_composed: deliver the prompt verbatim (no `@path` file expansion).
        payload = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None,
            "session_id": "",
            "client_composed": True,
        }, ensure_ascii=False).encode() + b"\n"

        async def write_stdin() -> None:
            assert proc.stdin is not None
            with suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(payload)
                await proc.stdin.drain()
                proc.stdin.close()

        stderr_task = asyncio.create_task(drain_stderr())
        stdin_task = asyncio.create_task(write_stdin())
        result_event: dict[str, Any] | None = None
        assistant_error: str | None = None
        try:
            assert proc.stdout is not None
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ClaudeCodeError("Claude Code did not finish in time. Try again.")
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError as exc:
                    raise ClaudeCodeError("Claude Code did not finish in time. Try again.") from exc
                except ValueError:
                    log.warning("Skipped an over-long line of Claude Code output")
                    continue
                if not raw:
                    break  # stdout closed without a result
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue  # not a JSON event line
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "system" and event.get("subtype") == "init":
                    outcome.model = _as_str(event.get("model")) or outcome.model
                elif kind == "stream_event":
                    inner = _as_dict(event.get("event"))
                    delta = _as_dict(inner.get("delta"))
                    text = _as_str(delta.get("text"))
                    if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta" and text:
                        yield text
                elif kind == "assistant":
                    assistant_error = _as_str(event.get("error")) or assistant_error
                    model = _as_str(_as_dict(event.get("message")).get("model"))
                    if model and not model.startswith("<"):
                        outcome.model = model
                elif kind == "result":
                    result_event = event
                    break  # the answer is complete; don't wait for stdout to close
        finally:
            if result_event is not None:
                # The answer is complete: let the CLI exit by itself in the
                # background instead of making the user wait for it.
                _spawn(_finish(proc, tmp, stdin_task, stderr_task, grace=5.0))
            else:
                # Error, timeout, or client disconnect: end it right away.
                await _finish(proc, tmp, stdin_task, stderr_task, grace=0.0)
    except BaseException:
        if not started:
            shutil.rmtree(tmp, ignore_errors=True)
        raise

    if result_event is None:
        lines = [line for line in stderr_tail.splitlines() if line.strip()]
        detail = lines[-1].strip() if lines else f"exit code {proc.returncode}"
        raise ClaudeCodeError(f"Claude Code stopped without an answer ({detail}).")
    if result_event.get("is_error") or assistant_error:
        if assistant_error == "authentication_failed":
            forget_status()
        raise ClaudeCodeError(_error_message(result_event, assistant_error))

    outcome.text = (_as_str(result_event.get("result")) or "").strip()
    outcome.stop_reason = _as_str(result_event.get("stop_reason"))
    outcome.usage = _as_dict(result_event.get("usage"))
    cost = result_event.get("total_cost_usd")
    outcome.cost_usd = cost if isinstance(cost, (int, float)) else None
