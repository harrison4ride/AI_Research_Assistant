"""F3: uploading PDFs, extracting their text and metadata, and attaching PDFs to papers.

Metadata comes from arXiv (when page 1 carries a verified arXiv id), else from the LLM
(faked here with `fake_llm.metadata`), else from layout heuristics.
"""

import hashlib

import httpx
import pytest

from app.db import SessionLocal
from app.models import Paper
from app.services import fulltext
from app.services.llm import ExtractedMetadata
from support import pdfs
from support.known_bugs import fails_until_fixed, known_bug
from support.papers import BERT_META, save, upload, upload_sample
from support.upstream import ARXIV_QUERY, arxiv_entry, arxiv_feed

LONG_ABSTRACT = (
    "This abstract was read by the language model. It is long enough to be trusted, because "
    "abstracts shorter than one hundred characters are ignored."
)


def stored_files(settings) -> list:
    return sorted(settings.pdf_dir.iterdir()) if settings.pdf_dir.exists() else []


# --- Successful uploads ---------------------------------------------------------------------


def test_upload_extracts_metadata_from_the_pdf_layout(client, fake_llm):
    data = pdfs.sample_pdf()

    response = upload(client, data, name="retrieval.pdf")

    assert response.status_code == 201
    paper = response.json()
    assert paper["source"] == "upload"
    assert paper["title"] == pdfs.SAMPLE_TITLE
    assert paper["authors"] == pdfs.SAMPLE_AUTHORS
    assert paper["year"] == pdfs.SAMPLE_YEAR  # the venue year, not the cited 2020
    assert paper["abstract"] == pdfs.SAMPLE_ABSTRACT
    assert paper["external_id"] == hashlib.sha256(data).hexdigest()
    assert paper["in_library"] is True and paper["saved_at"] is not None
    assert paper["has_pdf"] is True and paper["page_count"] == 2
    assert paper["full_text_status"] == "ok"
    assert [p["id"] for p in client.get("/api/papers").json()] == [paper["id"]]


def test_upload_asks_the_llm_with_the_text_of_the_first_pages_only(client, fake_llm):
    # README: "the first pages go to Anthropic for metadata extraction". The app sends at most
    # the first 15,000 characters of the text.
    last_line = "This closing sentence is on the last page only."
    data = pdfs.long_paper_pdf(extra_pages=10, last_line=last_line)  # about 40,000 characters

    paper = upload(client, data).json()

    [first_pages] = fake_llm.metadata_requests
    with SessionLocal() as session:
        full_text = session.get(Paper, paper["id"]).full_text
    assert last_line in full_text and paper["page_count"] == 11 and len(full_text) > 30_000
    assert full_text.startswith(first_pages)  # the beginning of the paper, unchanged
    assert len(first_pages) <= 15_000
    assert pdfs.SAMPLE_ABSTRACT[:60] in first_pages
    assert pdfs.LONG_FILLER[:60] in first_pages  # pages, not only page 1
    assert last_line not in first_pages


