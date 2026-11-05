"""Downloading a search result's open-access PDF so the assistant can read the full paper.

PDF hosts are faked with `upstream`, and their names resolved by the fake `dns`.
"""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Paper
from app.services import fulltext
from support import pdfs
from support.known_bugs import fails_until_fixed, known_bug
from support.papers import BERT_META, events, meta, save
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


def pdf_in_pieces(data: bytes, piece: int = 64 * 1024):
    """A PDF that arrives in many pieces, as it does over a real network."""
    async def pieces():
        for start in range(0, len(data), piece):
            yield data[start:start + piece]

    return lambda request: httpx.Response(200, content=pieces(), headers={"content-type": "application/pdf"})


def with_size(megabytes: int, extra: int = 0) -> bytes:
    """The sample PDF, padded to exactly `megabytes` MB plus `extra` bytes."""
    data = pdfs.sample_pdf()
    return data + b"%" * (megabytes * 1024 * 1024 + extra - len(data))


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
    # The real name still goes in the Host header and is used for TLS (SNI and the certificate check).
    assert request.headers["host"] == "papers.example.org"
    assert request.extensions["sni_hostname"] == "papers.example.org"


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
    (lambda r: httpx.Response(302), "The PDF link returned HTTP 302."),  # a redirect that names no target
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


@pytest.mark.parametrize("reply", [pdf_reply, pdf_in_pieces], ids=["at once", "in pieces"])
@pytest.mark.parametrize("extra", [1, 1024 * 1024], ids=["one byte over", "a megabyte over"])
def test_pdf_over_the_size_limit_is_not_kept(client, upstream, paper, settings, monkeypatch, reply, extra):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    upstream.get(PDF_URL, reply(with_size(1, extra)))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == "The PDF is larger than 1 MB."
    assert body["has_pdf"] is False


@pytest.mark.parametrize("reply", [pdf_reply, pdf_in_pieces], ids=["at once", "in pieces"])
def test_a_pdf_exactly_as_large_as_the_limit_is_kept_byte_for_byte(client, upstream, paper, settings, monkeypatch,
                                                                   reply):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    data = with_size(1)
    upstream.get(PDF_URL, reply(data))

    assert fetch(client, paper["id"]).json()["full_text_status"] == "ok"
    assert client.get(f"/api/papers/{paper['id']}/pdf").content == data


def test_a_pdf_download_cannot_hang_forever(client, upstream, paper):
    # A host that stops answering must not keep the reader waiting without end.
    upstream.get(PDF_URL, pdf_reply())

    fetch(client, paper["id"])

    [request] = upstream.requests
    assert all(isinstance(limit, (int, float)) for limit in request.extensions["timeout"].values())


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


def test_a_plain_http_link_to_a_public_host_is_downloaded(client, upstream, dns):
    # arXiv's own PDF links are http:// links.
    dns["arxiv.org"] = PUBLIC_IP
    upstream.get("http://arxiv.org/pdf/1810.04805v2", pdf_reply())
    paper = save(client, meta(BERT_META, pdf_url="http://arxiv.org/pdf/1810.04805v2"))

    assert fetch(client, paper["id"]).json()["full_text_status"] == "ok"
    [request] = upstream.requests
    assert (request.url.scheme, request.url.host, request.headers["host"]) == ("http", PUBLIC_IP, "arxiv.org")


def test_a_link_with_a_port_is_downloaded_from_that_port(client, upstream, dns):
    dns["papers.example.org"] = PUBLIC_IP
    upstream.get("https://papers.example.org:8443/bert.pdf", pdf_reply())
    paper = save(client, meta(BERT_META, pdf_url="https://papers.example.org:8443/bert.pdf"))

    assert fetch(client, paper["id"]).json()["full_text_status"] == "ok"
    [request] = upstream.requests
    assert (request.url.host, request.url.port) == (PUBLIC_IP, 8443)
    assert request.headers["host"] == "papers.example.org:8443"  # the host and port the link names


def test_a_relative_redirect_is_followed_on_the_same_host(client, upstream, paper):
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": "/files/bert-v2.pdf"}))
    upstream.get("https://papers.example.org/files/bert-v2.pdf", pdf_reply())

    assert fetch(client, paper["id"]).json()["full_text_status"] == "ok"
    assert [(r.headers["host"], r.url.path) for r in upstream.requests] == [
        ("papers.example.org", "/bert.pdf"), ("papers.example.org", "/files/bert-v2.pdf")]


