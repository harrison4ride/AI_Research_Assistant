"""Pydantic models shared by the API routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SearchSource = Literal["arxiv", "openalex"]


class PaperMeta(BaseModel):
    """Bibliographic metadata for one paper, independent of where it came from."""

    source: Literal["arxiv", "openalex", "upload"]
    external_id: str | None = None
    title: str
    authors: list[str] = []
    year: int | None = None
    abstract: str | None = None
    url: str | None = None  # landing page
    pdf_url: str | None = None
    venue: str | None = None
    doi: str | None = None


class SearchResponse(BaseModel):
    query: str
    source: SearchSource
    page: int
    per_page: int
    total: int | None
    results: list[PaperMeta]


class PaperOut(PaperMeta):
    """A paper stored in the local library."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    has_pdf: bool = False
    page_count: int | None = None
    full_text_status: Literal["ok", "unavailable", "error"] | None = None
    full_text_error: str | None = None


class PaperDetail(PaperOut):
    """A single paper with its stored summary (the list view omits it)."""

    summary: str | None = None
    summary_model: str | None = None
    summary_context: Literal["full_text", "abstract"] | None = None
    summary_created_at: datetime | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    model: str | None = None
    context: Literal["full_text", "abstract"] | None = None
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()


class AppConfig(BaseModel):
    llm_provider: Literal["claude-code", "api"]
    llm_model: str  # human-readable label, e.g. "Claude Code (opus)"
    llm_ready: bool  # whether summaries and Q&A can run
    llm_hint: str | None  # how to fix it when not ready


class PaperUpdate(BaseModel):
    """Editable metadata fields (e.g. to correct what was extracted from a PDF)."""

    title: str | None = Field(None, min_length=1, max_length=500)
    # Large collaborations list thousands of authors; the form sends the full list.
    authors: list[str] | None = Field(None, max_length=10000)
    year: int | None = Field(None, ge=1000, le=2100)
    abstract: str | None = Field(None, max_length=20000)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title must not be blank")
        return v.strip() if v else v

    @field_validator("authors")
    @classmethod
    def _clean_authors(cls, v: list[str] | None) -> list[str] | None:
        return [a.strip() for a in v if a.strip()] if v is not None else v


class SavedKey(BaseModel):
    """Maps a search result identity to its library id."""

    source: str
    external_id: str
    id: int