def test_uploaded_pdf_is_stored_and_served_back(client, fake_llm, settings):
    paper = upload_sample(client)

    response = client.get(f"/api/papers/{paper['id']}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    # No "attachment" disposition, so browsers show the PDF instead of downloading it.
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert response.content == pdfs.sample_pdf()
    assert [f.name for f in stored_files(settings)] == [f"{paper['external_id']}.pdf"]


def test_uploading_the_same_file_twice_returns_the_existing_entry(client, fake_llm):
    first = upload(client)
    second = upload(client, name="renamed-copy.pdf")

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/papers").json()) == 1


def test_llm_metadata_wins_when_its_title_is_on_the_page(client, fake_llm):
    fake_llm.metadata = ExtractedMetadata(title=pdfs.SAMPLE_TITLE.upper(), authors=["A. Smith", " B. Jones ", ""],
                                          year=2022, abstract=LONG_ABSTRACT)

    paper = upload_sample(client)

    assert paper["title"] == pdfs.SAMPLE_TITLE.upper()
    assert paper["authors"] == ["A. Smith", "B. Jones"]
    assert paper["year"] == 2022
    assert paper["abstract"] == LONG_ABSTRACT


def test_llm_metadata_is_ignored_when_its_title_is_not_in_the_pdf(client, fake_llm):
    # E.g. the model returned another paper's metadata: none of its fields are used.
    fake_llm.metadata = ExtractedMetadata(title="A Completely Different Paper", authors=["Mallory"],
                                          year=1999, abstract=LONG_ABSTRACT)

    paper = upload_sample(client)

    assert paper["title"] == pdfs.SAMPLE_TITLE
    assert paper["authors"] == pdfs.SAMPLE_AUTHORS
    assert paper["year"] == pdfs.SAMPLE_YEAR
    assert paper["abstract"] == pdfs.SAMPLE_ABSTRACT


def test_llm_fields_that_are_empty_or_short_keep_the_heuristic_values(client, fake_llm):
    fake_llm.metadata = ExtractedMetadata(title=pdfs.SAMPLE_TITLE, authors=[], year=None, abstract="Too short.")

    paper = upload_sample(client)

    assert paper["authors"] == pdfs.SAMPLE_AUTHORS
    assert paper["year"] == pdfs.SAMPLE_YEAR
    assert paper["abstract"] == pdfs.SAMPLE_ABSTRACT


def test_title_falls_back_to_the_file_name(client, fake_llm):
    data = pdfs.unstructured_pdf(["Notes about retrieval augmented generation and why it helps. " * 6])

    paper = upload(client, data, name="My Reading Notes.PDF").json()

    assert paper["title"] == "My Reading Notes"
    assert paper["authors"] == [] and paper["abstract"] is None


def test_pdf_metadata_title_and_authors_are_used(client, fake_llm):
    data = pdfs.paper_pdf(metadata={"title": "Title From The PDF Properties", "author": "Eve Adams; Frank Moore"})

    paper = upload(client, data).json()

    assert paper["title"] == "Title From The PDF Properties"
    assert paper["authors"] == ["Eve Adams", "Frank Moore"]


@pytest.mark.parametrize("placeholder", [
    "Microsoft Word - draft3.docx", "untitled", "Document1", "paper", "main", "arXiv", "main.pdf", "paper.tex"])
def test_placeholder_title_in_pdf_properties_is_ignored(client, fake_llm, placeholder):
    data = pdfs.paper_pdf(metadata={"title": placeholder})

    assert upload(client, data).json()["title"] == pdfs.SAMPLE_TITLE


def test_a_real_title_in_pdf_properties_is_kept(client, fake_llm):
    data = pdfs.paper_pdf(metadata={"title": "Untangling Placeholder Titles in PDF Files"})

    assert upload(client, data).json()["title"] == "Untangling Placeholder Titles in PDF Files"


REAL_TITLES_STARTING_WITH_PLACEHOLDER_WORDS = [
    "Paper Recommendation with Graph Neural Networks",
    "Main Memory Databases Revisited for Modern Hardware",
    "Document Layout Analysis at Web Scale",
    "arXiv Usage Statistics over Two Decades",
]


@known_bug(
    "Confirmed app bug: JUNK_META_TITLE in app/services/pdf.py has no end anchor after the "
    "placeholder words, so any real title that merely starts with Main, Paper, Document, or "
    "arXiv is discarded as a placeholder.")
def test_a_real_title_in_pdf_properties_is_kept_whatever_word_it_starts_with(client, fake_llm):
    # pdf.py filters only "placeholder titles that PDF producers write into the metadata".
    kept = []
    for real_title in REAL_TITLES_STARTING_WITH_PLACEHOLDER_WORDS:
        response = upload(client, pdfs.paper_pdf(metadata={"title": real_title}))
        assert response.status_code == 201, response.text
        kept.append(response.json()["title"])

    with fails_until_fixed():
        assert kept == REAL_TITLES_STARTING_WITH_PLACEHOLDER_WORDS


# --- arXiv PDFs -----------------------------------------------------------------------------------

ARXIV_STAMP = "arXiv:1706.03762v7 [cs.CL] 2 Aug 2023"


def test_arxiv_pdf_gets_its_metadata_from_arxiv(client, fake_llm, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([arxiv_entry()]))
    data = pdfs.paper_pdf(title_lines=["Attention Is All You Need"], margin_stamp=ARXIV_STAMP)

    paper = upload(client, data).json()

    [request] = upstream.sent_to(ARXIV_QUERY)
    assert request.url.params["id_list"] == "1706.03762"
    assert paper["title"] == "Attention Is All You Need"
    assert paper["authors"] == ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]
    assert paper["year"] == 2017  # from arXiv, not the 2023 on the stamp
    assert paper["doi"] == "10.48550/arXiv.1706.03762"
    assert paper["url"] == "https://arxiv.org/abs/1706.03762"
    assert paper["venue"] == "NeurIPS 2017"
    assert fake_llm.metadata_requests == []  # arXiv's answer is authoritative; no LLM call


