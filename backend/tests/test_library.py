"""F2: saving papers to the local library, browsing, editing, and deleting them.

Also covers papers opened from search without saving (kept for CACHED_PAPER_DAYS).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import ChatMessage, Paper
from app.services.cache import prune_cached_papers
from support import pdfs
from support.papers import (
    ARXIV_META,
    BERT_META,
    OPENALEX_META,
    meta,
    open_unsaved,
    save,
    upload_sample,
)


def library(client) -> list[dict]:
    response = client.get("/api/papers")
    assert response.status_code == 200
    return response.json()


def titles(papers: list[dict]) -> list[str]:
    return [p["title"] for p in papers]


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
    from_arxiv = save(client, ARXIV_META)

    response = client.post("/api/papers", json=OPENALEX_META)  # DOI 10.48550/arxiv.1706.03762

    assert response.status_code == 200
    assert response.json()["id"] == from_arxiv["id"]
    assert len(library(client)) == 1


def test_openalex_copy_of_an_arxiv_paper_matches_a_later_arxiv_save(client):
    from_openalex = save(client, OPENALEX_META)

    response = client.post("/api/papers", json=meta(ARXIV_META, doi=None))

    assert response.status_code == 200
    assert response.json()["id"] == from_openalex["id"]


def test_doi_match_ignores_case(client):
    first = save(client, meta(BERT_META, doi="10.18653/V1/N19-1423"))

    second = client.post("/api/papers", json=meta(BERT_META, external_id="W999", doi="10.18653/v1/n19-1423"))

    assert second.status_code == 200 and second.json()["id"] == first["id"]


def test_different_papers_get_separate_entries(client):
    save(client, ARXIV_META)
    save(client, BERT_META)

    assert len(library(client)) == 2


@pytest.mark.parametrize(("body", "detail"), [
    (meta(ARXIV_META, source="upload"), "Use the upload endpoint to add PDF files."),
    (meta(ARXIV_META, external_id=None), "external_id is required for a search result."),
    (meta(ARXIV_META, external_id=""), "external_id is required for a search result."),
])
def test_invalid_search_results_are_rejected(client, body, detail):
    response = client.post("/api/papers", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == detail
    assert library(client) == []


@pytest.mark.parametrize("body", [
    {k: v for k, v in ARXIV_META.items() if k != "title"},
    meta(ARXIV_META, source="semantic-scholar"),
    meta(ARXIV_META, year="recent"),
    meta(ARXIV_META, authors="Ashish Vaswani"),
])
def test_malformed_paper_metadata_is_rejected(client, body):
    assert client.post("/api/papers", json=body).status_code == 422
    assert library(client) == []


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


def test_filter_longer_than_200_characters_is_rejected(client):
    assert client.get("/api/papers", params={"q": "x" * 201}).status_code == 422


def test_unsaved_papers_are_not_listed_or_found_by_the_filter(client):
    open_unsaved(client, BERT_META)

    assert client.get("/api/papers", params={"q": "bert"}).json() == []


def test_library_survives_a_restart(client):
    saved = save(client, ARXIV_META)
    client.__exit__(None, None, None)  # stop the app (runs its shutdown)

    with TestClient(app) as restarted:
        papers = restarted.get("/api/papers").json()

    assert [p["id"] for p in papers] == [saved["id"]]


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


def test_partial_edit_leaves_other_fields_alone(client):
    paper = save(client, ARXIV_META)

    updated = client.patch(f"/api/papers/{paper['id']}", json={"year": 2016}).json()

    assert updated["year"] == 2016
    assert updated["title"] == ARXIV_META["title"] and updated["authors"] == ARXIV_META["authors"]


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
    assert client.get(f"/api/papers/{paper['id']}").json()["title"] == ARXIV_META["title"]


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


def test_deleting_a_paper_deletes_its_conversation(client):
    paper = save(client, ARXIV_META)
    with SessionLocal() as db:
        db.add_all([ChatMessage(paper_id=paper["id"], role="user", content="Q"),
                    ChatMessage(paper_id=paper["id"], role="assistant", content="A")])
        db.commit()

    client.delete(f"/api/papers/{paper['id']}")

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0


def test_deleting_a_paper_removes_its_stored_pdf(client, settings):
    paper = upload_sample(client)
    [stored] = list(settings.pdf_dir.iterdir())

    client.delete(f"/api/papers/{paper['id']}")

    assert not stored.exists()


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
    with SessionLocal() as db:
        db.add(ChatMessage(paper_id=stale, role="user", content="Q"))
        db.commit()

    assert prune_cached_papers() == 1

    assert _existing_ids() == {recent, saved_long_ago}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0


def test_pruning_removes_the_pdf_of_a_deleted_paper(settings):
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = settings.pdf_dir / "abc.pdf"
    pdf_file.write_bytes(pdfs.sample_pdf())
    _add_paper("W1", in_library=False, last_opened_days_ago=30, pdf_path="abc.pdf")

    prune_cached_papers()

    assert not pdf_file.exists()


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
