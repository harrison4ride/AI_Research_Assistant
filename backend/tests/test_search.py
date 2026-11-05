"""F1: searching for papers through OpenAlex (the default) and arXiv.

External APIs are faked with `upstream` (see conftest.py); nothing leaves the machine.
"""

import httpx
import pytest

from app.services import arxiv, openalex
from support.upstream import (
    ARXIV_QUERY,
    OPENALEX_WORKS,
    arxiv_entry,
    arxiv_error_feed,
    arxiv_feed,
    openalex_page,
    openalex_work,
)

# --- OpenAlex ------------------------------------------------------------------------


def test_openalex_search_returns_the_fields_the_ui_shows(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([openalex_work()], count=1234))

    response = client.get("/api/search", params={"q": "attention is all you need"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "attention is all you need"
    assert (body["source"], body["page"], body["per_page"], body["total"]) == ("openalex", 1, 10, 1234)
    assert body["results"] == [{
        "source": "openalex",
        "external_id": "W2741809807",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "year": 2017,
        "abstract": "The dominant sequence transduction models are based on complex recurrent networks.",
        "url": "https://arxiv.org/abs/1706.03762",
        "pdf_url": "https://arxiv.org/pdf/1706.03762",
        "venue": "arXiv (Cornell University)",
        "doi": "10.48550/arxiv.1706.03762",
    }]


def test_openalex_is_the_default_source_and_gets_the_query_and_paging(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([]))

    response = client.get("/api/search", params={"q": "  graph neural networks  ", "page": 3, "per_page": 25})

    [request] = upstream.sent_to(OPENALEX_WORKS)
    params = request.url.params
    assert params["search"] == "graph neural networks"  # trimmed
    assert (params["page"], params["per_page"]) == ("3", "25")
    assert "abstract_inverted_index" in params["select"].split(",")
    assert "mailto" not in params and "api_key" not in params
    # The response names the page it holds, which "Load more" continues from.
    body = response.json()
    assert (body["query"], body["source"], body["page"], body["per_page"]) == ("graph neural networks", "openalex", 3, 25)


@pytest.mark.parametrize("source", ["openalex", "arxiv"])
def test_the_largest_valid_search_is_accepted(client, upstream, source):
    upstream.json(OPENALEX_WORKS, openalex_page([]))
    upstream.text(ARXIV_QUERY, arxiv_feed([]))
    query = "transformer " * 25  # 300 characters, the search box's maxLength

    response = client.get("/api/search", params={"q": query, "source": source, "page": 100, "per_page": 50})

    assert response.status_code == 200
    assert (response.json()["page"], response.json()["per_page"]) == (100, 50)
    [request] = upstream.requests
    params = request.url.params
    if source == "openalex":
        assert (params["page"], params["per_page"]) == ("100", "50")
    else:
        assert (params["start"], params["max_results"]) == ("4950", "50")


def test_openalex_email_and_api_key_are_sent_when_configured(client, upstream, settings, monkeypatch):
    monkeypatch.setattr(settings, "openalex_email", "me@example.org")
    monkeypatch.setattr(settings, "openalex_api_key", "oa-key")
    upstream.json(OPENALEX_WORKS, openalex_page([]))

    client.get("/api/search", params={"q": "rag"})

    params = upstream.sent_to(OPENALEX_WORKS)[0].url.params
    assert (params["mailto"], params["api_key"]) == ("me@example.org", "oa-key")


def test_openalex_result_with_missing_fields(client, upstream):
    work = openalex_work(title=None, authors=(), year=None, abstract=None, doi=None,
                         landing_page=None, pdf_url=None, venue=None)
    without_id = {**openalex_work(work_id="W1"), "id": None}
    upstream.json(OPENALEX_WORKS, openalex_page([work, without_id]))

    result, other = client.get("/api/search", params={"q": "x"}).json()["results"]

    assert result["title"] == "(untitled)"
    assert result["authors"] == []
    assert result["year"] is None and result["abstract"] is None and result["doi"] is None
    assert result["pdf_url"] is None and result["venue"] is None
    assert result["url"] == "https://openalex.org/W2741809807"  # falls back to the OpenAlex page
    assert (other["external_id"], other["url"]) == (None, "https://arxiv.org/abs/1706.03762")


def test_openalex_pdf_link_of_the_primary_location_is_used_when_there_is_no_open_access_one(client, upstream):
    work = openalex_work(pdf_url=None)
    work["primary_location"]["pdf_url"] = "https://publisher.example/paper.pdf"
    upstream.json(OPENALEX_WORKS, openalex_page([work]))

    [result] = client.get("/api/search", params={"q": "x"}).json()["results"]

    assert result["pdf_url"] == "https://publisher.example/paper.pdf"


def test_openalex_markup_is_removed_but_comparisons_are_kept(client, upstream):
    work = openalex_work(title="<i>In vivo</i> imaging &amp; more",
                         abstract="Significant at p < 0.05, n > 30 <b>subjects</b>.")
    upstream.json(OPENALEX_WORKS, openalex_page([work]))

    [result] = client.get("/api/search", params={"q": "x"}).json()["results"]

    assert result["title"] == "In vivo imaging & more"
    assert result["abstract"] == "Significant at p < 0.05, n > 30 subjects."


def test_openalex_empty_result(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([], count=0))

    body = client.get("/api/search", params={"q": "zzzz no such topic"}).json()

    assert body["results"] == [] and body["total"] == 0


@pytest.mark.parametrize(("reply", "status", "detail"), [
    (lambda r: httpx.Response(500), 502, "OpenAlex returned HTTP 500."),
    (lambda r: httpx.Response(429), 429, "OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv."),
    (lambda r: httpx.Response(200, text="<html>maintenance</html>"), 502, "OpenAlex returned invalid JSON."),
])
def test_openalex_errors_become_clear_http_errors(client, upstream, reply, status, detail):
    upstream.get(OPENALEX_WORKS, reply)

    response = client.get("/api/search", params={"q": "rag"})

    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_openalex_timeout(client, upstream):
    upstream.fail(OPENALEX_WORKS, httpx.ReadTimeout)

    response = client.get("/api/search", params={"q": "rag"})

    assert response.status_code == 504
    assert response.json()["detail"] == "OpenAlex timed out, please try again."


def test_network_error_message_does_not_leak_internal_details(client, upstream):
    upstream.fail(OPENALEX_WORKS, httpx.ConnectError, "[Errno 8] nodename nor servname provided")

    response = client.get("/api/search", params={"q": "rag"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not reach OpenAlex. Check your connection and try again."


# --- arXiv ---------------------------------------------------------------------------


def test_arxiv_search_parses_the_atom_feed(client, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([arxiv_entry()], total=42), content_type="application/atom+xml")

    response = client.get("/api/search", params={"q": "attention is all you need", "source": "arxiv"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "arxiv" and body["total"] == 42
    assert body["results"] == [{
        "source": "arxiv",
        "external_id": "1706.03762",  # version suffix removed
        "title": "Attention Is All You Need",  # line breaks collapsed
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        "year": 2017,
        "abstract": "The dominant sequence transduction models are based on complex recurrent networks.",
        "url": "https://arxiv.org/abs/1706.03762",
        "pdf_url": "http://arxiv.org/pdf/1706.03762v7",
        "venue": "NeurIPS 2017",
        "doi": "10.48550/arXiv.1706.03762",
    }]


def test_arxiv_query_keeps_exact_phrase_and_drops_stopwords(client, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([]))

    client.get("/api/search", params={"q": "attention is all you need", "source": "arxiv",
                                      "page": 3, "per_page": 5})

    params = upstream.sent_to(ARXIV_QUERY)[0].url.params
    assert params["search_query"] == (
        'ti:"attention is all you need" OR abs:"attention is all you need" OR '
        "((ti:attention OR abs:attention) AND (ti:need OR abs:need))"
    )
    assert (params["start"], params["max_results"]) == ("10", "5")
    assert params["sortBy"] == "relevance"  # best matches first


def test_arxiv_entries_with_missing_fields(client, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([
        "<entry><title>A Paper Without Details</title></entry>",  # no id, date, abstract, authors, or links
        "<entry><id>https://example.org/papers/42</id></entry>",  # no title, and an id that is not arXiv's
    ]))

    first, second = client.get("/api/search", params={"q": "x", "source": "arxiv"}).json()["results"]

    assert first == {"source": "arxiv", "external_id": None, "title": "A Paper Without Details", "authors": [],
                     "year": None, "abstract": None, "url": None, "pdf_url": None, "venue": "arXiv", "doi": None}
    assert (second["title"], second["external_id"], second["url"]) == (
        "(untitled)", None, "https://example.org/papers/42")


@pytest.mark.parametrize(("links", "pdf_url"), [
    ('<link title="pdf" href="https://arxiv.org/pdf/2101.00001v1"/>', "https://arxiv.org/pdf/2101.00001v1"),
    ('<link href="https://arxiv.org/pdf/2101.00001v1" type="application/pdf"/>', "https://arxiv.org/pdf/2101.00001v1"),
    ('<link title="pdf" href="https://arxiv.org/pdf/2101.00001v1" rel="related" type="application/pdf"/>'
     '<link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>',
     "https://arxiv.org/pdf/2101.00001v1"),
    ('<link href="https://arxiv.org/abs/2101.00001v1" rel="alternate" type="text/html"/>', None),
], ids=["marked by its title", "marked by its type", "before the abstract page", "no PDF link"])
def test_arxiv_pdf_link_is_recognized_by_its_title_or_its_type(client, upstream, links, pdf_url):
    entry = f"<entry><id>http://arxiv.org/abs/2101.00001v1</id><title>A Paper</title>{links}</entry>"
    upstream.text(ARXIV_QUERY, arxiv_feed([entry]))

    [result] = client.get("/api/search", params={"q": "x", "source": "arxiv"}).json()["results"]

    assert result["pdf_url"] == pdf_url


@pytest.mark.parametrize("total", [None, "about 40"], ids=["missing", "not a number"])
def test_arxiv_feed_without_a_usable_total_still_shows_its_results(client, upstream, total):
    feed = arxiv_feed([arxiv_entry()]).replace(
        "<opensearch:totalResults>1</opensearch:totalResults>",
        f"<opensearch:totalResults>{total}</opensearch:totalResults>" if total else "")
    upstream.text(ARXIV_QUERY, feed)

    body = client.get("/api/search", params={"q": "x", "source": "arxiv"}).json()

    assert body["total"] is None and [r["external_id"] for r in body["results"]] == ["1706.03762"]


def test_arxiv_entry_without_journal_reference_is_labelled_arxiv(client, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([arxiv_entry(journal_ref=None, doi=None)]))

    [result] = client.get("/api/search", params={"q": "x", "source": "arxiv"}).json()["results"]

    assert result["venue"] == "arXiv"
    assert result["doi"] is None


def test_arxiv_punctuation_only_query_returns_nothing_without_calling_arxiv(client, upstream):
    response = client.get("/api/search", params={"q": "???", "source": "arxiv"})

    assert response.status_code == 200
    assert response.json()["results"] == [] and response.json()["total"] == 0
    assert upstream.requests == []


def test_arxiv_rejected_query_is_reported(client, upstream):
    upstream.text(ARXIV_QUERY, arxiv_error_feed("incorrect id format for 1234"))

    response = client.get("/api/search", params={"q": "x", "source": "arxiv"})

    assert response.status_code == 400
    assert response.json()["detail"] == "arXiv rejected the query: incorrect id format for 1234"


def test_arxiv_rejection_without_a_reason_is_reported(client, upstream):
    error = "<entry><id>http://arxiv.org/api/errors#unknown</id><title>Error</title></entry>"
    upstream.text(ARXIV_QUERY, arxiv_feed([error], total=1))

    response = client.get("/api/search", params={"q": "x", "source": "arxiv"})

    assert (response.status_code, response.json()["detail"]) == (
        400, "arXiv rejected the query: arXiv rejected the query.")


@pytest.mark.parametrize(("reply", "status", "detail"), [
    (lambda r: httpx.Response(500), 502, "arXiv returned HTTP 500."),
    (lambda r: httpx.Response(200, text="<feed><entry>"), 502, "arXiv returned malformed XML."),
])
def test_arxiv_errors(client, upstream, reply, status, detail):
    upstream.get(ARXIV_QUERY, reply)

    response = client.get("/api/search", params={"q": "x", "source": "arxiv"})

    assert (response.status_code, response.json()["detail"]) == (status, detail)


def test_arxiv_rate_limit_pauses_further_calls(client, upstream):
    upstream.get(ARXIV_QUERY, lambda r: httpx.Response(503, headers={"Retry-After": "120"}))

    first = client.get("/api/search", params={"q": "transformers", "source": "arxiv"})
    second = client.get("/api/search", params={"q": "diffusion models", "source": "arxiv"})

    assert first.status_code == 429
    assert "paused for about 120 s" in first.json()["detail"]
    assert "Search OpenAlex meanwhile" in first.json()["detail"]
    assert second.status_code == 429  # answered from the cooldown...
    assert len(upstream.requests) == 1  # ...without calling arXiv again


@pytest.mark.parametrize(("retry_after", "pause"), [
    (None, 60),  # no header: a minute
    ("30", 60),  # at least a minute
    ("3600", 600),  # at most 10 minutes (README; INSTALL.md "up to 600 seconds")
    ("Wed, 04 Nov 2026 20:00:00 GMT", 60),  # a date instead of seconds: a minute
    ("soon", 60),
])
def test_arxiv_pause_lasts_one_to_ten_minutes_and_then_arxiv_is_asked_again(
        client, upstream, clock, retry_after, pause):
    headers = {"Retry-After": retry_after} if retry_after else {}
    upstream.get(ARXIV_QUERY, lambda r: httpx.Response(429, headers=headers))

    response = client.get("/api/search", params={"q": "first", "source": "arxiv"})

    assert response.status_code == 429
    assert f"paused for about {pause} s" in response.json()["detail"]
    upstream.text(ARXIV_QUERY, arxiv_feed([arxiv_entry()]))
    clock.advance(pause - 1)
    assert client.get("/api/search", params={"q": "second", "source": "arxiv"}).status_code == 429
    assert len(upstream.requests) == 1
    clock.advance(1)
    resumed = client.get("/api/search", params={"q": "third", "source": "arxiv"})
    assert resumed.status_code == 200 and len(resumed.json()["results"]) == 1
    assert len(upstream.requests) == 2


@pytest.mark.parametrize(("later", "sent_after"), [(1.0, 3.0), (2.5, 3.0), (5.0, 5.0)])
def test_arxiv_calls_are_spaced_3_seconds_apart(client, upstream, clock, later, sent_after):
    # README: "The app keeps 3 seconds between its arXiv calls." A search made sooner waits for
    # the rest of the 3 s; one made later does not wait at all.
    sent_at = []

    def feed(request):
        sent_at.append(clock.now)
        return httpx.Response(200, content=arxiv_feed([]))

    upstream.get(ARXIV_QUERY, feed)

    client.get("/api/search", params={"q": "first", "source": "arxiv"})
    clock.advance(later)
    client.get("/api/search", params={"q": "second", "source": "arxiv"})

    assert sent_at[1] - sent_at[0] == pytest.approx(sent_after)


def test_arxiv_connection_error_is_reported_without_a_pause(client, upstream):
    upstream.fail(ARXIV_QUERY, httpx.ConnectError, "[Errno 61] Connection refused")

    response = client.get("/api/search", params={"q": "x", "source": "arxiv"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Could not reach arXiv. Check your connection and try again."
    upstream.text(ARXIV_QUERY, arxiv_feed([]))
    assert client.get("/api/search", params={"q": "y", "source": "arxiv"}).status_code == 200
    assert len(upstream.requests) == 2


def test_the_pause_message_counts_down_to_the_last_second(client, upstream, clock):
    upstream.get(ARXIV_QUERY, lambda r: httpx.Response(429))
    client.get("/api/search", params={"q": "first", "source": "arxiv"})  # starts a 60 s pause

    clock.advance(30)
    halfway = client.get("/api/search", params={"q": "second", "source": "arxiv"})
    clock.advance(29.6)
    last_second = client.get("/api/search", params={"q": "third", "source": "arxiv"})

    assert "paused for about 30 s" in halfway.json()["detail"]
    assert "paused for about 1 s" in last_second.json()["detail"]
    assert len(upstream.requests) == 1


def test_arxiv_timeout_also_starts_a_cooldown(client, upstream):
    upstream.fail(ARXIV_QUERY, httpx.ReadTimeout)

    first = client.get("/api/search", params={"q": "x", "source": "arxiv"})
    second = client.get("/api/search", params={"q": "y", "source": "arxiv"})

    assert first.status_code == 504
    assert first.json()["detail"] == (
        "arXiv did not answer in time (it may be limiting requests). Try again in a minute, or search OpenAlex.")
    assert second.status_code == 429
    assert len(upstream.requests) == 1


def test_openalex_still_works_while_arxiv_is_paused(client, upstream):
    upstream.get(ARXIV_QUERY, lambda r: httpx.Response(429))
    upstream.json(OPENALEX_WORKS, openalex_page([openalex_work()]))

    assert client.get("/api/search", params={"q": "x", "source": "arxiv"}).status_code == 429
    response = client.get("/api/search", params={"q": "x", "source": "openalex"})

    assert response.status_code == 200 and len(response.json()["results"]) == 1


# --- Request validation ----------------------------------------------------------------


@pytest.mark.parametrize("params", [
    {},
    {"q": ""},
    {"q": "x" * 301},
    {"q": "x", "page": 0},
    {"q": "x", "page": 101},
    {"q": "x", "per_page": 0},
    {"q": "x", "per_page": 51},
    {"q": "x", "source": "google-scholar"},
    {"q": "x", "page": "two"},
])
def test_invalid_search_requests_are_rejected_before_calling_any_source(client, upstream, params):
    response = client.get("/api/search", params=params)

    assert response.status_code == 422
    assert upstream.requests == []


def test_blank_query_is_rejected(client, upstream):
    response = client.get("/api/search", params={"q": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "Search query must not be blank."
    assert upstream.requests == []


# --- Result cache ------------------------------------------------------------------------


def test_repeated_search_is_answered_from_the_cache(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([openalex_work()]))

    first = client.get("/api/search", params={"q": "graph neural networks"})
    second = client.get("/api/search", params={"q": "  graph   neural networks "})  # same words

    assert first.json() == second.json()
    assert len(upstream.requests) == 1


def test_cache_keeps_query_case_because_openalex_treats_AND_as_an_operator(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([]))

    client.get("/api/search", params={"q": "cats AND dogs"})
    client.get("/api/search", params={"q": "cats and dogs"})

    assert [r.url.params["search"] for r in upstream.requests] == ["cats AND dogs", "cats and dogs"]


def test_cache_separates_pages_page_sizes_and_sources(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([]))
    upstream.text(ARXIV_QUERY, arxiv_feed([]))

    for params in ({"q": "rag"}, {"q": "rag", "page": 2}, {"q": "rag", "per_page": 25},
                   {"q": "rag", "source": "arxiv"}):
        client.get("/api/search", params=params)

    assert len(upstream.requests) == 4


def test_cached_results_expire_after_10_minutes(client, upstream, clock):
    upstream.json(OPENALEX_WORKS, openalex_page([openalex_work()]))

    client.get("/api/search", params={"q": "rag"})
    clock.advance(599)
    client.get("/api/search", params={"q": "rag"})
    assert len(upstream.requests) == 1
    clock.advance(2)
    client.get("/api/search", params={"q": "rag"})

    assert len(upstream.requests) == 2


def test_the_cache_keeps_the_256_most_recently_used_searches(client, upstream):
    upstream.json(OPENALEX_WORKS, openalex_page([]))
    for n in range(256):
        client.get("/api/search", params={"q": f"topic {n}"})
    client.get("/api/search", params={"q": "topic 0"})  # used again: now the most recent

    client.get("/api/search", params={"q": "topic 256"})  # one more than fits: "topic 1" goes

    def sent_for(query: str) -> int:
        return sum(r.url.params["search"] == query for r in upstream.requests)

    client.get("/api/search", params={"q": "topic 0"})
    client.get("/api/search", params={"q": "topic 2"})
    assert (sent_for("topic 0"), sent_for("topic 2")) == (1, 1)  # still cached
    client.get("/api/search", params={"q": "topic 1"})
    assert sent_for("topic 1") == 2


def test_failed_searches_are_not_cached(client, upstream):
    upstream.get(OPENALEX_WORKS, lambda r: httpx.Response(500))
    assert client.get("/api/search", params={"q": "rag"}).status_code == 502

    upstream.json(OPENALEX_WORKS, openalex_page([openalex_work()]))
    response = client.get("/api/search", params={"q": "rag"})

    assert response.status_code == 200 and len(response.json()["results"]) == 1


# --- Parsing helpers ------------------------------------------------------------------------


def test_arxiv_query_builder():
    assert arxiv.build_query("???") is None
    assert arxiv.build_query("the of and") == 'ti:"the of and" OR abs:"the of and"'  # only stopwords
    assert arxiv.build_query("graph-based RAG!") == (
        'ti:"graph-based RAG" OR abs:"graph-based RAG" OR '
        "((ti:graph OR abs:graph) AND (ti:based OR abs:based) AND (ti:RAG OR abs:RAG))"
    )


def test_openalex_abstract_is_rebuilt_from_the_inverted_index():
    # Real abstracts repeat words: every position of a word is used.
    assert openalex.rebuild_abstract({"the": [0, 3], "cat": [1], "saw": [2], "dog": [4]}) == "the cat saw the dog"
    assert openalex.rebuild_abstract({"dog.": [5], "the": [0, 3], "cat": [1], "saw": [2], "big": [4]}) == (
        "the cat saw the big dog.")
    assert openalex.rebuild_abstract(None) is None
    assert openalex.rebuild_abstract({}) is None
