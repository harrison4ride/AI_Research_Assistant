"""F2: saving papers to the local library, browsing, editing, and deleting them.

Also covers papers opened from search without saving (kept for CACHED_PAPER_DAYS).
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text, update

import app.main as main_module
from app import config, db
from app.db import SessionLocal, engine
from app.main import app
from app.models import ChatMessage, Paper
from app.routers import papers as papers_router
from app.services import cache
from app.services.cache import prune_cached_papers
from support import pdfs, scratch
from support.papers import (
    ARXIV_META,
    BERT_META,
    OPENALEX_META,
    events,
    meta,
    open_unsaved,
    save,
    upload_sample,
)
from support.upstream import PUBLIC_IP


def library(client) -> list[dict]:
    response = client.get("/api/papers")
    assert response.status_code == 200
    return response.json()


def titles(papers: list[dict]) -> list[str]:
    return [p["title"] for p in papers]


def stored_paper_count() -> int:
    """Papers in the database, saved or only opened."""
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Paper))


# --- Saving search results -------------------------------------------------------------


def test_save_a_search_result(client):
    response = client.post("/api/papers", json=ARXIV_META)

    assert response.status_code == 201
    paper = response.json()
    for key, value in ARXIV_META.items():
        assert paper[key] == value
    assert isinstance(paper["id"], int)
    assert paper["in_library"] is True
    assert paper["saved_at"] is not None and paper["created_at"] is not None
    assert paper["has_pdf"] is False and paper["full_text_status"] is None
    assert library(client) == [paper]


def test_saved_paper_detail_has_no_summary_yet(client):
    paper = save(client, ARXIV_META)

    detail = client.get(f"/api/papers/{paper['id']}").json()

    assert detail["title"] == ARXIV_META["title"]
    assert detail["summary"] is None and detail["summary_model"] is None


def test_timestamps_are_utc_with_offset(client):
    paper = save(client, ARXIV_META)

    for key in ("created_at", "saved_at"):
        parsed = datetime.fromisoformat(paper[key])
        assert parsed.utcoffset() == timedelta(0)
        assert abs(datetime.now(timezone.utc) - parsed) < timedelta(minutes=1)


def test_saving_the_same_paper_twice_returns_the_existing_entry(client):
    first = client.post("/api/papers", json=ARXIV_META)
    second = client.post("/api/papers", json=ARXIV_META)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert len(library(client)) == 1


def test_same_paper_from_arxiv_and_openalex_is_saved_once(client):
    # arXiv's feed often has no <arxiv:doi>; only the arXiv id ties it to OpenAlex's arXiv DOI.
    from_arxiv = save(client, meta(ARXIV_META, doi=None))

    response = client.post("/api/papers", json=OPENALEX_META)  # DOI 10.48550/arxiv.1706.03762

    assert response.status_code == 200
    assert response.json()["id"] == from_arxiv["id"]
    assert [p["id"] for p in library(client)] == [from_arxiv["id"]]


def test_openalex_copy_of_an_arxiv_paper_matches_a_later_arxiv_save(client):
    from_openalex = save(client, OPENALEX_META)

    response = client.post("/api/papers", json=meta(ARXIV_META, doi=None))

    assert response.status_code == 200
    assert response.json()["id"] == from_openalex["id"]


@pytest.mark.parametrize(("stored", "sent"), [
    ("10.18653/V1/N19-1423", "10.18653/v1/n19-1423"),
    ("10.18653/v1/n19-1423", "10.18653/V1/N19-1423"),
])
def test_doi_match_ignores_case(client, stored, sent):
    first = save(client, meta(BERT_META, doi=stored))

    second = client.post("/api/papers", json=meta(BERT_META, external_id="W999", doi=sent))

    assert second.status_code == 200 and second.json()["id"] == first["id"]
    assert len(library(client)) == 1


def test_an_arxiv_doi_matches_only_its_own_arxiv_paper(client):
    bert_on_arxiv = save(client, meta(ARXIV_META, external_id="1810.04805", title=BERT_META["title"],
                                      authors=BERT_META["authors"], abstract=BERT_META["abstract"], doi=None))

    response = client.post("/api/papers", json=OPENALEX_META)  # DOI 10.48550/arxiv.1706.03762: another paper

    assert response.status_code == 201 and response.json()["id"] != bert_on_arxiv["id"]
    assert len(library(client)) == 2


def test_different_papers_from_the_same_source_get_separate_entries(client):
    first = client.post("/api/papers", json=OPENALEX_META)
    second = client.post("/api/papers", json=BERT_META)  # also from OpenAlex

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert sorted(titles(library(client))) == sorted([OPENALEX_META["title"], BERT_META["title"]])


SAVE_AND_OPEN = pytest.mark.parametrize("endpoint", ["/api/papers", "/api/papers/open"], ids=["save", "open"])


@SAVE_AND_OPEN
def test_the_same_result_without_a_doi_is_kept_once(client, endpoint):
    # Many OpenAlex works have no DOI: the source and its id still identify them.
    result = meta(BERT_META, doi=None)

    first = client.post(endpoint, json=result)
    second = client.post(endpoint, json=result)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert stored_paper_count() == 1


@SAVE_AND_OPEN
def test_a_result_that_another_request_stores_at_the_same_moment_is_not_stored_twice(client, endpoint, monkeypatch):
    # E.g. a double click: both requests look for the paper before either has stored it.
    find_duplicate = papers_router.find_duplicate
    other_request = {}

    def the_other_request_stores_it_first(result, db):
        if not other_request:  # not there yet when this request looks, but stored right after
            with SessionLocal() as session:
                paper = Paper(**result.model_dump(), in_library=endpoint == "/api/papers")
                session.add(paper)
                session.commit()
                other_request["id"] = paper.id
            return None
        return find_duplicate(result, db)

    monkeypatch.setattr(papers_router, "find_duplicate", the_other_request_stores_it_first)

    response = client.post(endpoint, json=BERT_META)

    assert response.status_code == 200 and response.json()["id"] == other_request["id"]
    assert response.json()["in_library"] is (endpoint == "/api/papers")
    assert stored_paper_count() == 1


@SAVE_AND_OPEN
@pytest.mark.parametrize(("body", "detail"), [
    (meta(ARXIV_META, source="upload"), "Use the upload endpoint to add PDF files."),
    (meta(ARXIV_META, external_id=None), "external_id is required for a search result."),
    (meta(ARXIV_META, external_id=""), "external_id is required for a search result."),
])
def test_invalid_search_results_are_rejected(client, endpoint, body, detail):
    response = client.post(endpoint, json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == detail
    assert stored_paper_count() == 0


@SAVE_AND_OPEN
@pytest.mark.parametrize("body", [
    {k: v for k, v in ARXIV_META.items() if k != "title"},
    meta(ARXIV_META, source="semantic-scholar"),
    meta(ARXIV_META, year="recent"),
    meta(ARXIV_META, authors="Ashish Vaswani"),
])
def test_malformed_paper_metadata_is_rejected(client, endpoint, body):
    assert client.post(endpoint, json=body).status_code == 422
    assert stored_paper_count() == 0


def test_saved_keys_let_the_search_page_mark_saved_results(client):
    saved = save(client, ARXIV_META)
    open_unsaved(client, BERT_META)  # opened only: not saved

    keys = client.get("/api/papers/keys").json()

    assert keys == [{"source": "arxiv", "external_id": "1706.03762", "id": saved["id"]}]


# --- Opening a search result without saving it ----------------------------------------


def test_open_without_saving(client):
    response = client.post("/api/papers/open", json=BERT_META)

    assert response.status_code == 201
    paper = response.json()
    assert paper["in_library"] is False and paper["saved_at"] is None
    assert library(client) == []
    detail = client.get(f"/api/papers/{paper['id']}")
    assert detail.status_code == 200 and detail.json()["in_library"] is False


def test_opening_again_returns_the_same_entry(client):
    first = open_unsaved(client, BERT_META)

    response = client.post("/api/papers/open", json=BERT_META)

    assert response.status_code == 200
    assert response.json()["id"] == first["id"]


def test_opening_a_saved_paper_keeps_it_in_the_library(client):
    saved = save(client, BERT_META)

    opened = open_unsaved(client, BERT_META)

    assert opened["id"] == saved["id"] and opened["in_library"] is True
    assert len(library(client)) == 1


def test_save_an_opened_paper_from_the_reader(client):
    opened = open_unsaved(client, BERT_META)

    response = client.post(f"/api/papers/{opened['id']}/save")

    assert response.status_code == 200
    assert response.json()["in_library"] is True and response.json()["saved_at"] is not None
    assert [p["id"] for p in library(client)] == [opened["id"]]


def test_saving_an_opened_paper_from_search_keeps_its_id_and_conversation(client):
    opened = open_unsaved(client, BERT_META)
    with SessionLocal() as db:
        db.add(ChatMessage(paper_id=opened["id"], role="user", content="What is BERT?"))
        db.commit()

    response = client.post("/api/papers", json=BERT_META)

    assert response.status_code == 200 and response.json()["id"] == opened["id"]
    assert response.json()["in_library"] is True
    assert [m["content"] for m in client.get(f"/api/papers/{opened['id']}/chat").json()] == ["What is BERT?"]


def test_save_unknown_paper(client):
    response = client.post("/api/papers/999999/save")
    assert response.status_code == 404
    assert response.json()["detail"] == "Paper not found."


# --- Browsing ------------------------------------------------------------------------------


def test_library_lists_most_recently_saved_first(client):
    opened_early = open_unsaved(client, BERT_META)
    save(client, ARXIV_META)
    client.post(f"/api/papers/{opened_early['id']}/save")  # saved last, though created first

    assert titles(library(client)) == [BERT_META["title"], ARXIV_META["title"]]


def test_unknown_paper_is_404(client):
    response = client.get("/api/papers/424242")
    assert response.status_code == 404
    assert response.json()["detail"] == "Paper not found."


@pytest.mark.parametrize("paper_id", ["abc", "1.5"])
def test_non_numeric_paper_id_is_rejected(client, paper_id):
    assert client.get(f"/api/papers/{paper_id}").status_code == 422


@pytest.mark.parametrize(("query", "expected"), [
    ("attention", ["Attention Is All You Need"]),  # title
    ("ATTENTION", ["Attention Is All You Need"]),  # case-insensitive
    ("devlin", ["BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"]),  # author
    ("convolutional", ["Attention Is All You Need"]),  # abstract
    ("müller", ["Über Graphen"]),  # non-ASCII author
    ("ÜBER", ["Über Graphen"]),  # non-ASCII case folding
    ("efficient", ["Eﬃcient Graph Kernels"]),  # ligature in the title
    ("x", ["Attention Is All You Need"]),  # a first letter: only in that abstract ("complex")
    ("no such words", []),
])
def test_filter_matches_title_author_and_abstract(client, query, expected):
    save(client, ARXIV_META)
    save(client, BERT_META)
    save(client, meta(BERT_META, external_id="W1", doi=None, title="Über Graphen", authors=["Jürgen Müller"],
                      abstract=None))
    save(client, meta(BERT_META, external_id="W2", doi=None, title="Eﬃcient Graph Kernels", authors=[],
                      abstract=None))

    response = client.get("/api/papers", params={"q": query})

    assert response.status_code == 200
    assert titles(response.json()) == expected


def test_blank_filter_lists_everything(client):
    save(client, ARXIV_META)
    save(client, BERT_META)

    assert len(client.get("/api/papers", params={"q": "   "}).json()) == 2


def test_filter_is_limited_to_200_characters_like_the_filter_box(client):
    # The library page's filter box has maxLength={200}.
    save(client, meta(BERT_META, title="x" * 200))

    longest = client.get("/api/papers", params={"q": "x" * 200})

    assert longest.status_code == 200 and titles(longest.json()) == ["x" * 200]
    assert client.get("/api/papers", params={"q": "x" * 201}).status_code == 422


def test_unsaved_papers_are_not_listed_or_found_by_the_filter(client):
    open_unsaved(client, BERT_META)

    assert client.get("/api/papers", params={"q": "bert"}).json() == []


def test_library_survives_a_restart():
    with TestClient(app) as first_run:
        saved = save(first_run, ARXIV_META)
    # Close every database connection, so the next run must read the database file again.
    engine.dispose()

    with TestClient(app) as second_run:
        papers = second_run.get("/api/papers").json()

    assert papers == [saved]


# --- Editing metadata ------------------------------------------------------------------------


def test_edit_all_metadata_fields(client):
    paper = save(client, ARXIV_META)
    changes = {"title": "Attention Is All You Need (NeurIPS version)", "authors": ["A. Vaswani", "N. Shazeer"],
               "year": 2018, "abstract": "Edited abstract."}

    response = client.patch(f"/api/papers/{paper['id']}", json=changes)

    assert response.status_code == 200
    for key, value in changes.items():
        assert response.json()[key] == value
    assert client.get(f"/api/papers/{paper['id']}").json()["title"] == changes["title"]


@pytest.mark.parametrize("change", [
    {"title": "A corrected title"}, {"authors": ["A. Vaswani"]}, {"year": 2016}, {"abstract": "A corrected abstract."},
])
def test_partial_edit_leaves_other_fields_alone(client, change):
    paper = save(client, ARXIV_META)

    response = client.patch(f"/api/papers/{paper['id']}", json=change)

    assert response.status_code == 200
    stored = client.get(f"/api/papers/{paper['id']}").json()
    assert {key: stored[key] for key in ARXIV_META} == {**ARXIV_META, **change}


def test_edit_trims_values_and_drops_blank_authors(client):
    paper = save(client, ARXIV_META)

    updated = client.patch(f"/api/papers/{paper['id']}",
                           json={"title": "  Trimmed  ", "authors": ["  Alice ", "", "   ", "Bob"]}).json()

    assert updated["title"] == "Trimmed"
    assert updated["authors"] == ["Alice", "Bob"]


def test_clearing_authors_with_null_keeps_the_library_working(client):
    paper = save(client, ARXIV_META)

    response = client.patch(f"/api/papers/{paper['id']}", json={"authors": None})

    assert response.status_code == 200 and response.json()["authors"] == []
    assert library(client)[0]["authors"] == []


def test_clearing_year_and_abstract(client):
    paper = save(client, ARXIV_META)

    updated = client.patch(f"/api/papers/{paper['id']}", json={"year": None, "abstract": None}).json()

    assert updated["year"] is None and updated["abstract"] is None


@pytest.mark.parametrize("changes", [
    {"title": "   "},
    {"title": ""},
    {"title": None},
    {"title": "x" * 501},
    {"year": 999},
    {"year": 2101},
    {"abstract": "x" * 20001},
])
def test_invalid_edits_are_rejected(client, changes):
    paper = save(client, ARXIV_META)

    response = client.patch(f"/api/papers/{paper['id']}", json=changes)

    assert response.status_code == 422
    stored = client.get(f"/api/papers/{paper['id']}").json()
    assert {key: stored[key] for key in changes} == {key: ARXIV_META[key] for key in changes}


@pytest.mark.parametrize("changes", [
    {"title": "x" * 500},  # the edit form's maxLength
    {"year": 1000},  # the edit form's min and max
    {"year": 2100},
    {"abstract": "x" * 20000},
    # Large collaborations list thousands of authors; the form sends the full list.
    {"authors": [f"Author {n}" for n in range(10000)]},
])
def test_the_largest_edits_the_form_allows_are_accepted(client, changes):
    paper = save(client, ARXIV_META)

    response = client.patch(f"/api/papers/{paper['id']}", json=changes)

    assert response.status_code == 200
    stored = client.get(f"/api/papers/{paper['id']}").json()
    assert {key: stored[key] for key in changes} == changes


def test_edit_unknown_paper(client):
    assert client.patch("/api/papers/999999", json={"title": "x"}).status_code == 404


# --- Deleting ------------------------------------------------------------------------------------


def test_delete_a_paper(client):
    paper = save(client, ARXIV_META)

    response = client.delete(f"/api/papers/{paper['id']}")

    assert response.status_code == 204 and response.content == b""
    assert client.get(f"/api/papers/{paper['id']}").status_code == 404
    assert library(client) == []


def test_delete_unknown_paper(client):
    assert client.delete("/api/papers/999999").status_code == 404


def _add_conversation(paper_id: int, question: str, answer: str) -> None:
    with SessionLocal() as session:
        session.add_all([ChatMessage(paper_id=paper_id, role="user", content=question),
                         ChatMessage(paper_id=paper_id, role="assistant", content=answer)])
        session.commit()


def _conversations() -> dict[int, list[str]]:
    with SessionLocal() as session:
        rows = session.execute(select(ChatMessage.paper_id, ChatMessage.content).order_by(ChatMessage.id))
        found: dict[int, list[str]] = {}
        for paper_id, content in rows:
            found.setdefault(paper_id, []).append(content)
        return found


def test_deleting_a_paper_deletes_its_conversation_only(client):
    paper = save(client, ARXIV_META)
    other = save(client, BERT_META)
    _add_conversation(paper["id"], "Q", "A")
    _add_conversation(other["id"], "About BERT?", "It is an encoder.")

    client.delete(f"/api/papers/{paper['id']}")

    assert _conversations() == {other["id"]: ["About BERT?", "It is an encoder."]}


def test_deleting_a_paper_removes_its_stored_pdf(client, settings):
    paper = upload_sample(client)
    [stored] = list(settings.pdf_dir.iterdir())

    client.delete(f"/api/papers/{paper['id']}")

    assert not stored.exists()


def test_a_paper_whose_stored_pdf_is_already_gone_can_be_deleted(client, fake_llm, settings):
    paper = upload_sample(client)
    for stored in settings.pdf_dir.iterdir():
        stored.unlink()  # e.g. removed by hand from DATA_DIR

    response = client.delete(f"/api/papers/{paper['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/papers/{paper['id']}").status_code == 404


def test_a_pdf_shared_by_two_entries_is_kept_until_both_are_deleted(client, settings):
    uploaded = upload_sample(client)
    search_result = save(client, BERT_META)
    attach = client.post(f"/api/papers/{search_result['id']}/pdf",
                         files={"file": ("same.pdf", pdfs.sample_pdf(), "application/pdf")})
    assert attach.status_code == 200
    [stored] = list(settings.pdf_dir.iterdir())  # stored once, by content hash

    client.delete(f"/api/papers/{uploaded['id']}")
    assert stored.exists()
    assert client.get(f"/api/papers/{search_result['id']}/pdf").content == pdfs.sample_pdf()

    client.delete(f"/api/papers/{search_result['id']}")
    assert not stored.exists()


def test_deleted_ids_are_never_reused(client):
    first = save(client, ARXIV_META)
    client.delete(f"/api/papers/{first['id']}")

    second = save(client, BERT_META)

    assert second["id"] > first["id"]


# --- Pruning papers that were opened but never saved -----------------------------------------


def _add_paper(external_id: str, *, in_library: bool, last_opened_days_ago: float, pdf_path: str | None = None) -> int:
    opened = datetime.now(timezone.utc) - timedelta(days=last_opened_days_ago)
    with SessionLocal() as db:
        paper = Paper(source="openalex", external_id=external_id, title=f"Paper {external_id}", authors=[],
                      in_library=in_library, saved_at=opened if in_library else None,
                      last_opened_at=opened, created_at=opened, pdf_path=pdf_path)
        db.add(paper)
        db.commit()
        return paper.id


def _existing_ids() -> set[int]:
    with SessionLocal() as db:
        return set(db.scalars(select(Paper.id)))


def test_unsaved_papers_not_opened_for_a_week_are_deleted():
    stale = _add_paper("W1", in_library=False, last_opened_days_ago=8)
    recent = _add_paper("W2", in_library=False, last_opened_days_ago=6)
    saved_long_ago = _add_paper("W3", in_library=True, last_opened_days_ago=400)
    _add_conversation(stale, "Q", "A")
    _add_conversation(recent, "Recent question?", "Recent answer.")

    assert prune_cached_papers() == 1

    assert _existing_ids() == {recent, saved_long_ago}
    assert _conversations() == {recent: ["Recent question?", "Recent answer."]}


def _stored_pdf(settings, name: str) -> Path:
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = settings.pdf_dir / name
    pdf_file.write_bytes(pdfs.sample_pdf())
    return pdf_file


def test_pruning_removes_every_stale_paper_with_its_own_pdf(settings):
    first_pdf, second_pdf = _stored_pdf(settings, "a.pdf"), _stored_pdf(settings, "b.pdf")
    _add_paper("W1", in_library=False, last_opened_days_ago=9, pdf_path="a.pdf")
    _add_paper("W2", in_library=False, last_opened_days_ago=20, pdf_path="b.pdf")

    assert prune_cached_papers() == 2

    assert _existing_ids() == set()
    assert not first_pdf.exists() and not second_pdf.exists()


@pytest.fixture
def local_time_far_from_utc():
    """The machine's local time zone set to UTC-10 (Hawaii) for the test."""
    original = os.environ.get("TZ")
    os.environ["TZ"] = "HST10"
    time.tzset()
    yield
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


