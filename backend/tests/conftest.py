"""Shared setup for the backend tests.

Every test runs against an isolated copy of the app:

- Settings come only from this file. The repository's .env is never read.
- The SQLite database and the PDFs live in a temporary folder, emptied before each test.
- No real LLM can be reached. CLAUDE_CODE_PATH points at a missing file and the
  Anthropic client at a closed local port with a fake key, so a call that a test
  forgot to fake fails fast instead of costing money. Tests replace the model with
  `fake_llm` (the model call itself) or `fake_claude` (a fake `claude` executable).
- No real network. The app's shared HTTP client is replaced by `upstream` and DNS by
  `dns`; a request to a URL that no test registered fails the test.
"""

import asyncio
import ipaddress
import json
import os
import shutil
import socket
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

SCRATCH = Path(tempfile.mkdtemp(prefix="ra-backend-tests-"))

from app import config  # noqa: E402  (importing it reads no settings yet)


def _isolate_settings() -> None:
    """Pin every setting before the app reads them (app.db reads them at import)."""
    for name in [*config.Settings.model_fields, "anthropic_auth_token", "anthropic_profile", "claudecode"]:
        os.environ.pop(name.upper(), None)
        os.environ.pop(name, None)
    os.environ.update({
        "DATA_DIR": str(SCRATCH / "data"),
        "SERVE_FRONTEND": "false",
        "LLM_PROVIDER": "claude-code",
        "CLAUDE_CODE_MODEL": "opus",
        "CLAUDE_CODE_PATH": str(SCRATCH / "claude-is-not-installed"),
        "ANTHROPIC_API_KEY": "test-key-not-real",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",  # nothing listens there
    })
    config.Settings.model_config["env_file"] = None
    config.get_settings.cache_clear()


_isolate_settings()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ChatMessage, Paper  # noqa: E402
from app.routers import assistant as assistant_router  # noqa: E402
from app.routers import search as search_router  # noqa: E402
from app.services import arxiv, claude_code, fulltext, llm, openalex  # noqa: E402
from app.services import http as http_service  # noqa: E402
from support import fake_claude as fake_claude_cli  # noqa: E402
from support.fake_llm import FakeLLM  # noqa: E402
from support.upstream import FakeUpstream  # noqa: E402

init_db()


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    shutil.rmtree(SCRATCH, ignore_errors=True)


@pytest.fixture
def settings() -> config.Settings:
    """The app's settings object. Change values with monkeypatch.setattr so they are restored."""
    return config.get_settings()


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    """An empty library and PDF folder, and no state left in module-level caches."""
    with engine.begin() as conn:
        conn.execute(delete(ChatMessage))
        conn.execute(delete(Paper))
    shutil.rmtree(config.get_settings().pdf_dir, ignore_errors=True)
    search_router._cache.clear()
    # arXiv asks for 3 s between calls; tests don't wait.
    monkeypatch.setattr(arxiv, "_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(arxiv, "_last_finished", 0.0)
    monkeypatch.setattr(arxiv, "_cooldown_until", 0.0)
    monkeypatch.setattr(arxiv, "_rate_lock", asyncio.Lock())
    monkeypatch.setattr(claude_code, "_status_cache", None)
    monkeypatch.setattr(claude_code, "_status_task", None)
    llm.get_client.cache_clear()  # an Anthropic client built from other settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The API, with its startup and shutdown (lifespan) run around the test."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def upstream(monkeypatch) -> Iterator[FakeUpstream]:
    """All external HTTP services (OpenAlex, arXiv, PDF hosts). Register answers on it."""
    fake = FakeUpstream()
    fake_client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handle), follow_redirects=True)
    for module in (http_service, arxiv, openalex, fulltext):
        monkeypatch.setattr(module, "get_client", lambda: fake_client)
    yield fake
    assert not fake.unexpected, "The app sent requests that no test registered:\n" + "\n".join(fake.unexpected)


@pytest.fixture(autouse=True)
def dns(monkeypatch) -> dict[str, str]:
    """Fake DNS for the PDF download's address check: maps host names to IP addresses.

    IP literals resolve to themselves; unknown names do not resolve.
    """
    hosts: dict[str, str] = {}

    async def getaddrinfo(self, host, port, *, family=0, type=0, proto=0, flags=0):
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host not in hosts:
                raise socket.gaierror(socket.EAI_NONAME, f"{host} is not known to the test DNS") from None
            address = ipaddress.ip_address(hosts[host])
        if address.version == 6:
            return [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(address), port, 0, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(address), port))]

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", getaddrinfo)
    return hosts


# --- Fake model (summaries, Q&A, section summaries, upload metadata) -------------


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    """Replace the model call for summaries, answers, section summaries, and upload metadata."""
    fake = FakeLLM()
    monkeypatch.setattr(llm, "stream_reply", fake.stream_reply)
    monkeypatch.setattr(assistant_router, "stream_reply", fake.stream_reply)
    monkeypatch.setattr(llm, "extract_metadata", fake.extract_metadata)
    return fake


# --- Fake Claude Code CLI ---------------------------------------------------------


@dataclass
class FakeClaude:
    """The fake `claude` executable (tests/support/fake_claude.py), set as CLAUDE_CODE_PATH."""

    path: Path
    record: Path
    monkeypatch: pytest.MonkeyPatch

    def set(self, **options: str) -> None:
        """Configure it, e.g. set(mode="error") sets FAKE_CLAUDE_MODE=error."""
        for key, value in options.items():
            self.monkeypatch.setenv(f"FAKE_CLAUDE_{key.upper()}", value)

    def invocations(self) -> list[dict]:
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines()]

    def runs(self) -> list[dict]:
        """Invocations that ran a prompt (not --version or auth status)."""
        return [entry for entry in self.invocations() if "stdin" in entry]


@pytest.fixture
def fake_claude(tmp_path, monkeypatch, settings) -> FakeClaude:
    path = fake_claude_cli.install(tmp_path / "bin")
    record = tmp_path / "claude-invocations.jsonl"
    for name in fake_claude_cli.ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    monkeypatch.setattr(settings, "claude_code_path", str(path))
    return FakeClaude(path, record, monkeypatch)
