"""Fake external HTTP services (OpenAlex, arXiv, PDF hosts) and canned responses.

The app sends every outgoing request through one shared httpx client
(app.services.http.get_client). The tests replace that client with one whose
transport is FakeUpstream.handle, so no request ever leaves the machine.
"""

from collections.abc import Callable
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import httpx

Handler = Callable[[httpx.Request], httpx.Response]

OPENALEX_WORKS = "https://api.openalex.org/works"
ARXIV_QUERY = "https://export.arxiv.org/api/query"
# A public address for fake PDF hosts (the download refuses private ones).
PUBLIC_IP = "93.184.216.34"


class FakeUpstream:
    """Answers requests from registered handlers and records every request."""

    def __init__(self) -> None:
        self._routes: list[tuple[str, str, str, Handler]] = []
        self.requests: list[httpx.Request] = []
        self.unexpected: list[str] = []

    def on(self, method: str, url: str, handler: Handler) -> None:
        """Answer `method url` (query string ignored) with `handler(request)`. Later routes win."""
        parts = urlsplit(url)
        self._routes.append((method.upper(), parts.hostname or "", parts.path or "/", handler))

    def get(self, url: str, handler: Handler) -> None:
        self.on("GET", url, handler)

    def json(self, url: str, payload: object, status: int = 200, headers: dict | None = None) -> None:
        self.get(url, lambda request: httpx.Response(status, json=payload, headers=headers))

    def text(self, url: str, body: str | bytes, status: int = 200, content_type: str = "text/plain",
             headers: dict | None = None) -> None:
        self.get(url, lambda request: httpx.Response(
            status, content=body, headers={"content-type": content_type, **(headers or {})}))

    def fail(self, url: str, error: type[httpx.HTTPError], message: str = "simulated failure") -> None:
        """Make requests to `url` raise a transport error (timeout, connection refused, ...)."""
        def raise_error(request: httpx.Request) -> httpx.Response:
            raise error(message, request=request)
        self.get(url, raise_error)

    def sent_to(self, url: str) -> list[httpx.Request]:
        """Requests whose (Host header, path) match `url`."""
        parts = urlsplit(url)
        return [r for r in self.requests if _host(r) == parts.hostname and r.url.path == (parts.path or "/")]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = _host(request)
        for method, route_host, path, handler in reversed(self._routes):
            if method == request.method and route_host == host and path == request.url.path:
                return handler(request)
        self.unexpected.append(f"{request.method} {request.url} (Host: {host})")
        return httpx.Response(599, text="No fake upstream is registered for this URL.")


def _host(request: httpx.Request) -> str:
    # PDF downloads connect to a vetted IP and name the real host in the Host header.
    return request.headers.get("host", request.url.host).split(":")[0]


# --- OpenAlex ---------------------------------------------------------------------


def openalex_work(
    work_id: str = "W2741809807",
    title: str | None = "Attention Is All You Need",
    authors: tuple[str, ...] = ("Ashish Vaswani", "Noam Shazeer"),
    year: int | None = 2017,
    abstract: str | None = "The dominant sequence transduction models are based on complex recurrent networks.",
    doi: str | None = "https://doi.org/10.48550/arxiv.1706.03762",
    landing_page: str | None = "https://arxiv.org/abs/1706.03762",
    pdf_url: str | None = "https://arxiv.org/pdf/1706.03762",
    venue: str | None = "arXiv (Cornell University)",
) -> dict:
    """One work in the shape the OpenAlex /works endpoint returns (abstract as an inverted index)."""
    inverted: dict[str, list[int]] = {}
    for position, word in enumerate((abstract or "").split()):
        inverted.setdefault(word, []).append(position)
    return {
        "id": f"https://openalex.org/{work_id}",
        "display_name": title,
        "publication_year": year,
        "authorships": [{"author": {"display_name": name}} for name in authors],
        "abstract_inverted_index": inverted or None,
        "primary_location": {
            "landing_page_url": landing_page,
            "pdf_url": None,
            "source": {"display_name": venue} if venue else None,
        },
        "best_oa_location": {"pdf_url": pdf_url} if pdf_url else None,
        "doi": doi,
    }


def openalex_page(works: list[dict], count: int | None = None) -> dict:
    return {"meta": {"count": len(works) if count is None else count}, "results": works}


# --- arXiv ------------------------------------------------------------------------


def arxiv_entry(
    arxiv_id: str = "1706.03762v7",
    title: str = "Attention Is All\n      You Need",
    authors: tuple[str, ...] = ("Ashish Vaswani", "Noam Shazeer", "Niki Parmar"),
    published: str = "2017-06-12T17:57:34Z",
    summary: str = "  The dominant sequence transduction models are based on complex recurrent\n  networks.  ",
    doi: str | None = "10.48550/arXiv.1706.03762",
    journal_ref: str | None = "NeurIPS 2017",
) -> str:
    """One <entry> of an arXiv Atom feed."""
    parts = [
        "<entry>",
        f"<id>http://arxiv.org/abs/{arxiv_id}</id>",
        f"<published>{published}</published>",
        f"<title>{escape(title)}</title>",
        f"<summary>{escape(summary)}</summary>",
        *(f"<author><name>{escape(name)}</name></author>" for name in authors),
        f"<arxiv:doi>{escape(doi)}</arxiv:doi>" if doi else "",
        f"<arxiv:journal_ref>{escape(journal_ref)}</arxiv:journal_ref>" if journal_ref else "",
        f'<link href="http://arxiv.org/abs/{arxiv_id}" rel="alternate" type="text/html"/>',
        f'<link title="pdf" href="http://arxiv.org/pdf/{arxiv_id}" rel="related" type="application/pdf"/>',
        "</entry>",
    ]
    return "".join(parts)


def arxiv_feed(entries: list[str], total: int | None = None) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" '
        'xmlns:arxiv="http://arxiv.org/schemas/atom">'
        f"<opensearch:totalResults>{len(entries) if total is None else total}</opensearch:totalResults>"
        + "".join(entries)
        + "</feed>"
    )


def arxiv_error_feed(message: str) -> str:
    """How arXiv reports a bad query: HTTP 200 with a single error entry."""
    return arxiv_feed([
        "<entry><id>http://arxiv.org/api/errors#incorrect_query</id>"
        f"<title>Error</title><summary>{escape(message)}</summary></entry>"
    ], total=1)

