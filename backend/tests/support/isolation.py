"""Pinning the app's settings, shared by the backend tests and the end-to-end server.

Both must keep the app away from the repository's .env, the real database, real
credentials, and a real LLM. Call isolate_settings() before anything reads the
settings (app.db reads them when it is imported).
"""

import os
from pathlib import Path

# Variables outside the Settings model that would reach a real model or account.
_EXTRA_VARIABLES = ["anthropic_auth_token", "anthropic_profile", "claudecode"]


def isolate_settings(*, data_dir: Path, claude_code_path: Path, **values: str | Path) -> None:
    """Replace every app setting in the environment with test values and ignore .env.

    `values` are extra settings by field name, e.g. serve_frontend="true".
    """
    from app import config

    for name in [*config.Settings.model_fields, *_EXTRA_VARIABLES]:
        os.environ.pop(name.upper(), None)
        os.environ.pop(name, None)
    os.environ.update({
        "DATA_DIR": str(data_dir),
        "LLM_PROVIDER": "claude-code",
        "CLAUDE_CODE_MODEL": "opus",
        # A missing file in the tests, the fake CLI in the end-to-end server.
        "CLAUDE_CODE_PATH": str(claude_code_path),
        # A fake key, and an address where nothing listens: an API call that was not
        # faked fails at once instead of reaching Anthropic.
        "ANTHROPIC_API_KEY": "test-key-not-real",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
        **{name.upper(): str(value) for name, value in values.items()},
    })
    config.Settings.model_config["env_file"] = None
    config.get_settings.cache_clear()