def test_arxiv_id_of_a_cited_paper_is_not_trusted(client, fake_llm, upstream):
    # Page 1 mentions another paper's arXiv id; arXiv's title for it is not on the page.
    upstream.text(ARXIV_QUERY, arxiv_feed([arxiv_entry(
        arxiv_id="1810.04805v2", title="BERT: Pre-training of Deep Bidirectional Transformers")]))
    data = pdfs.paper_pdf(first_page_note="We build on BERT (arXiv:1810.04805 [cs.CL]) for the encoder.")

    paper = upload(client, data).json()

    assert len(upstream.sent_to(ARXIV_QUERY)) == 1
    assert paper["title"] == pdfs.SAMPLE_TITLE
    assert paper["authors"] == pdfs.SAMPLE_AUTHORS
    assert paper["doi"] is None
    # arXiv's answer was rejected, so the first pages went to the model instead.
    assert len(fake_llm.metadata_requests) == 1


def test_an_arxiv_id_that_arxiv_does_not_know_falls_back_to_the_model(client, fake_llm, upstream):
    upstream.text(ARXIV_QUERY, arxiv_feed([], total=0))
    fake_llm.metadata = ExtractedMetadata(title=pdfs.SAMPLE_TITLE, authors=["Alice Smith"], year=2023,
                                          abstract=LONG_ABSTRACT)
    data = pdfs.paper_pdf(margin_stamp=ARXIV_STAMP)

    paper = upload(client, data).json()

    assert len(upstream.sent_to(ARXIV_QUERY)) == 1
    assert len(fake_llm.metadata_requests) == 1
    assert (paper["authors"], paper["abstract"]) == (["Alice Smith"], LONG_ABSTRACT)


def test_upload_during_an_arxiv_pause_skips_the_lookup(client, fake_llm, upstream):
    # README: "During a pause, searches fail at once with a message, and uploads skip the arXiv
    # metadata lookup."
    upstream.get(ARXIV_QUERY, lambda request: httpx.Response(429))
    assert client.get("/api/search", params={"q": "x", "source": "arxiv"}).status_code == 429
    data = pdfs.paper_pdf(title_lines=["Attention Is All You Need"], margin_stamp=ARXIV_STAMP)

    response = upload(client, data)

    assert response.status_code == 201
    assert response.json()["title"] == "Attention Is All You Need"
    assert len(upstream.sent_to(ARXIV_QUERY)) == 1  # only the search that started the pause
    assert len(fake_llm.metadata_requests) == 1


