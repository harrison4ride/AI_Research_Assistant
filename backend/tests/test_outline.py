"""The reader's section outline (from the PDF) and its one-sentence section summaries."""

import json

from app.services.llm import LlmError
from support import pdfs
from support.papers import ARXIV_META, BERT_META, save, upload, upload_sample

SECTIONS = ["Abstract", *pdfs.SAMPLE_SECTION_TITLES]


def outline(client, paper_id: int) -> dict:
    response = client.get(f"/api/papers/{paper_id}/outline")
    assert response.status_code == 200, response.text
    return response.json()


def summarize_sections(client, paper_id: int, model: str | None = None):
    return client.post(f"/api/papers/{paper_id}/outline/summaries", json={"model": model})


def summaries_for_every_heading(call) -> str:
    headings = json.loads(call.prompt.split("<headings>\n", 1)[1].split("\n</headings>", 1)[0])
    return json.dumps({"summaries": [{"n": h["n"], "summary": f"About {h['heading']}."} for h in headings]})


def test_outline_lists_the_sections_of_the_pdf(client, fake_llm):
    paper = upload_sample(client)

    body = outline(client, paper["id"])

    assert body["available"] is True and body["summarized"] is False
    assert [s["title"] for s in body["sections"]] == SECTIONS
    assert [s["page"] for s in body["sections"]] == [1, 1, 2, 2, 2]
    assert all(0 <= s["top"] <= 1 and s["summary"] is None for s in body["sections"])


def test_outline_prefers_the_pdf_bookmarks(client, fake_llm):
    toc = [[1, "Introduction", 1], [1, "Method", 2], [2, "Retriever", 2], [1, "Experiments", 2]]
    paper = upload(client, pdfs.paper_pdf(toc=toc)).json()

    body = outline(client, paper["id"])

    assert [(s["level"], s["title"], s["page"]) for s in body["sections"]] == [
        (1, "Introduction", 1), (1, "Method", 2), (2, "Retriever", 2), (1, "Experiments", 2)]


def test_outline_needs_a_pdf(client):
    paper = save(client, ARXIV_META)

    body = outline(client, paper["id"])

    assert body["available"] is False
    assert body["reason"] == "The outline needs the paper's PDF."


def test_outline_of_unknown_paper(client):
    assert client.get("/api/papers/999999/outline").status_code == 404


def test_section_summaries_are_written_and_saved(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply_with(summaries_for_every_heading)

    response = summarize_sections(client, paper["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["summarized"] is True and body["model"] == "fake-model-1"
    assert [s["summary"] for s in body["sections"]] == [f"About {title}." for title in SECTIONS]
    assert outline(client, paper["id"]) == body  # saved


def test_section_headings_are_passed_to_the_model_as_data(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply_with(summaries_for_every_heading)

    summarize_sections(client, paper["id"], model="sonnet")

    [call] = fake_llm.calls
    assert call.model == "sonnet"
    assert '{"n": 2, "heading": "1 Introduction"}' in call.prompt
    assert pdfs.BODY_MARKER in call.paper


def test_a_reply_that_skips_a_section_is_not_saved(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply(json.dumps({"summaries": [{"n": 1, "summary": "About the abstract."},
                                             {"n": 3, "summary": "About the method."}]}))

    response = summarize_sections(client, paper["id"])

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The model's reply skipped 3 of 5 sections, so it was not saved. Try again.")
    assert outline(client, paper["id"])["summarized"] is False


def test_model_failure_while_summarizing_sections(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.fail(LlmError("Claude Code reported an error: overloaded"))

    response = summarize_sections(client, paper["id"])

    assert response.status_code == 502
    assert response.json()["detail"] == "Claude Code reported an error: overloaded"


def test_section_summaries_need_the_full_text(client, fake_llm):
    paper = save(client, BERT_META)  # abstract only

    response = summarize_sections(client, paper["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == "Section summaries need the paper's full text (its PDF)."
    assert fake_llm.calls == []


def test_section_summaries_with_unknown_model(client, fake_llm):
    paper = upload_sample(client)

    response = summarize_sections(client, paper["id"], model="gpt-4o")

    assert response.status_code == 422
    assert fake_llm.calls == []


def test_without_headings_the_model_names_the_sections_and_they_are_located(client, fake_llm):
    data = pdfs.unstructured_pdf([
        "Method. We retrieve passages with a dense retriever and condition the generator on them. " * 3,
        "Results. Retrieval improves exact match on every benchmark we tried, by eleven points. " * 3,
    ])
    paper = upload(client, data).json()
    assert outline(client, paper["id"])["sections"] == []
    fake_llm.reply(json.dumps({"sections": [
        {"title": "Method", "summary": "How passages are retrieved."},
        {"title": "Results", "summary": "Retrieval helps."},
        {"title": "Appendix Z", "summary": "Not in this PDF."},
    ]}))

    body = summarize_sections(client, paper["id"]).json()

    assert [(s["title"], s["summary"]) for s in body["sections"]] == [
        ("Method", "How passages are retrieved."), ("Results", "Retrieval helps."), ("Appendix Z", "Not in this PDF.")]
    assert [s["page"] for s in body["sections"]] == [1, 1, None]  # found in the PDF, or not


def test_attaching_a_new_pdf_resets_the_outline(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply_with(summaries_for_every_heading)
    summarize_sections(client, paper["id"])
    toc = [[1, "Introduction", 1], [1, "Method", 2], [1, "Experiments", 2]]

    client.post(f"/api/papers/{paper['id']}/pdf",
                files={"file": ("v2.pdf", pdfs.paper_pdf(toc=toc), "application/pdf")})

    body = outline(client, paper["id"])
    assert body["summarized"] is False
    assert [s["title"] for s in body["sections"]] == ["Introduction", "Method", "Experiments"]


def test_section_summaries_through_claude_code(client, fake_claude):
    paper = upload_sample(client)

    body = summarize_sections(client, paper["id"]).json()

    assert body["model"] == "claude-fake-1 via Claude Code"
    assert [s["summary"] for s in body["sections"]] == [f"Fake summary of the section {title}." for title in SECTIONS]