def test_redirect_to_another_public_host_is_followed(client, upstream, dns, paper):
    dns["cdn.example.net"] = "93.184.216.99"
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": "https://cdn.example.net/files/bert.pdf"}))
    upstream.get("https://cdn.example.net/files/bert.pdf", pdf_reply())

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "ok"
    # Each hop connects to the address checked for its own host.
    assert [(r.url.host, r.headers["host"], r.extensions["sni_hostname"]) for r in upstream.requests] == [
        (PUBLIC_IP, "papers.example.org", "papers.example.org"),
        ("93.184.216.99", "cdn.example.net", "cdn.example.net"),
    ]


def test_redirect_loops_give_up_after_5_redirects(client, upstream, paper):
    # README: "It checks every redirect again (at most 5)".
    upstream.get(PDF_URL, lambda r: httpx.Response(302, headers={"location": PDF_URL}))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert body["full_text_error"] == "The PDF could not be downloaded."
    assert len(upstream.requests) == 6  # the link and 5 redirects


def test_a_pdf_after_exactly_5_redirects_is_downloaded(client, upstream, paper):
    hops = [PDF_URL, *(f"https://papers.example.org/hop{n}.pdf" for n in range(1, 6))]
    for here, there in zip(hops, hops[1:]):
        upstream.get(here, lambda r, there=there: httpx.Response(302, headers={"location": there}))
    upstream.get(hops[-1], pdf_reply())

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "ok"
    assert len(upstream.requests) == 6


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


def test_a_host_with_any_private_address_is_not_downloaded(client, upstream, dns):
    # One answer is public, another points into the local network: the host is refused.
    dns["mixed.example.org"] = [PUBLIC_IP, "10.0.0.7"]
    paper = save(client, meta(BERT_META, pdf_url="https://mixed.example.org/paper.pdf"))

    body = fetch(client, paper["id"]).json()

    assert (body["full_text_status"], body["full_text_error"]) == ("error", PRIVATE_URL_MESSAGE)
    assert upstream.requests == []


@known_bug(
    "Confirmed app bug: fulltext._check_public raises UnsafeUrl for any non-http(s) link, and "
    "ensure_full_text reports every UnsafeUrl as 'points to a local or private address', which is "
    "false for an ftp:// link to a public host.")
def test_a_link_that_is_not_http_is_refused_with_a_true_reason(client, upstream):
    paper = save(client, meta(BERT_META, pdf_url="ftp://ftp.example.org/pub/bert.pdf"))

    body = fetch(client, paper["id"]).json()

    assert body["full_text_status"] == "error"
    assert upstream.requests == []
    with fails_until_fixed():
        assert "private" not in body["full_text_error"] and "local" not in body["full_text_error"]
        assert "http" in body["full_text_error"].lower()


MALFORMED_LINKS = ["https://papers.example.org:99999/bert.pdf",  # an invalid port
                   "http://[::1/bert.pdf"]  # a broken IPv6 literal


@known_bug(
    "Confirmed app bug: a malformed link makes urlsplit() raise ValueError in "
    "fulltext._check_public, which ensure_full_text does not catch, so /fulltext and /summary "
    "answer 500 instead of recording the failure and falling back to the abstract "
    "(ensure_full_text docstring: expected failures are recorded 'rather than raised').")
def test_a_malformed_pdf_link_is_recorded_and_the_abstract_is_used(fake_llm, upstream):
    with TestClient(app, raise_server_exceptions=False) as client:
        replies = []
        for n, url in enumerate(MALFORMED_LINKS):
            paper = save(client, meta(BERT_META, external_id=f"W-malformed-{n}", doi=None, pdf_url=url))
            replies.append((url, fetch(client, paper["id"]), client.post(f"/api/papers/{paper['id']}/summary")))

    assert upstream.requests == []
    with fails_until_fixed():
        for url, fetched, summary in replies:
            assert fetched.status_code == 200, url
            assert fetched.json()["full_text_status"] == "error" and fetched.json()["full_text_error"], url
            stream = events(summary)
            assert (stream[0]["context"], stream[-1]["type"]) == ("abstract", "done"), url


