"""F4: summarizing a paper with the LLM, based on the paper's content.

`fake_llm` replaces the model call and records what the app sent; the last tests run
the default Claude Code provider end to end against the fake `claude` executable.
"""

import re
from types import SimpleNamespace

import httpx
import pytest

from app.db import SessionLocal
from app.models import Paper
from app.services import llm, pdf
from app.services.llm import SUMMARY_REQUEST, LlmError
from support import pdfs
from support.fake_anthropic import FakeAnthropic, answer
from support.fake_llm import RESET
from support.known_bugs import fails_until_fixed, known_bug
from support.papers import ARXIV_META, BERT_META, events, meta, save, streamed_text, upload, upload_sample
from support.upstream import PUBLIC_IP


def summarize(client, paper_id: int, model: str | None = None):
    return client.post(f"/api/papers/{paper_id}/summary", params={"model": model} if model else None)


def source_note(paper_block: str) -> str:
    return re.search(r"<source_note>(.*?)</source_note>", paper_block, re.DOTALL).group(1)


def test_summary_is_streamed_and_saved(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply("**TL;DR**: Retrieval ", "reduces hallucination.")

    response = summarize(client, paper["id"])

    assert response.status_code == 200
    # Streamed as it is written: neither cached nor held back by a proxy such as nginx.
    assert response.headers["cache-control"].lower() == "no-cache"
    assert response.headers["x-accel-buffering"].lower() == "no"
    stream = events(response)
    assert stream[0] == {"type": "meta", "context": "full_text", "truncated": False}
    assert [e["type"] for e in stream[1:]] == ["text", "text", "done"]
    assert streamed_text(stream) == "**TL;DR**: Retrieval reduces hallucination."
    done = stream[-1]["paper"]
    assert done["id"] == paper["id"]
    assert done["summary"] == "**TL;DR**: Retrieval reduces hallucination."
    assert done["summary_model"] == "fake-model-1"
    assert done["summary_context"] == "full_text"
    assert done["summary_created_at"] is not None

    saved = client.get(f"/api/papers/{paper['id']}").json()
    assert {k: saved[k] for k in done if k.startswith("summary")} == {k: done[k] for k in done if k.startswith("summary")}


def test_summary_is_based_on_the_full_text_of_the_paper(client, fake_llm):
    paper = upload_sample(client)

    summarize(client, paper["id"])

    [call] = fake_llm.calls
    assert call.messages == [{"role": "user", "content": SUMMARY_REQUEST}]
    assert f"<title>{pdfs.SAMPLE_TITLE}</title>" in call.paper
    assert "<authors>Alice Smith, Bob Jones, Carol White</authors>" in call.paper
    assert f"<year>{pdfs.SAMPLE_YEAR}</year>" in call.paper
    assert pdfs.BODY_MARKER in call.paper  # text from page 2, not just the metadata
    assert re.search(r"\b2 pages\b", source_note(call.paper))  # the model knows how long the paper is
    assert call.model == "opus"  # the configured default


def test_summary_of_a_paper_without_pdf_uses_the_abstract(client, fake_llm, upstream):
    paper = save(client, ARXIV_META)  # no PDF link

    stream = events(summarize(client, paper["id"]))

    assert stream[0]["context"] == "abstract"
    assert stream[-1]["paper"]["summary_context"] == "abstract"
    [call] = fake_llm.calls
    assert ARXIV_META["abstract"] in call.paper
    assert "Only the abstract is available" in call.paper
    # The full text was looked for first (and recorded as unavailable).
    assert client.get(f"/api/papers/{paper['id']}").json()["full_text_status"] == "unavailable"
    assert upstream.requests == []


def test_summary_downloads_the_open_access_pdf_first(client, fake_llm, upstream, dns):
    dns["papers.example.org"] = PUBLIC_IP
    upstream.get("https://papers.example.org/attention.pdf",
                 lambda request: httpx.Response(200, content=pdfs.sample_pdf()))
    paper = save(client, meta(ARXIV_META, pdf_url="https://papers.example.org/attention.pdf"))

    stream = events(summarize(client, paper["id"]))

    assert stream[0]["context"] == "full_text"
    assert pdfs.BODY_MARKER in fake_llm.calls[0].paper


def test_summary_needs_something_to_read(client, fake_llm):
    paper = save(client, meta(BERT_META, abstract=None))  # no PDF and no abstract

    response = summarize(client, paper["id"])

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "There is nothing to read for this paper: no full text and no abstract. Attach its PDF first.")
    assert fake_llm.calls == []