def test_unsaved_papers_are_pruned_after_the_set_days_in_any_local_time_zone(local_time_far_from_utc):
    # Times are stored in UTC, so the machine's time zone must not move the cutoff.
    kept = _add_paper("W1", in_library=False, last_opened_days_ago=7 - 2 / 24)  # 2 hours short of a week
    _add_paper("W2", in_library=False, last_opened_days_ago=7 + 2 / 24)  # 2 hours past it

    assert prune_cached_papers() == 1
    assert _existing_ids() == {kept}


def test_pruning_removes_the_pdf_of_a_deleted_paper(settings):
    pdf_file = _stored_pdf(settings, "abc.pdf")
    _add_paper("W1", in_library=False, last_opened_days_ago=30, pdf_path="abc.pdf")

    prune_cached_papers()

    assert not pdf_file.exists()


def test_pruning_keeps_a_pdf_that_another_paper_still_uses(settings):
    # PDFs are stored by content hash, so a library paper may share the file.
    pdf_file = _stored_pdf(settings, "shared.pdf")
    _add_paper("W1", in_library=False, last_opened_days_ago=30, pdf_path="shared.pdf")
    kept = _add_paper("W2", in_library=True, last_opened_days_ago=30, pdf_path="shared.pdf")

    assert prune_cached_papers() == 1

    assert _existing_ids() == {kept}
    assert pdf_file.exists()


