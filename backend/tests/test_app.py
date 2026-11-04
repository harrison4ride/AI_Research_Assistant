"""App-level behavior: health check, configuration for the UI, settings, and how the
app serves the UI in development and production mode (README "Run", INSTALL.md)."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app import config
from app.main import app
from app.config import BACKEND_DIR, REPO_ROOT

DEV_PAGE = "In development mode the app runs at"
NO_BUILD_PAGE = "No frontend build was found in"


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- Settings ------------------------------------------------------------------------


def test_settings_defaults_are_the_documented_ones(monkeypatch):
    # INSTALL.md § Environment Variables; none of these needs to be set.
    for name in config.Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)

    defaults = config.Settings()

    assert (defaults.llm_provider, defaults.claude_code_model, defaults.llm_model) == (
        "claude-code", "opus", "claude-opus-5")
    assert defaults.claude_code_path is None and defaults.anthropic_api_key is None
    assert defaults.llm_effort == "medium"
    assert defaults.llm_max_tokens == 32000
    assert defaults.llm_max_paper_chars == 400_000
    assert defaults.llm_history_messages == 20
    assert defaults.llm_extract_metadata is True
    assert defaults.max_pdf_mb == 50
    assert defaults.cached_paper_days == 7
    assert defaults.data_dir == BACKEND_DIR / "data"
    assert defaults.serve_frontend is True
    assert defaults.frontend_dist == REPO_ROOT / "frontend" / "dist"


@pytest.mark.parametrize(("name", "value"), [
    ("LLM_EFFORT", "fast"), ("LLM_MAX_TOKENS", "0"), ("LLM_PROVIDER", "openai"),
    ("CACHED_PAPER_DAYS", "0"), ("MAX_PDF_MB", "0"),
])
def test_an_invalid_setting_stops_the_app_naming_the_setting(monkeypatch, name, value):
    # INSTALL.md: "An invalid value ... stops the backend at startup with a message naming the setting."
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name.lower()):
        config.Settings()


def test_relative_paths_are_resolved_against_the_backend_folder(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "my-data")
    monkeypatch.setenv("FRONTEND_DIST", "../frontend/dist")

    settings = config.Settings()

    assert settings.data_dir == BACKEND_DIR / "my-data"
    assert settings.frontend_dist == REPO_ROOT / "frontend" / "dist"


# --- Configuration for the UI ------------------------------------------------------------


def test_config_for_the_default_claude_code_provider(client, settings, monkeypatch):
    for name in ("LLM_PROVIDER", "CLAUDE_CODE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    defaults = config.Settings()
    monkeypatch.setattr(settings, "llm_provider", defaults.llm_provider)
    monkeypatch.setattr(settings, "claude_code_model", defaults.claude_code_model)

    body = client.get("/api/config").json()

    assert body["llm_provider"] == "claude-code"
    assert body["llm_model"] == "Claude Code (opus)"
    assert body["llm_default_model"] == "opus"
    # README: Opus, Sonnet, Haiku, Fable, and "Claude Code default".
    assert body["llm_models"] == [
        {"id": "opus", "label": "Opus"}, {"id": "sonnet", "label": "Sonnet"}, {"id": "haiku", "label": "Haiku"},
        {"id": "fable", "label": "Fable"}, {"id": "default", "label": "Claude Code default"}]
    assert body["cached_paper_days"] == 7


def test_config_reports_claude_code_missing_with_a_fix(client):
    # CLAUDE_CODE_PATH points at a file that does not exist (see conftest.py).
    body = client.get("/api/config").json()
    assert body["llm_ready"] is False
    assert "CLAUDE_CODE_PATH" in body["llm_hint"]
    assert "not an executable file" in body["llm_hint"]


def test_config_ready_when_claude_code_is_installed_and_logged_in(client, fake_claude):
    body = client.get("/api/config").json()
    assert body["llm_ready"] is True
    assert body["llm_hint"] is None
    # The status check only reads local state: it ran --version and auth status, no prompt.
    assert sorted(entry["argv"][0] for entry in fake_claude.invocations()) == ["--version", "auth"]
    assert fake_claude.runs() == []


def test_config_reports_logged_out_claude_code(client, fake_claude):
    fake_claude.set(auth="logged-out")
    body = client.get("/api/config").json()
    assert body["llm_ready"] is False
    # INSTALL.md troubleshooting: the fix is `claude auth login`.
    assert "`claude auth login`" in body["llm_hint"]


def test_config_for_the_api_provider(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "api")
    body = client.get("/api/config").json()
    assert body["llm_provider"] == "api"
    assert body["llm_model"] == "claude-opus-5"
    assert body["llm_default_model"] == "claude-opus-5"
    # README: Claude Opus 5, Claude Sonnet 5, Claude Haiku 4.5, and Claude Fable 5.1.
    assert body["llm_models"] == [
        {"id": "claude-opus-5", "label": "Claude Opus 5"}, {"id": "claude-sonnet-5", "label": "Claude Sonnet 5"},
        {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5"}, {"id": "claude-fable-5-1", "label": "Claude Fable 5.1"}]
    assert body["llm_ready"] is True  # a key is configured (a fake one)


def test_config_for_the_api_provider_without_any_key(client, settings, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "llm_provider", "api")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # no `ant` login profile either
    body = client.get("/api/config").json()
    assert body["llm_ready"] is False
    assert "ANTHROPIC_API_KEY" in body["llm_hint"]


def test_cached_paper_days_comes_from_settings(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "cached_paper_days", 3)
    assert client.get("/api/config").json()["cached_paper_days"] == 3


# --- Development mode: this port serves only the API --------------------------------------


def test_root_explains_where_the_ui_is_in_development_mode(client):
    # The tests run with SERVE_FRONTEND=false, as `make dev` does.
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "This port serves only the API" in response.text
    assert DEV_PAGE in response.text and "http://localhost:5173" in response.text
    assert NO_BUILD_PAGE not in response.text


@pytest.mark.parametrize("files", [[], ["index.html"]], ids=["empty folder", "interrupted build"])
def test_root_explains_a_missing_frontend_build(app_module, tmp_path, files):
    # INSTALL.md: "The page says which case applies."
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in files:
        (dist / name).write_text("<!doctype html>")
    module = app_module(serve_frontend=True, frontend_dist=dist)

    with TestClient(module.app) as started:
        response = started.get("/")

    assert response.status_code == 200
    assert f"{NO_BUILD_PAGE} <code>{dist}</code>" in response.text
    assert "make build" in response.text and "FRONTEND_DIST" in response.text
    assert DEV_PAGE not in response.text


@pytest.mark.parametrize("path", ["/api/does-not-exist", "/api/papers/1/no-such-thing"])
def test_unknown_api_path_is_a_json_404_in_development_mode(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_wrong_method_is_a_json_405_in_development_mode(client):
    response = client.put("/api/health")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


# --- Production mode: one process serves the API and the built UI ----------------------------


@pytest.fixture
def production(app_module, tmp_path) -> TestClient:
    """The app as `make start` runs it, serving a minimal build from a temporary folder."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Built UI</title><script src='/assets/app-1a2b.js'></script>")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (dist / "assets" / "app-1a2b.js").write_text("console.log('built')")
    module = app_module(serve_frontend=True, frontend_dist=dist)
    with TestClient(module.app) as started:
        yield started


