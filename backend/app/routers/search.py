"""Paper search across external sources (F1)."""

from fastapi import APIRouter, HTTPException, Query

from ..schemas import SearchResponse, SearchSource
from ..services import arxiv, openalex
from ..services.http import UpstreamError

router = APIRouter(prefix="/api", tags=["search"])

SOURCES = {"arxiv": arxiv.search, "openalex": openalex.search}


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=300, description="Keywords or a research topic"),
    source: SearchSource = "arxiv",
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(10, ge=1, le=50),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(422, "Search query must not be blank.")
    try:
        results, total = await SOURCES[source](query, page, per_page)
    except UpstreamError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return SearchResponse(
        query=query, source=source, page=page, per_page=per_page, total=total, results=results
    )