@pytest.mark.parametrize("users_change", [
    {"in_library": True, "saved_at": datetime.now(timezone.utc)},  # saved to the library
    {"last_opened_at": datetime.now(timezone.utc)},  # opened again in the reader
], ids=["saved", "reopened"])
def test_a_paper_saved_or_reopened_while_pruning_runs_is_kept(settings, monkeypatch, users_change):
    pdf_file = _stored_pdf(settings, "busy.pdf")
    paper_id = _add_paper("W1", in_library=False, last_opened_days_ago=10, pdf_path="busy.pdf")
    real_delete = cache.delete

    def delete_after_the_user_acted(table):
        # The user acts after the stale papers were selected, before they are deleted.
        with SessionLocal() as other:
            other.execute(update(Paper).where(Paper.id == paper_id).values(**users_change))
            other.commit()
        return real_delete(table)

    monkeypatch.setattr(cache, "delete", delete_after_the_user_acted)

    assert prune_cached_papers() == 0
    assert _existing_ids() == {paper_id}
    assert pdf_file.exists()


async def test_unsaved_papers_are_also_pruned_every_12_hours(monkeypatch, caplog):
    waits, runs = [], []

    async def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 4:
            raise asyncio.CancelledError  # the app shuts down

    def prune():
        runs.append(len(waits))
        if len(runs) == 1:
            raise RuntimeError("database is locked")

    async def to_thread(function):
        return function()

    monkeypatch.setattr(main_module, "asyncio", SimpleNamespace(sleep=sleep, to_thread=to_thread))
    monkeypatch.setattr(main_module, "prune_cached_papers", prune)

    with pytest.raises(asyncio.CancelledError):
        await main_module._prune_periodically()

    assert waits == [12 * 3600] * 4
    assert runs == [1, 2, 3]  # one run after each wait: a failed run does not stop the cleanup
    assert "Pruning unsaved papers failed" in caplog.text