def test_production_mode_serves_the_built_ui(production):
    page = production.get("/")
    assert page.status_code == 200
    assert "<title>Built UI</title>" in page.text
    # After a rebuild the browser must fetch the page that names the new asset files.
    assert page.headers["cache-control"] == "no-cache"

    assert production.get("/assets/app-1a2b.js").text == "console.log('built')"
    favicon = production.get("/favicon.svg")
    assert favicon.status_code == 200 and favicon.headers["content-type"].startswith("image/svg+xml")


def test_production_mode_still_serves_the_api(production):
    assert production.get("/api/health").json() == {"status": "ok"}
    assert production.get("/api/papers").json() == []


def test_unknown_api_path_and_wrong_method_are_json_errors_in_production_mode(production):
    missing = production.get("/api/does-not-exist")
    assert (missing.status_code, missing.json()) == (404, {"detail": "Not Found"})
    wrong = production.put("/api/health")
    assert (wrong.status_code, wrong.json()) == (405, {"detail": "Method Not Allowed"})
    assert production.get("/assets/missing.js").status_code == 404


# --- Old settings file -----------------------------------------------------------------------------


@pytest.mark.parametrize("old_file_exists", [True, False])
def test_an_old_backend_env_file_is_reported_at_startup(monkeypatch, tmp_path, caplog, old_file_exists):
    # INSTALL.md: backend/.env is no longer read, "and the app warns if it exists".
    if old_file_exists:
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-old\n")
    monkeypatch.setattr(main_module, "BACKEND_DIR", tmp_path)

    with caplog.at_level(logging.WARNING, logger="app.main"), TestClient(app):
        pass

    warnings = [r.getMessage() for r in caplog.records if r.name == "app.main" and r.levelno == logging.WARNING]
    expected = ["backend/.env is not read; move its settings into .env in the project root."]
    assert warnings == (expected if old_file_exists else [])