def test_upload_still_works_when_arxiv_is_unavailable(client, fake_llm, upstream):
    upstream.get(ARXIV_QUERY, lambda request: httpx.Response(503))
    data = pdfs.paper_pdf(title_lines=["Attention Is All You Need"], margin_stamp=ARXIV_STAMP)

    response = upload(client, data)

    assert response.status_code == 201
    assert response.json()["title"] == "Attention Is All You Need"  # from the PDF itself
    assert len(fake_llm.metadata_requests) == 1


# --- Rejected uploads --------------------------------------------------------------------------------


@pytest.mark.parametrize(("data", "name"), [
    (b"Just some notes, not a PDF at all.", "notes.pdf"),
    (b"<!doctype html><html><body>Login required</body></html>", "paper.pdf"),
    (b"", "empty.pdf"),
])
def test_files_that_are_not_pdfs_are_rejected(client, fake_llm, settings, data, name):
    response = upload(client, data, name=name)

    assert response.status_code == 415
    assert response.json()["detail"] == "The file is not a PDF."
    assert client.get("/api/papers").json() == []
    assert stored_files(settings) == []


@pytest.mark.parametrize(("data", "detail"), [
    (pdfs.corrupt_pdf(), "The file could not be read as a PDF."),
    (pdfs.encrypted_pdf(), "The PDF is password-protected."),
    (pdfs.empty_pdf(), "The PDF has no pages."),
    (pdfs.blank_pdf(), "No text could be extracted. The PDF may be a scanned image."),
])
def test_unreadable_pdfs_are_rejected_with_the_reason(client, fake_llm, settings, data, detail):
    response = upload(client, data)

    assert response.status_code == 422
    assert response.json()["detail"] == detail
    assert client.get("/api/papers").json() == []
    assert stored_files(settings) == []
    assert fake_llm.metadata_requests == []


@pytest.mark.parametrize("over", [1, 1024 * 1024], ids=["one byte", "a megabyte"])
def test_file_over_the_size_limit_is_rejected(client, fake_llm, settings, monkeypatch, over):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    data = pdfs.sample_pdf()
    data += b"%" * (1024 * 1024 + over - len(data))  # still a PDF, but over 1 MB

    response = upload(client, data)

    assert response.status_code == 413
    assert response.json()["detail"] == "The file is larger than 1 MB."
    assert client.get("/api/papers").json() == []