def test_pruning_follows_the_cached_paper_days_setting(settings, monkeypatch):
    monkeypatch.setattr(settings, "cached_paper_days", 30)
    kept = _add_paper("W1", in_library=False, last_opened_days_ago=8)

    assert prune_cached_papers() == 0
    assert _existing_ids() == {kept}


def test_stale_unsaved_papers_are_pruned_when_the_app_starts():
    stale = _add_paper("W1", in_library=False, last_opened_days_ago=10)

    with TestClient(app) as started:
        assert started.get(f"/api/papers/{stale}").status_code == 404


def test_opening_an_unsaved_paper_postpones_its_deletion(client):
    paper_id = _add_paper("W1", in_library=False, last_opened_days_ago=8)

    assert client.get(f"/api/papers/{paper_id}").status_code == 200

    assert prune_cached_papers() == 0
    assert paper_id in _existing_ids()


def test_opening_a_search_result_again_postpones_its_deletion(client):
    opened = open_unsaved(client, BERT_META)
    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
    with SessionLocal() as session:
        session.execute(update(Paper).where(Paper.id == opened["id"])
                        .values(created_at=eight_days_ago, last_opened_at=eight_days_ago))
        session.commit()

    assert client.post("/api/papers/open", json=BERT_META).json()["id"] == opened["id"]

    assert prune_cached_papers() == 0
    assert _existing_ids() == {opened["id"]}


