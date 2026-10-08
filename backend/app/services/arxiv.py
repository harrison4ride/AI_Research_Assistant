"""arXiv search client (Atom API: https://info.arxiv.org/help/api/)."""

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET

import httpx

from ..schemas import PaperMeta
from .http import UpstreamError, get_client

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}

# arXiv drops these as stopwords, and an AND clause on a dropped term matches
# nothing — so "attention is all you need" would return zero results.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "that", "the", "this", "to", "via", "we", "with",
    "all", "you", "not", "using",
}

# arXiv asks clients to make one request at a time, 3 seconds apart.
_MIN_INTERVAL = 3.0
_rate_lock = asyncio.Lock()
_last_finished = 0.0


def build_query(query: str) -> str | None:
    """Exact phrase in title/abstract OR every keyword in title/abstract.

    The phrase clause ranks exact title matches first; the keyword clause keeps
    multi-concept topic queries ("graph neural networks drug discovery") working.
    Returns None when nothing searchable is left after removing punctuation.
    """
    clean = " ".join(re.sub(r"[^\w\s-]", " ", query).split())
    if not re.search(r"\w", clean):
        return None
    words = [w for w in re.split(r"[\s-]+", clean) if w and w.lower() not in STOPWORDS]
    parts = [f'ti:"{clean}"', f'abs:"{clean}"']
    if words:
        parts.append("(" + " AND ".join(f"(ti:{w} OR abs:{w})" for w in words) + ")")
    return " OR ".join(parts)


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return " ".join(el.text.split()) or None


def _strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def parse_entry(entry: ET.Element) -> PaperMeta:
    abs_url = _text(entry.find("a:id", NS)) or ""
    arxiv_id = _strip_version(abs_url.split("/abs/")[-1]) if "/abs/" in abs_url else None
    published = _text(entry.find("a:published", NS))
    pdf_url = None
    for link in entry.findall("a:link", NS):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href")
    return PaperMeta(
        source="arxiv",
        external_id=arxiv_id,
        title=_text(entry.find("a:title", NS)) or "(untitled)",
        authors=[
            name
            for a in entry.findall("a:author", NS)
            if (name := _text(a.find("a:name", NS)))
        ],
        year=int(published[:4]) if published and published[:4].isdigit() else None,
        abstract=_text(entry.find("a:summary", NS)),
        url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else abs_url or None,
        pdf_url=pdf_url,
        venue=_text(entry.find("arxiv:journal_ref", NS)) or "arXiv",
        doi=_text(entry.find("arxiv:doi", NS)),
    )


def _api_error(root: ET.Element) -> str | None:
    """arXiv reports bad queries as a 200 feed holding one entry whose id points at /api/errors."""
    for entry in root.findall("a:entry", NS):
        if "/api/errors" in (_text(entry.find("a:id", NS)) or ""):
            return _text(entry.find("a:summary", NS)) or "arXiv rejected the query."
    return None


async def _fetch(params: dict) -> httpx.Response:
    """Serialize arXiv calls and keep 3 s between the end of one and the start of the next."""
    global _last_finished
    async with _rate_lock:
        # A request that failed while this one waited may have started a cooldown.
        if time.monotonic() < _cooldown_until:
            raise _cooldown_error()
        wait = _MIN_INTERVAL - (time.monotonic() - _last_finished)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await get_client().get(API_URL, params=params)
        finally:
            _last_finished = time.monotonic()


# After arXiv refuses or stalls, stop calling it for a while instead of making
# every search wait for the same failure (arXiv counts all calls from one IP).
_cooldown_until = 0.0
MIN_COOLDOWN, MAX_COOLDOWN = 60.0, 600.0


def _start_cooldown(retry_after: str | None = None) -> None:
    global _cooldown_until
    seconds = MIN_COOLDOWN
    if retry_after and retry_after.strip().isdigit():
        seconds = min(max(float(retry_after), MIN_COOLDOWN), MAX_COOLDOWN)
    _cooldown_until = time.monotonic() + seconds


def _cooldown_error() -> UpstreamError:
    wait = max(1, round(_cooldown_until - time.monotonic()))
    return UpstreamError(
        f"arXiv is limiting requests right now, so it is paused for about {wait} s. Search OpenAlex meanwhile.",
        429,
    )


async def _query(params: dict) -> ET.Element:
    """Run one arXiv API call and return the parsed feed, raising UpstreamError on failure."""
    if time.monotonic() < _cooldown_until:
        raise _cooldown_error()
    try:
        resp = await _fetch(params)
    except httpx.TimeoutException as exc:
        _start_cooldown()
        raise UpstreamError(
            "arXiv did not answer in time (it may be limiting requests). Try again in a minute, or search OpenAlex.",
            504,
        ) from exc
    except httpx.HTTPError as exc:
        log.warning("arXiv request failed: %r", exc)
        raise UpstreamError("Could not reach arXiv. Check your connection and try again.") from exc
    if resp.status_code in (429, 503):
        _start_cooldown(resp.headers.get("retry-after"))
        raise _cooldown_error()
    if resp.status_code != 200:
        raise UpstreamError(f"arXiv returned HTTP {resp.status_code}.")
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise UpstreamError("arXiv returned malformed XML.") from exc
    if error := _api_error(root):
        raise UpstreamError(f"arXiv rejected the query: {error}", 400)
    return root


async def search(query: str, page: int, per_page: int) -> tuple[list[PaperMeta], int | None]:
    search_query = build_query(query)
    if search_query is None:
        return [], 0
    root = await _query({
        "search_query": search_query,
        "start": (page - 1) * per_page,
        "max_results": per_page,
        "sortBy": "relevance",
    })
    total_text = _text(root.find("os:totalResults", NS))
    total = int(total_text) if total_text and total_text.isdigit() else None
    return [parse_entry(e) for e in root.findall("a:entry", NS)], total


async def fetch_by_id(arxiv_id: str) -> PaperMeta | None:
    """Look up one paper by arXiv id (e.g. "1706.03762"); None if arXiv doesn't know it."""
    root = await _query({"id_list": arxiv_id, "max_results": 1})
    entry = root.find("a:entry", NS)
    if entry is None or entry.find("a:title", NS) is None:
        return None
    return parse_entry(entry)
