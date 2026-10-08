"""Application settings, loaded from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # One settings file, in the repo root. Variables set in the shell take
    # precedence, except empty ones (an empty exported ANTHROPIC_API_KEY must not
    # hide the key in .env).
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- Storage ---
    # Where the SQLite DB and uploaded PDFs live.
    data_dir: Path = BACKEND_DIR / "data"
    # Built frontend (npm run build). When present, the backend serves it too,
    # so the whole app runs as one process on one port.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # Off in development, where Vite serves the live UI and dist/ may be stale.
    serve_frontend: bool = True
    max_pdf_mb: int = Field(50, gt=0)

    # --- Paper search ---
    # Optional OpenAlex identification: an email puts requests in the "polite
    # pool"; an API key raises the free daily quota.
    openalex_email: str | None = None
    openalex_api_key: str | None = None

    # --- LLM (Anthropic Claude) ---
    # Read from .env; if unset, the SDK falls back to its own credential lookup.
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    llm_model: str = "claude-opus-5"
    # Thinking depth / cost. Claude Opus 5 is strong at "medium"; raise for harder questions.
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # Upper bound on thinking + answer tokens per response.
    llm_max_tokens: int = Field(32000, gt=0, le=128000)
    # Paper text beyond this many characters (~4 chars per token) is cut off.
    llm_max_paper_chars: int = Field(400_000, gt=0)
    # Q&A turns of history sent with each new question.
    llm_history_messages: int = Field(20, ge=0)
    # Use the LLM to extract title/authors/year/abstract from uploaded PDFs.
    llm_extract_metadata: bool = True

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdfs"

    @field_validator("data_dir", "frontend_dist")
    @classmethod
    def _anchor_relative_paths(cls, value: Path) -> Path:
        # Resolve relative paths against backend/, so they don't depend on the launch directory.
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