# --- Saving a paper that was only opened keeps what was made for it ---------------------------

PDF_URL = "https://papers.example.org/bert.pdf"


def _summaries_for_every_heading(call) -> str:
    headings = json.loads(call.prompt.split("<headings>\n", 1)[1].split("\n</headings>", 1)[0])
    return json.dumps({"summaries": [{"n": h["n"], "summary": f"About {h['heading']}."} for h in headings]})


@pytest.mark.parametrize("save_from", ["reader", "search page"])
def test_saving_an_opened_paper_keeps_its_summary_section_summaries_and_conversation(
        client, fake_llm, upstream, dns, save_from):
    # README: "If you save it later, it keeps its summary, section summaries, and conversation."
    dns["papers.example.org"] = PUBLIC_IP
    upstream.get(PDF_URL, lambda request: httpx.Response(200, content=pdfs.sample_pdf()))
    search_result = meta(BERT_META, pdf_url=PDF_URL)
    paper_id = open_unsaved(client, search_result)["id"]
    fake_llm.reply_with(_summaries_for_every_heading)
    assert client.post(f"/api/papers/{paper_id}/outline/summaries", json={}).status_code == 200
    fake_llm.reply("The saved summary.")
    events(client.post(f"/api/papers/{paper_id}/summary"))
    fake_llm.reply("The saved answer.")
    events(client.post(f"/api/papers/{paper_id}/chat", json={"question": "What is new?"}))

    if save_from == "reader":
        response = client.post(f"/api/papers/{paper_id}/save")
    else:
        response = client.post("/api/papers", json=search_result)

    assert response.status_code == 200 and response.json()["id"] == paper_id
    assert [p["id"] for p in library(client)] == [paper_id]
    assert client.get(f"/api/papers/{paper_id}").json()["summary"] == "The saved summary."
    outline = client.get(f"/api/papers/{paper_id}/outline").json()
    assert outline["summarized"] is True
    assert [s["summary"] for s in outline["sections"]] == [f"About {s['title']}." for s in outline["sections"]]
    assert [m["content"] for m in client.get(f"/api/papers/{paper_id}/chat").json()] == [
        "What is new?", "The saved answer."]
    assert len(upstream.requests) == 1  # the PDF was downloaded once, while the paper was unsaved


