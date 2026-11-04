"""App-level behavior: health check, configuration for the UI, and the root page."""

from pathlib import Path

from app.services import claude_code


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_explains_where_the_ui_is_when_only_the_api_is_served(client):
    # The tests run with SERVE_FRONTEND=false, as `make dev` does.
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "This port serves only the API" in response.text
    assert "http://localhost:5173" in response.text


def test_unknown_api_path_is_a_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_wrong_method_is_a_405(client):
    assert client.put("/api/health").status_code == 405


def test_config_for_the_default_claude_code_provider(client):
    body = client.get("/api/config").json()
    assert body["llm_provider"] == "claude-code"
    assert body["llm_model"] == "Claude Code (opus)"
    assert body["llm_default_model"] == "opus"
    assert [m["id"] for m in body["llm_models"]] == ["opus", "sonnet", "haiku", "fable", "default"]
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
    assert body["llm_hint"] == claude_code.LOGIN_HINT


def test_config_for_the_api_provider(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "api")
    body = client.get("/api/config").json()
    assert body["llm_provider"] == "api"
    assert body["llm_model"] == "claude-opus-5"
    assert body["llm_default_model"] == "claude-opus-5"
    assert [m["id"] for m in body["llm_models"]] == [
        "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5-1"]
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
