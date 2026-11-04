"""Shared setup for the backend tests.

Every test runs against an isolated copy of the app:

- Settings come only from this file (support/isolation.py). The repository's .env is never read.
- The SQLite database and the PDFs live in a temporary folder, emptied before each test,
  created for each test session and removed after it.
- Module-level caches, locks, cooldowns, and background tasks start fresh in every
  test (support/app_state.py).
- No real LLM can be reached. CLAUDE_CODE_PATH points at a missing file and the
  Anthropic client at a closed local port with a fake key, so a call that a test
  forgot to fake fails fast instead of costing money. Tests replace the model with
  `fake_llm` (the model call itself) or `fake_claude` (a fake `claude` executable).
- No real network. The network layer of every httpx.AsyncClient is replaced by
  `upstream`, and DNS by `dns`; a request to a URL that no test registered fails the test.
- Time-based rules (arXiv spacing and cooldowns, the search cache) run on `clock`,
  which tests advance by hand, so they keep their real durations without slowing tests.
"""

import asyncio
import importlib.util
import ipaddress
import json
import os
import shutil
import socket
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import httpx
import pytest

# One scratch folder per process: app.db binds its engine to it at import, and a second
# pytest session in the same process (which imports this file again) must use it too.
_SCRATCH_VARIABLE = "RA_BACKEND_TESTS_SCRATCH"
SCRATCH = Path(os.environ.get(_SCRATCH_VARIABLE) or tempfile.mkdtemp(prefix="ra-backend-tests-"))
os.environ[_SCRATCH_VARIABLE] = str(SCRATCH)

from support.isolation import isolate_settings  # noqa: E402  (importing it reads no settings)

isolate_settings(
    data_dir=SCRATCH / "data",
    claude_code_path=SCRATCH / "claude-is-not-installed",
    serve_frontend="false",  # as `make dev` runs it
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

import app.main as main_module  # noqa: E402
from app import config  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ChatMessage, Paper  # noqa: E402
from app.routers import search as search_router  # noqa: E402
from app.services import arxiv, llm  # noqa: E402
from support import app_state  # noqa: E402
from support import fake_claude as fake_claude_cli  # noqa: E402
from support.clock import FakeClock  # noqa: E402
from support.fake_llm import FakeLLM  # noqa: E402
from support.upstream import FakeUpstream  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _scratch_data_folder() -> None:
    """The data folder of this session, with an empty database.

    Made per session (not at import), so pytest can run the suite twice in one process;
    pytest_sessionfinish removes it.
    """
    config.get_settings().data_dir.mkdir(parents=True, exist_ok=True)
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
    """An empty library and PDF folder, and fresh module-level state."""
    with engine.begin() as conn:
        conn.execute(delete(ChatMessage))
        conn.execute(delete(Paper))
    shutil.rmtree(config.get_settings().pdf_dir, ignore_errors=True)
    app_state.reset(monkeypatch)


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> FakeClock:
    """The time seen by the arXiv client and the search cache. Waiting on it is instant."""
    fake = FakeClock()
    monkeypatch.setattr(arxiv, "time", fake.as_time_module())
    monkeypatch.setattr(arxiv, "asyncio", fake.as_asyncio_module())
    monkeypatch.setattr(search_router, "time", fake.as_time_module())
    return fake


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The API, with its startup and shutdown (lifespan) run around the test."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def upstream(monkeypatch) -> Iterator[FakeUpstream]:
    """All external HTTP services (OpenAlex, arXiv, PDF hosts). Register answers on it.

    It replaces the network layer of httpx.AsyncClient, so it answers every request
    the app sends, from whichever module and client.
    """
    fake = FakeUpstream()

    async def handle_async_request(transport, request: httpx.Request) -> httpx.Response:
        await request.aread()
        return await fake.handle_async(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request)
    yield fake
    assert not fake.unexpected, "The app sent requests that no test registered:\n" + "\n".join(fake.unexpected)


@pytest.fixture(autouse=True)
def dns(monkeypatch) -> dict[str, str | list[str]]:
    """Fake DNS for the PDF download's address check: maps host names to IP addresses.

    A name may map to one address or a list of them. IP literals resolve to
    themselves; unknown names do not resolve.
    """
    hosts: dict[str, str | list[str]] = {}

    async def getaddrinfo(self, host, port, *, family=0, type=0, proto=0, flags=0):
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            if host not in hosts:
                raise socket.gaierror(socket.EAI_NONAME, f"{host} is not known to the test DNS") from None
            known = hosts[host]
            addresses = [ipaddress.ip_address(a) for a in ([known] if isinstance(known, str) else known)]
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(a), port, 0, 0)) if a.version == 6
            else (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (str(a), port))
            for a in addresses
        ]

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", getaddrinfo)
    return hosts


# --- The app in other modes ---------------------------------------------------------


@pytest.fixture
def app_module(settings, monkeypatch) -> Callable[..., ModuleType]:
    """Build a new copy of app/main.py's module with changed settings.

    app/main.py decides at import whether it serves the built UI, so other modes
    need a fresh copy. It shares the routers, database, and services with `app`.
    """
    def build(**changes) -> ModuleType:
        for name, value in changes.items():
            monkeypatch.setattr(settings, name, value)
        spec = importlib.util.spec_from_file_location("app._main_under_test", main_module.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return build


# --- Fake model (summaries, Q&A, section summaries, upload metadata) -------------


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    """Replace the model behind both providers, and the upload metadata extraction."""
    fake = FakeLLM()
    monkeypatch.setattr(llm, "_stream_claude_code", fake.provider)
    monkeypatch.setattr(llm, "_stream_api", fake.provider)
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

    @staticmethod
    def is_running(pid: int) -> bool:
        """Whether the process with this id (from an invocation's "pid") still exists."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:  # it exists, but belongs to someone else (the id was reused)
            return True
        return True


@pytest.fixture
def fake_claude(tmp_path, monkeypatch, settings) -> FakeClaude:
    path = fake_claude_cli.install(tmp_path / "bin")
    record = tmp_path / "claude-invocations.jsonl"
    for name in fake_claude_cli.ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    monkeypatch.setattr(settings, "claude_code_path", str(path))
    return FakeClaude(path, record, monkeypatch)
