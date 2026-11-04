"""A fake `claude` (Claude Code CLI) for tests. It speaks the CLI's stream-json protocol
and never contacts a model, so tests of the default LLM provider cost nothing.

The app runs Claude Code as
    claude --print --output-format stream-json ... --system-prompt-file FILE [--model M] [--effort E]
with the prompt as one JSON message on stdin, and checks the installation with
`claude --version` and `claude auth status --json`.

Behavior is set through environment variables, which the app passes on to the CLI:
  FAKE_CLAUDE_MODE      ok (default) | error | rate_limit | auth_failed | refusal | max_tokens |
                        empty | crash | hang | noise
  FAKE_CLAUDE_REPLY     fixed answer text instead of the generated one
  FAKE_CLAUDE_METADATA  reply to metadata-extraction prompts (default: prose without JSON,
                        so the app keeps its PDF heuristics)
  FAKE_CLAUDE_MODEL     model name to report (default claude-fake-1)
  FAKE_CLAUDE_VERSION   output of --version (default "2.1.300 (Claude Code)")
  FAKE_CLAUDE_AUTH      logged-in (default) | logged-out | fails | garbage
  FAKE_CLAUDE_RECORD    file that gets one JSON line per invocation (argv, prompts, environment)
A prompt containing "[[fake:<mode>]]" uses that mode for one call; end-to-end tests use
this, because their server's environment is fixed.

Use install() to get an executable path for CLAUDE_CODE_PATH.
"""

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

ENV_VARS = [
    "FAKE_CLAUDE_MODE", "FAKE_CLAUDE_REPLY", "FAKE_CLAUDE_METADATA", "FAKE_CLAUDE_MODEL",
    "FAKE_CLAUDE_VERSION", "FAKE_CLAUDE_AUTH", "FAKE_CLAUDE_RECORD",
]
# Variables whose presence in the CLI's environment the tests check.
WATCHED_ENV = [
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE",
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
    "ENABLE_CLAUDEAI_MCP_SERVERS", "CLAUDE_CODE_TMPDIR",
]
DEFAULT_MODEL = "claude-fake-1"


def install(directory: Path) -> Path:
    """Write an executable `claude` wrapper into `directory` that runs this script."""
    directory.mkdir(parents=True, exist_ok=True)
    wrapper = directory / "claude"
    # A shell wrapper (not a shebang line) works even when the paths contain spaces.
    wrapper.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -I {shlex.quote(str(Path(__file__).resolve()))} "$@"\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def _record(entry: dict) -> None:
    path = os.environ.get("FAKE_CLAUDE_RECORD")
    if path:
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _emit(event: object) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _option(argv: list[str], flag: str) -> str | None:
    if flag in argv and argv.index(flag) + 1 < len(argv):
        return argv[argv.index(flag) + 1]
    return None


def _tag(text: str, name: str) -> str | None:
    match = re.search(rf"<{name}>\n?(.*?)\n?</{name}>", text, re.DOTALL)
    return match.group(1) if match else None


def _reply(prompt: str, system: str) -> str:
    if os.environ.get("FAKE_CLAUDE_REPLY"):
        return os.environ["FAKE_CLAUDE_REPLY"]
    if "<pages>" in prompt:  # metadata extraction from an uploaded PDF
        return os.environ.get("FAKE_CLAUDE_METADATA", "Sorry, I could not read the metadata.")
    title = _tag(system, "title") or "this paper"
    basis = "the abstract only" if "Only the abstract is available" in system else "the full text"
    if block := re.search(r"<headings>\n(.*?)\n</headings>", prompt, re.DOTALL):  # section summaries
        headings = json.loads(block.group(1))
        return json.dumps({"summaries": [
            {"n": h["n"], "summary": f"Fake summary of the section {h['heading']}."} for h in headings
        ]})
    if "Identify this paper's main sections" in prompt:
        return json.dumps({"sections": [
            {"title": "Method", "summary": "Fake summary of the method."},
            {"title": "Results", "summary": "Fake summary of the results."},
        ]})
    if "Summarize this paper" in prompt:
        return (
            f"**TL;DR**: Fake summary of “{title}”, written from {basis}.\n\n"
            "**Problem**: Fake problem statement.\n\n"
            "**Key results**: Fake results."
        )
    question = prompt.rsplit("The user's new question (answer this one):\n", 1)[-1].strip()
    earlier = prompt.count('role="user"')
    return (
        f"Fake answer to “{question}” about “{title}”, from {basis}. "
        f"Earlier questions in this conversation: {earlier}."
    )


def _chunks(text: str, size: int = 20) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def _run(argv: list[str]) -> int:
    system_file = _option(argv, "--system-prompt-file")
    system = Path(system_file).read_text(encoding="utf-8") if system_file else ""
    line = sys.stdin.readline()
    try:
        payload = json.loads(line)
    except ValueError:
        payload = None
    message = payload.get("message") if isinstance(payload, dict) else None
    prompt = message.get("content", "") if isinstance(message, dict) else ""
    _record({
        "argv": argv,
        "system_prompt": system,
        "stdin": payload,
        "cwd": os.getcwd(),
        "env": {name: os.environ.get(name) for name in WATCHED_ENV},
    })

    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if trigger := re.search(r"\[\[fake:(\w+)\]\]", prompt):
        mode = trigger.group(1)
    model = os.environ.get("FAKE_CLAUDE_MODEL", DEFAULT_MODEL)

    if mode == "crash":
        sys.stderr.write("fatal: simulated crash\n")
        return 3
    if mode == "hang":
        time.sleep(60)
        return 0
    if mode == "noise":  # lines the app must skip
        print("this line is not JSON", flush=True)
        print("[1, 2, 3]", flush=True)
        _emit({"type": "stream_event", "event": "not an object"})

    _emit({"type": "system", "subtype": "init", "model": model, "tools": []})
    if mode in ("rate_limit", "auth_failed"):
        error = "rate_limit" if mode == "rate_limit" else "authentication_failed"
        detail = "You've reached your usage limit · resets 5pm." if mode == "rate_limit" else "Invalid API key"
        _emit({"type": "assistant", "error": error, "message": {"model": "<synthetic>", "content": []}})
        _emit({"type": "result", "subtype": "success", "is_error": True, "result": detail})
        return 1
    if mode == "error":
        _emit({"type": "result", "subtype": "error_during_execution", "is_error": True,
               "result": "Simulated failure."})
        return 1

    text = "" if mode == "empty" else _reply(prompt, system)
    for chunk in _chunks(text):
        _emit({"type": "stream_event", "event": {
            "type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": chunk}}})
        time.sleep(0.002)
    _emit({"type": "assistant", "message": {"model": model, "role": "assistant",
                                            "content": [{"type": "text", "text": text}]}})
    _emit({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "stop_reason": {"refusal": "refusal", "max_tokens": "max_tokens"}.get(mode, "end_turn"),
        "usage": {"input_tokens": 1200, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 1100, "output_tokens": 80},
        "total_cost_usd": 0.0,
    })
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--version"]:
        _record({"argv": argv})
        print(os.environ.get("FAKE_CLAUDE_VERSION", "2.1.300 (Claude Code)"))
        return 0
    if argv[:2] == ["auth", "status"]:
        _record({"argv": argv})
        auth = os.environ.get("FAKE_CLAUDE_AUTH", "logged-in")
        if auth == "fails":
            print("error: unknown command 'auth'", file=sys.stderr)
            return 1
        if auth == "garbage":
            print("Logged in, probably")
            return 0
        print(json.dumps({"loggedIn": auth == "logged-in", "authMethod": "claude.ai"}))
        return 0
    return _run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