# --- Upgrading an older database ------------------------------------------------------------------

# The papers table as the first library milestone (M2) created it.
M2_PAPERS_TABLE = """
CREATE TABLE papers (
    id INTEGER NOT NULL PRIMARY KEY, source VARCHAR(20) NOT NULL, external_id VARCHAR(200),
    title TEXT NOT NULL, authors JSON NOT NULL, year INTEGER, abstract TEXT, url TEXT, pdf_url TEXT,
    venue TEXT, doi VARCHAR(200), created_at DATETIME NOT NULL,
    CONSTRAINT uq_paper_source_external_id UNIQUE (source, external_id)
)"""


@pytest.fixture
def older_database(tmp_path, monkeypatch):
    """Start the app on a database file made by an older version, instead of the test database.

    The app's own engine opens its connections on that file, so every part of the app uses
    it: the requests, the pruning at startup (services/cache.py), and the summary and chat
    saves (routers/assistant.py), which hold SessionLocal rather than db.engine.
    """
    path = tmp_path / "app.db"
    test_database = scratch.database()
    engine.dispose()
    scratch.connect_engine_to(engine, path)
    monkeypatch.setattr(db, "DB_PATH", path)
    yield engine
    engine.dispose()
    scratch.connect_engine_to(engine, test_database)