def test_a_paper_deleted_just_before_its_pdf_is_saved_is_404_and_nothing_is_stored(
        client, upstream, paper, settings, monkeypatch):
    upstream.get(PDF_URL, pdf_reply())
    real_store_pdf = fulltext.store_pdf

    def store_after_the_paper_was_deleted(data):
        with SessionLocal() as session:  # the user removes the paper at this very moment
            session.delete(session.get(Paper, paper["id"]))
            session.commit()
        return real_store_pdf(data)

    monkeypatch.setattr(fulltext, "store_pdf", store_after_the_paper_was_deleted)

    response = fetch(client, paper["id"])

    assert (response.status_code, response.json()["detail"]) == (404, "Paper not found.")
    assert list(settings.pdf_dir.iterdir()) == []


def test_a_paper_deleted_during_its_download_is_404_and_nothing_is_stored(client, upstream, paper, settings):
    def delete_then_answer(request):
        with SessionLocal() as session:  # the user removes the paper while its PDF downloads
            session.delete(session.get(Paper, paper["id"]))
            session.commit()
        return httpx.Response(200, content=pdfs.sample_pdf())

    upstream.get(PDF_URL, delete_then_answer)

    response = fetch(client, paper["id"])

    assert (response.status_code, response.json()["detail"]) == (404, "Paper not found.")
    assert not settings.pdf_dir.exists() or list(settings.pdf_dir.iterdir()) == []


def _stored_search_result(n: int) -> int:
    with SessionLocal() as session:
        paper = Paper(source="openalex", external_id=f"W{n}", title=f"Paper {n}", authors=[],
                      pdf_url=f"https://papers.example.org/{n}.pdf")
        session.add(paper)
        session.commit()
        return paper.id


async def _need_full_text(paper_id: int) -> bool:
    """What a request that needs the paper's text does (e.g. GET /outline, POST /summary)."""
    with SessionLocal() as session:
        return await fulltext.ensure_full_text(session.get(Paper, paper_id), session)


def _held_back(release: asyncio.Event):
    async def reply(request):
        await release.wait()
        return httpx.Response(200, content=pdfs.sample_pdf())

    return reply


async def _let_tasks_run() -> None:
    for _ in range(200):  # every request runs as far as it can while a PDF is held back
        await asyncio.sleep(0)


async def test_one_download_per_paper_at_a_time(upstream, dns):
    # E.g. the reader's page load and a click on "Generate summary" both need the full text.
    dns["papers.example.org"] = PUBLIC_IP
    paper_id = _stored_search_result(1)
    release = asyncio.Event()
    upstream.get("https://papers.example.org/1.pdf", _held_back(release))

    first = asyncio.create_task(_need_full_text(paper_id))
    second = asyncio.create_task(_need_full_text(paper_id))
    await _let_tasks_run()
    assert len(upstream.requests) == 1
    release.set()

    assert await asyncio.gather(first, second) == [True, True]
    assert len(upstream.requests) == 1
    with SessionLocal() as session:
        assert session.get(Paper, paper_id).full_text_status == "ok"


async def test_a_slow_download_does_not_hold_up_another_paper(upstream, dns):
    dns["papers.example.org"] = PUBLIC_IP
    slow, other = _stored_search_result(1), _stored_search_result(2)
    release = asyncio.Event()
    upstream.get("https://papers.example.org/1.pdf", _held_back(release))
    upstream.get("https://papers.example.org/2.pdf", lambda request: httpx.Response(200, content=pdfs.sample_pdf()))

    held = asyncio.create_task(_need_full_text(slow))
    await _let_tasks_run()

    assert await asyncio.wait_for(_need_full_text(other), timeout=5) is True  # did not wait for paper 1
    release.set()
    assert await held is True


async def test_requests_waiting_for_the_download_of_a_paper_deleted_meanwhile_report_it_gone(upstream, dns):
    dns["papers.example.org"] = PUBLIC_IP
    paper_id = _stored_search_result(1)
    release = asyncio.Event()
    upstream.get("https://papers.example.org/1.pdf", _held_back(release))

    first = asyncio.create_task(_need_full_text(paper_id))
    second = asyncio.create_task(_need_full_text(paper_id))  # waits for the first one's download
    await _let_tasks_run()
    with SessionLocal() as session:  # the user removes the paper meanwhile
        session.delete(session.get(Paper, paper_id))
        session.commit()
    release.set()

    assert await asyncio.gather(first, second) == [False, False]  # both answer 404 Paper not found
