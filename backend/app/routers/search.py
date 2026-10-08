"""Paper search across external sources (F1)."""

import time
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, Query

from ..schemas import SearchResponse, SearchSource
from ..services import arxiv, openalex
from ..services.http import UpstreamError

router = APIRouter(prefix="/api", tags=["search"])

SOURCES = {"arxiv": arxiv.search, "openalex": openalex.search}

# Recent results, so repeating a search (or paging back) doesn't call the
# source again: arXiv in particular rate-limits all calls from one IP.
CACHE_TTL = 600.0
CACHE_SIZE = 256
_cache: OrderedDict[tuple, tuple[float, SearchResponse]] = OrderedDict()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=300, description="Keywords or a research topic"),
    source: SearchSource = "openalex",
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(10, ge=1, le=50),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(422, "Search query must not be blank.")
    # Case matters: OpenAlex treats uppercase AND/OR/NOT as operators.
    key = (source, " ".join(query.split()), page, per_page)
    now = time.monotonic()
    if (hit := _cache.get(key)) and hit[0] > now:
        _cache.move_to_end(key)
        return hit[1]
    try:
        results, total = await SOURCES[source](query, page, per_page)
    except UpstreamError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    response = SearchResponse(
        query=query, source=source, page=page, per_page=per_page, total=total, results=results
    )
    _cache[key] = (now + CACHE_TTL, response)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return response
