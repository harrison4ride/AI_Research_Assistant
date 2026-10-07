"""OpenAlex search client (https://docs.openalex.org/)."""

import html
import logging
import re

import httpx

from ..config import get_settings
from ..schemas import PaperMeta
from .http import UpstreamError, get_client

log = logging.getLogger(__name__)

API_URL = "https://api.openalex.org/works"
FIELDS = ",".join([
    "id", "display_name", "publication_year", "authorships", "abstract_inverted_index",
    "primary_location", "best_oa_location", "doi",
])

# Only real tags (letter right after "<"), so text like "p < 0.05, n > 30" survives.
_TAG_RE = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")


def _clean(text: str | None) -> str | None:
    """OpenAlex titles/abstracts sometimes carry HTML markup like <i>…</i>."""
    if not text:
        return None
    return " ".join(html.unescape(_TAG_RE.sub("", text)).split()) or None


def rebuild_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]}; turn it back into text."""
    if not inverted:
        return None
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return _clean(" ".join(word for _, word in sorted(positions)))


def parse_work(work: dict) -> PaperMeta:
    primary = work.get("primary_location") or {}
    best_oa = work.get("best_oa_location") or {}
    doi = work.get("doi")
    openalex_id = (work.get("id") or "").rsplit("/", 1)[-1] or None
    return PaperMeta(
        source="openalex",
        external_id=openalex_id,
        title=_clean(work.get("display_name")) or "(untitled)",
        authors=[
            name
            for a in work.get("authorships") or []
            if (name := (a.get("author") or {}).get("display_name"))
        ],
        year=work.get("publication_year"),
        abstract=rebuild_abstract(work.get("abstract_inverted_index")),
        url=primary.get("landing_page_url") or doi or work.get("id"),
        pdf_url=best_oa.get("pdf_url") or primary.get("pdf_url"),
        venue=(primary.get("source") or {}).get("display_name"),
        doi=doi.removeprefix("https://doi.org/") if doi else None,
    )


async def search(query: str, page: int, per_page: int) -> tuple[list[PaperMeta], int | None]:
    settings = get_settings()
    params: dict[str, str | int] = {
        "search": query,
        "page": page,
        "per_page": per_page,
        "select": FIELDS,
    }
    if settings.openalex_email:
        params["mailto"] = settings.openalex_email
    if settings.openalex_api_key:
        params["api_key"] = settings.openalex_api_key
    try:
        resp = await get_client().get(API_URL, params=params)
    except httpx.TimeoutException as exc:
        raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
    except httpx.HTTPError as exc:
        log.warning("OpenAlex request failed: %r", exc)
        raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
    if resp.status_code == 429:
        raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
    if resp.status_code != 200:
        raise UpstreamError(f"OpenAlex returned HTTP {resp.status_code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise UpstreamError("OpenAlex returned invalid JSON.") from exc
    total = (data.get("meta") or {}).get("count")
    return [parse_work(w) for w in data.get("results") or []], total