def _papers_in_the_test_database() -> int:
    test_database = create_engine(f"sqlite:///{config.get_settings().data_dir / 'app.db'}")
    try:
        with test_database.connect() as conn:
            return conn.execute(text("SELECT count(*) FROM papers")).scalar_one()
    finally:
        test_database.dispose()


def test_an_older_database_is_upgraded_and_keeps_its_papers(older_database, fake_llm):
    # Saved a month ago, long before the unsaved-paper cutoff (CACHED_PAPER_DAYS).
    created = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0)
    with older_database.begin() as conn:
        conn.execute(text(M2_PAPERS_TABLE))
        conn.execute(text(
            "INSERT INTO papers (id, source, external_id, title, authors, year, abstract, url, pdf_url, venue, doi, "
            "created_at) VALUES (1, 'arxiv', '1706.03762', 'Attention Is All You Need', '[\"Ashish Vaswani\"]', "
            "2017, 'The abstract.', NULL, NULL, 'arXiv', NULL, :created)"),
            {"created": created.strftime("%Y-%m-%d %H:%M:%S.%f")})

    with TestClient(app) as started:  # startup runs init_db(), then prunes unsaved papers
        papers = started.get("/api/papers").json()
        chat = started.get("/api/papers/1/chat")
        answer = events(started.post("/api/papers/1/chat", json={"question": "What is new?"}))

    columns = {c["name"] for c in inspect(older_database).get_columns("papers")}
    assert {"pdf_path", "full_text", "summary", "in_library", "saved_at", "last_opened_at", "outline"} <= columns
    # Papers saved before the reader existed are library papers, saved when they were created,
    # so the pruning at startup kept them, old as they are.
    [paper] = papers
    assert (paper["id"], paper["title"], paper["in_library"]) == (1, "Attention Is All You Need", True)
    assert paper["saved_at"] == paper["created_at"] == created.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert (chat.status_code, chat.json()) == (200, [])  # the newer chat table was created
    # Questions work on the upgraded database, and their answers are saved in it.
    assert answer[0]["context"] == "abstract" and answer[-1]["type"] == "done"
    assert _conversations() == {1: ["What is new?", "This is a fake answer."]}

    # Later the user opens a paper from search and leaves it unsaved: once it has not been
    # opened for longer than CACHED_PAPER_DAYS, the next start removes it from this database.
    stale = _add_paper("W1", in_library=False, last_opened_days_ago=8)
    with TestClient(app):
        pass

    assert _existing_ids() == {1} and stale != 1
    assert _papers_in_the_test_database() == 0  # nothing of this went to the test database


def test_an_older_database_missing_a_required_column_stops_the_app_with_a_clear_error(older_database):
    with older_database.begin() as conn:
        conn.execute(text(M2_PAPERS_TABLE.replace("title TEXT NOT NULL, ", "")))

    with pytest.raises(RuntimeError) as raised:
        db.init_db()

    assert str(raised.value) == (
        f"Database schema is out of date: cannot add required column papers.title. "
        f"Delete {db.DB_PATH} to recreate it.")
