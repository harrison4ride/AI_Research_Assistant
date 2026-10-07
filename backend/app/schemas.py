"""Pydantic models shared by the API routes."""

from typing import Literal

from pydantic import BaseModel

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
