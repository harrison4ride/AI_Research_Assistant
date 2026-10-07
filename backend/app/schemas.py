"""Pydantic models shared by the API routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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


class SavedKey(BaseModel):
    """Maps a search result identity to its library id."""

    source: str
    external_id: str
    id: int