def test_file_exactly_at_the_size_limit_is_accepted(client, fake_llm, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    data = pdfs.sample_pdf()
    data += b"%" * (1024 * 1024 - len(data))  # trailing bytes after %%EOF are ignored by readers

    assert upload(client, data).status_code == 201


def test_upload_without_a_file_is_rejected(client):
    assert client.post("/api/papers/upload").status_code == 422


def test_up_to_1_kb_of_junk_before_the_pdf_header_is_tolerated(client, fake_llm):
    # fulltext.looks_like_pdf: "The header may be preceded by a little junk; PDF readers tolerate up to 1 KB."
    junk = b"\r\n" * 512
    tolerated = junk[:1024 - len(b"%PDF-")] + pdfs.sample_pdf()  # the header ends at byte 1024
    too_much = junk[:1024 - len(b"%PDF-") + 1] + pdfs.sample_pdf()

    assert upload(client, tolerated).status_code == 201
    response = upload(client, too_much)
    assert (response.status_code, response.json()["detail"]) == (415, "The file is not a PDF.")


# --- Attaching a PDF to a search result ---------------------------------------------------------------


def test_attach_pdf_to_a_saved_search_result(client, fake_llm):
    paper = save(client, BERT_META)

    response = client.post(f"/api/papers/{paper['id']}/pdf",
                           files={"file": ("bert.pdf", pdfs.sample_pdf(), "application/pdf")})

    assert response.status_code == 200
    attached = response.json()
    assert attached["has_pdf"] is True and attached["full_text_status"] == "ok"
    assert attached["page_count"] == 2 and attached["full_text_error"] is None
    # The paper keeps its own metadata; only the full text is added.
    assert attached["title"] == BERT_META["title"] and attached["authors"] == BERT_META["authors"]
    assert client.get(f"/api/papers/{paper['id']}/pdf").content == pdfs.sample_pdf()


def test_attaching_another_pdf_replaces_the_old_file(client, settings):
    paper = save(client, BERT_META)
    first_pdf = pdfs.paper_pdf(title_lines=["First Version Of The Paper"])
    second_pdf = pdfs.paper_pdf(title_lines=["Second Version Of The Paper"])

    client.post(f"/api/papers/{paper['id']}/pdf", files={"file": ("v1.pdf", first_pdf, "application/pdf")})
    client.post(f"/api/papers/{paper['id']}/pdf", files={"file": ("v2.pdf", second_pdf, "application/pdf")})

    assert client.get(f"/api/papers/{paper['id']}/pdf").content == second_pdf
    assert [f.name for f in stored_files(settings)] == [f"{hashlib.sha256(second_pdf).hexdigest()}.pdf"]


@pytest.mark.parametrize(("data", "status", "detail"), [
    (b"not a pdf", 415, "The file is not a PDF."),
    (pdfs.corrupt_pdf(), 422, "The file could not be read as a PDF."),
    (pdfs.encrypted_pdf(), 422, "The PDF is password-protected."),
    (pdfs.blank_pdf(), 422, "No text could be extracted. The PDF may be a scanned image."),
    (pdfs.sample_pdf() + b"%" * (1024 * 1024), 413, "The file is larger than 1 MB."),
])
def test_a_refused_attachment_leaves_the_paper_unchanged(client, settings, monkeypatch, data, status, detail):
    monkeypatch.setattr(settings, "max_pdf_mb", 1)
    paper = save(client, BERT_META)
    client.post(f"/api/papers/{paper['id']}/fulltext")  # no PDF link: only the abstract
    before = client.get(f"/api/papers/{paper['id']}").json()

    response = client.post(f"/api/papers/{paper['id']}/pdf", files={"file": ("x.pdf", data, "application/pdf")})

    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert client.get(f"/api/papers/{paper['id']}").json() == before
    assert stored_files(settings) == []


def test_attaching_to_a_paper_deleted_meanwhile_is_404_and_keeps_no_file(client, settings, monkeypatch):
    paper = save(client, BERT_META)
    real_store_pdf = fulltext.store_pdf

    def store_after_the_paper_was_deleted(data):
        with SessionLocal() as session:  # the user removes the paper while the PDF is being read
            session.delete(session.get(Paper, paper["id"]))
            session.commit()
        return real_store_pdf(data)

    monkeypatch.setattr(fulltext, "store_pdf", store_after_the_paper_was_deleted)

    response = client.post(f"/api/papers/{paper['id']}/pdf",
                           files={"file": ("bert.pdf", pdfs.sample_pdf(), "application/pdf")})

    assert (response.status_code, response.json()["detail"]) == (404, "Paper not found.")
    assert stored_files(settings) == []
    assert client.get(f"/api/papers/{paper['id']}").status_code == 404


def test_attach_to_unknown_paper(client):
    response = client.post("/api/papers/999999/pdf",
                           files={"file": ("x.pdf", pdfs.sample_pdf(), "application/pdf")})
    assert response.status_code == 404


def test_pdf_of_a_paper_without_one_is_404(client):
    paper = save(client, BERT_META)

    response = client.get(f"/api/papers/{paper['id']}/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "No local PDF for this paper."


def test_pdf_of_unknown_paper_is_404(client):
    assert client.get("/api/papers/999999/pdf").status_code == 404


def test_pdf_whose_stored_file_is_gone_is_404(client, fake_llm, settings):
    paper = upload_sample(client)
    for stored in stored_files(settings):
        stored.unlink()

    response = client.get(f"/api/papers/{paper['id']}/pdf")

    assert (response.status_code, response.json()["detail"]) == (404, "No local PDF for this paper.")
