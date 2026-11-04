"""Downloading a search result's open-access PDF so the assistant can read the full paper.

PDF hosts are faked with `upstream`, and their names resolved by the fake `dns`.
"""

import httpx
import pytest

from app.services import fulltext
from support import pdfs
from support.papers import BERT_META, meta, save
from support.upstream import PUBLIC_IP

PDF_URL = "https://papers.example.org/bert.pdf"
PRIVATE_URL_MESSAGE = "The PDF link points to a local or private address, so it was not downloaded."


@pytest.fixture
def paper(client, dns):
    dns["papers.example.org"] = PUBLIC_IP
    return save(client, meta(BERT_META, pdf_url=PDF_URL))


def fetch(client, paper_id: int, retry: bool = False):
    return client.post(f"/api/papers/{paper_id}/fulltext", params={"retry": "true"} if retry else None)


def pdf_reply(data: bytes | None = None):
    return lambda request: httpx.Response(200, content=data or pdfs.sample_pdf(),
                                          headers={"content-type": "application/pdf"})


def test_download_open_access_pdf(client, upstream, paper):
    upstream.get(PDF_URL, pdf_reply())

    response = fetch(client, paper["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["full_text_status"] == "ok" and body["full_text_error"] is None
    assert body["has_pdf"] is True and body["page_count"] == 2
    assert client.get(f"/api/papers/{paper['id']}/pdf").content == pdfs.sample_pdf()


def test_download_connects_to_the_checked_address(client, upstream, paper):
    # The address is resolved once and checked; the request then goes to that IP, so a
    # second DNS answer cannot swap in a private address (DNS rebinding).
    upstream.get(PDF_URL, pdf_reply())

    fetch(client, paper["id"])

    [request] = upstream.requests
    assert request.url.host == PUBLIC_IP
    assert request.headers["host"] == "papers.example.org"


def test_paper_without_a_pdf_link(client, upstream):
    paper = save(client, BERT_META)  # pdf_url is None

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "unavailable"
    assert body["full_text_error"] == "No open-access PDF link is known for this paper."
    assert upstream.requests == []


@pytest.mark.parametrize(("reply", "error"), [
    (lambda r: httpx.Response(200, text="<html>Please log in</html>", headers={"content-type": "text/html"}),
     "The PDF link led to a web page instead of a PDF file."),
    (lambda r: httpx.Response(404), "The PDF link returned HTTP 404."),
    (lambda r: httpx.Response(403), "The PDF link returned HTTP 403."),
    (lambda r: httpx.Response(200, content=pdfs.blank_pdf()),
     "No text could be extracted. The PDF may be a scanned image."),
])
def test_download_failures_are_recorded_with_the_reason(client, upstream, paper, reply, error):
    upstream.get(PDF_URL, reply)

    response = fetch(client, paper["id"])

    assert response.status_code == 200  # the paper still works, on its abstract
    body = response.json()
    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == error
    assert body["has_pdf"] is False


def test_network_error_while_downloading(client, upstream, paper):
    upstream.fail(PDF_URL, httpx.ConnectError, "connection reset")

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == "The PDF could not be downloaded."


def test_pdf_over_the_size_limit_is_not_kept(client, upstream, paper, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    upstream.get(PDF_URL, pdf_reply(pdfs.sample_pdf() + b"%" * (2 * 1024 * 1024)))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == "The PDF is larger than 1 MB."
    assert body["has_pdf"] is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/api/papers",
    "http://localhost/secret.pdf",
    "http://[::1]/paper.pdf",
    "http://10.0.0.7/paper.pdf",
    "http://192.168.1.20/paper.pdf",
    "http://169.254.169.254/latest/meta-data/",
    "http://intranet.example.org/paper.pdf",
])
def test_links_to_local_or_private_addresses_are_not_downloaded(client, upstream, dns, url):
    dns["localhost"] = "127.0.0.1"
    dns["intranet.example.org"] = "10.1.2.3"
    paper = save(client, meta(BERT_META, pdf_url=url))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == PRIVATE_URL_MESSAGE
    assert upstream.requests == []


def test_redirect_to_a_private_address_is_not_followed(client, upstream, paper):
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": "http://10.0.0.7/internal.pdf"}))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_error"] == PRIVATE_URL_MESSAGE
    assert len(upstream.requests) == 1  # only the first hop was requested


def test_redirect_to_another_public_host_is_followed(client, upstream, dns, paper):
    dns["cdn.example.net"] = "93.184.216.99"
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": "https://cdn.example.net/files/bert.pdf"}))
    upstream.get("https://cdn.example.net/files/bert.pdf", pdf_reply())

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "ok"
    assert [r.headers["host"] for r in upstream.requests] == ["papers.example.org", "cdn.example.net"]


def test_redirect_loops_give_up(client, upstream, paper):
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": PDF_URL}))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == "The PDF could not be downloaded."
    assert len(upstream.requests) == fulltext.MAX_REDIRECTS + 1


def test_unresolvable_host(client, upstream):
    paper = save(client, meta(BERT_META, pdf_url="https://no-such-host.invalid/paper.pdf"))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_error"] == "The PDF could not be downloaded."
    assert upstream.requests == []


def test_failed_download_is_not_repeated_unless_retried(client, upstream, paper):
    upstream.get(PDF_URL, lambda r: httpx.Response(503))
    assert fetch(client, paper["id"]).json()["full_text_status"] == "error"

    upstream.get(PDF_URL, pdf_reply())
    again = fetch(client, paper["id"]).json()
    assert again["full_text_status"] == "error" and len(upstream.requests) == 1

    retried = fetch(client, paper["id"], retry=True).json()
    assert retried["full_text_status"] == "ok" and len(upstream.requests) == 2


def test_successful_download_is_not_repeated(client, upstream, paper):
    upstream.get(PDF_URL, pdf_reply())
    fetch(client, paper["id"])

    assert fetch(client, paper["id"], retry=True).json()["full_text_status"] == "ok"
    assert len(upstream.requests) == 1


def test_fetch_full_text_of_unknown_paper(client):
    assert fetch(client, 999999).status_code == 404


@pytest.mark.parametrize("url", ["ftp://papers.example.org/x.pdf", "file:///etc/passwd", "javascript:alert(1)"])
async def test_only_http_and_https_links_are_allowed(url):
    with pytest.raises(fulltext.UnsafeUrl):
        await fulltext._check_public(url)


async def test_public_address_check_returns_the_ip_to_connect_to(dns):
    dns["papers.example.org"] = PUBLIC_IP
    assert await fulltext._check_public("https://papers.example.org/x.pdf") == PUBLIC_IP
