"""Application settings, loaded from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where the SQLite DB and uploaded PDFs live. Relative paths are resolved
    # against backend/ so the location doesn't depend on the launch directory.
    data_dir: Path = BACKEND_DIR / "data"

    @field_validator("data_dir")
    @classmethod
    def _anchor_data_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    max_pdf_mb: int = 50

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdfs"

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
    llm_max_tokens: int = 32000
    # Paper text beyond this many characters (~4 chars per token) is cut off.
    llm_max_paper_chars: int = 400_000
    # Q&A turns of history sent with each new question.
    llm_history_messages: int = 20
    # Use the LLM to extract title/authors/year/abstract from uploaded PDFs.
    llm_extract_metadata: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