def test_summary_of_unknown_paper(client, fake_llm):
    response = summarize(client, 999999)

    assert response.status_code == 404
    assert fake_llm.calls == []


def test_summary_with_a_model_from_the_menu(client, fake_llm):
    paper = upload_sample(client)

    summarize(client, paper["id"], model="sonnet")

    assert fake_llm.calls[0].model == "sonnet"


def test_summary_with_an_unknown_model_is_rejected_before_calling_the_llm(client, fake_llm):
    paper = upload_sample(client)

    response = summarize(client, paper["id"], model="gpt-4o")

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown model “gpt-4o”."
    assert fake_llm.calls == []


def test_regenerating_replaces_the_summary(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply("First summary.")
    fake_llm.reply("Second summary.", model="fake-model-2")

    summarize(client, paper["id"])
    summarize(client, paper["id"])

    saved = client.get(f"/api/papers/{paper['id']}").json()
    assert (saved["summary"], saved["summary_model"]) == ("Second summary.", "fake-model-2")


def test_failed_summary_is_reported_and_keeps_the_previous_one(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply("A good summary.")
    summarize(client, paper["id"])
    fake_llm.fail(LlmError("The model declined to answer this request."), "Partial text that ")

    stream = events(summarize(client, paper["id"]))

    assert stream[-1] == {"type": "error", "message": "The model declined to answer this request."}
    assert not any(e["type"] == "done" for e in stream)
    assert client.get(f"/api/papers/{paper['id']}").json()["summary"] == "A good summary."


def test_unexpected_failure_is_reported_in_the_stream_without_details(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.fail(RuntimeError("database is locked at /secret/path"))

    response = summarize(client, paper["id"])

    assert response.status_code == 200  # the stream had already started
    assert events(response)[-1] == {
        "type": "error", "message": "Something went wrong while generating the answer. Please try again."}
    assert client.get(f"/api/papers/{paper['id']}").json()["summary"] is None


def test_restarted_answer_discards_the_earlier_text(client, fake_llm):
    # With the API provider, a refusal can switch to a fallback model mid-answer.
    paper = upload_sample(client)
    fake_llm.reply("Text from the first model", RESET, "Text from the fallback model.")

    stream = events(summarize(client, paper["id"]))

    assert {"type": "reset"} in stream
    assert streamed_text(stream) == "Text from the fallback model."
    assert stream[-1]["paper"]["summary"] == "Text from the fallback model."


def test_very_long_paper_is_cut_off_and_the_client_is_told(client, fake_llm, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_paper_chars", 200)
    paper = upload_sample(client)

    stream = events(summarize(client, paper["id"]))

    assert stream[0] == {"type": "meta", "context": "full_text", "truncated": True}
    paper_block = fake_llm.calls[0].paper
    assert "The text was cut off after the first 200 characters." in paper_block
    text = paper_block.split("<text>\n", 1)[1].split("\n</text>", 1)[0]
    assert len(text) == 200
    assert pdfs.BODY_MARKER not in paper_block


@known_bug(
    "Confirmed app bug: pdf.extract reads only the first MAX_PDF_PAGES_FOR_TEXT pages, but "
    "build_context is given page_count of the whole PDF and truncated=False, so neither the model "
    "nor the UI is told that the text was cut off (README: the prompt tells the model when a long "
    "paper is cut off, and the Summary tab shows a note).")
def test_a_pdf_longer_than_the_page_limit_is_reported_as_cut_off(client, fake_llm):
    uploaded = upload(client, pdfs.numbered_pages_pdf(pdf.MAX_PDF_PAGES_FOR_TEXT + 2))
    assert uploaded.status_code == 201, uploaded.text

    stream = events(summarize(client, uploaded.json()["id"]))

    [call] = fake_llm.calls
    assert stream[-1]["type"] == "done"
    with fails_until_fixed():
        assert stream[0] == {"type": "meta", "context": "full_text", "truncated": True}  # the UI is told
        assert "cut off" in source_note(call.paper)  # and so is the model


@pytest.mark.parametrize(("pdf_url", "host", "downloads"), [
    ("https://papers.example.org/missing.pdf", "papers.example.org", 1),  # the link answers 404
    ("http://10.0.0.7/bert.pdf", "10.0.0.7", 0),  # a private address: refused without a request
])
def test_after_a_failed_download_the_abstract_is_used_and_labelled(
        client, fake_llm, upstream, dns, pdf_url, host, downloads):
    dns["papers.example.org"] = PUBLIC_IP
    upstream.get("https://papers.example.org/missing.pdf", lambda request: httpx.Response(404))
    paper = save(client, meta(BERT_META, pdf_url=pdf_url))

    summary = events(summarize(client, paper["id"]))
    answer_ = events(client.post(f"/api/papers/{paper['id']}/chat", json={"question": "What is new?"}))
    again = events(summarize(client, paper["id"]))

    assert [stream[0]["context"] for stream in (summary, answer_, again)] == ["abstract"] * 3
    assert summary[-1]["paper"]["summary_context"] == "abstract"
    assert answer_[-1]["messages"][1]["context"] == "abstract"
    assert all(BERT_META["abstract"] in call.paper for call in fake_llm.calls)
    # Tried once, not again for every request: every attempt starts with an address check,
    # also one that is refused before any request is sent.
    assert dns.lookups == [host]
    assert len(upstream.requests) == downloads


@pytest.mark.parametrize("endpoint", ["summary", "chat"])
def test_a_paper_deleted_while_its_pdf_downloads_is_404(client, fake_llm, upstream, dns, endpoint):
    dns["papers.example.org"] = PUBLIC_IP
    paper = save(client, meta(BERT_META, pdf_url="https://papers.example.org/bert.pdf"))

    def delete_then_answer(request):
        with SessionLocal() as session:
            session.delete(session.get(Paper, paper["id"]))
            session.commit()
        return httpx.Response(200, content=pdfs.sample_pdf())

    upstream.get("https://papers.example.org/bert.pdf", delete_then_answer)

    response = client.post(f"/api/papers/{paper['id']}/{endpoint}",
                           json={"question": "Why?"} if endpoint == "chat" else None)

    assert (response.status_code, response.json()["detail"]) == (404, "Paper not found.")
    assert fake_llm.calls == []


def test_paper_deleted_while_the_summary_was_written(client, fake_llm):
    paper = upload_sample(client)

    def delete_paper(call):
        with SessionLocal() as db:
            db.delete(db.get(Paper, paper["id"]))
            db.commit()

    fake_llm.reply("A summary nobody will see.", before=delete_paper)

    stream = events(summarize(client, paper["id"]))

    assert stream[-1] == {"type": "error", "message": "The paper was removed from the library."}


# --- Through the default Claude Code provider (fake `claude` executable) -------------------------


def test_summary_through_claude_code(client, fake_claude):
    paper = upload_sample(client)

    stream = events(summarize(client, paper["id"], model="haiku"))

    assert stream[0]["context"] == "full_text"
    assert len([e for e in stream if e["type"] == "text"]) > 1  # streamed in pieces
    summary = stream[-1]["paper"]["summary"]
    # The fake CLI reports what it was given: the paper's title and its text up to page 2's last words.
    assert f"about “{pdfs.SAMPLE_TITLE}”" in summary
    assert f"The paper text ends with “{pdfs.SAMPLE_TEXT_END}”" in summary
    assert streamed_text(stream) == summary
    assert stream[-1]["paper"]["summary_model"] == "claude-fake-haiku via Claude Code"

    # The upload asked Claude Code for the metadata (quickly, at low effort), then the summary ran.
    metadata_run, summary_run = fake_claude.runs()
    assert "<pages>" in metadata_run["stdin"]["message"]["content"]
    assert metadata_run["argv"][metadata_run["argv"].index("--effort") + 1] == "low"
    assert summary_run["argv"][summary_run["argv"].index("--model") + 1] == "haiku"
    assert summary_run["argv"][summary_run["argv"].index("--effort") + 1] == "medium"
    assert pdfs.BODY_MARKER in summary_run["system_prompt"]
    assert summary_run["stdin"]["message"]["content"] == SUMMARY_REQUEST


def test_claude_code_failure_is_shown_to_the_user(client, fake_claude):
    paper = upload_sample(client)
    fake_claude.set(mode="rate_limit")

    stream = events(summarize(client, paper["id"]))

    assert stream[-1]["type"] == "error"
    assert stream[-1]["message"].startswith("Claude Code usage limit reached (You've reached your usage limit")
    assert client.get(f"/api/papers/{paper['id']}").json()["summary"] is None


@pytest.mark.parametrize(("mode", "message"), [
    ("refusal", "The model declined to answer this request."),
    ("empty", "The model returned an empty answer. Try again."),
])
def test_a_refused_or_empty_summary_from_claude_code_keeps_the_previous_one(client, fake_claude, mode, message):
    paper = upload_sample(client)
    previous = events(summarize(client, paper["id"]))[-1]["paper"]
    fake_claude.set(mode=mode)

    stream = events(summarize(client, paper["id"]))

    assert stream[-1] == {"type": "error", "message": message}
    saved = client.get(f"/api/papers/{paper['id']}").json()
    assert (saved["summary"], saved["summary_created_at"]) == (previous["summary"], previous["summary_created_at"])


def test_a_summary_cut_off_by_claude_code_is_kept_with_a_note(client, fake_claude):
    paper = upload_sample(client)
    fake_claude.set(mode="max_tokens")

    stream = events(summarize(client, paper["id"]))

    summary = stream[-1]["paper"]["summary"]
    answer_text = streamed_text(stream)
    assert answer_text and summary.startswith(answer_text)
    assert "cut off" in summary[len(answer_text):]
    assert client.get(f"/api/papers/{paper['id']}").json()["summary"] == summary


def test_summary_when_claude_code_is_not_installed(client):
    # CLAUDE_CODE_PATH points at a missing file (conftest.py): the user gets the fix.
    paper = upload_sample(client)

    stream = events(summarize(client, paper["id"]))

    assert stream[-1]["type"] == "error"
    assert "CLAUDE_CODE_PATH" in stream[-1]["message"]


# --- Through the Anthropic API provider (LLM_PROVIDER=api, fake client) -------------------------


def test_summary_and_answers_through_the_anthropic_api(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "api")
    api = FakeAnthropic()
    api.parse_result = SimpleNamespace(stop_reason="max_tokens", parsed_output=None)  # upload: heuristics
    api.streams = [answer("**TL;DR**: A summary from the API."),
                   answer("An answer from Sonnet.", model="claude-sonnet-5-20261001")]
    monkeypatch.setattr(llm, "get_client", lambda: api)
    paper = upload_sample(client)

    summary = events(summarize(client, paper["id"]))
    reply = events(client.post(f"/api/papers/{paper['id']}/chat",
                               json={"question": "What datasets are used?", "model": "claude-sonnet-5"}))
    alias = client.post(f"/api/papers/{paper['id']}/chat", json={"question": "Why?", "model": "haiku"})

    assert streamed_text(summary) == summary[-1]["paper"]["summary"] == "**TL;DR**: A summary from the API."
    assert summary[-1]["paper"]["summary_model"] == "claude-opus-5"
    assert reply[-1]["messages"][1]["content"] == "An answer from Sonnet."
    assert reply[-1]["messages"][1]["model"] == "claude-sonnet-5-20261001"
    # A Claude Code alias is not an API model.
    assert (alias.status_code, alias.json()["detail"]) == (422, "Unknown model “haiku”.")
    summary_request, question_request = api.stream_params
    assert summary_request["model"] == "claude-opus-5"
    assert summary_request["messages"] == [{"role": "user", "content": SUMMARY_REQUEST}]
    instructions, paper_block = summary_request["system"]
    assert pdfs.BODY_MARKER in paper_block["text"] and paper_block["cache_control"] == {"type": "ephemeral"}
    assert question_request["model"] == "claude-sonnet-5"
    assert question_request["system"] == summary_request["system"]  # the same cached paper prefix
    assert question_request["messages"] == [{"role": "user", "content": "What datasets are used?"}]
