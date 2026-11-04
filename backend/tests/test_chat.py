"""F5: asking questions about a paper, with the conversation kept per paper.

`fake_llm` replaces the model call; the last tests use the fake `claude` executable.
"""

import json
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import ChatMessage, Paper
from app.services.llm import LlmError
from support import pdfs
from support.papers import ARXIV_META, BERT_META, events, meta, save, streamed_text, upload_sample


def ask(client, paper_id: int, question: str, model: str | None = None):
    return client.post(f"/api/papers/{paper_id}/chat", json={"question": question, "model": model})


def history(client, paper_id: int) -> list[dict]:
    response = client.get(f"/api/papers/{paper_id}/chat")
    assert response.status_code == 200
    return response.json()


def test_answer_is_streamed_and_both_turns_are_saved(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply("Natural Questions, ", "TriviaQA, and WebQuestions.")

    response = ask(client, paper["id"], "What datasets are used?")

    assert response.status_code == 200
    stream = events(response)
    assert stream[0] == {"type": "meta", "context": "full_text", "truncated": False}
    assert streamed_text(stream) == "Natural Questions, TriviaQA, and WebQuestions."
    question, answer = stream[-1]["messages"]
    assert (question["role"], question["content"]) == ("user", "What datasets are used?")
    assert (answer["role"], answer["content"]) == ("assistant", "Natural Questions, TriviaQA, and WebQuestions.")
    assert (answer["model"], answer["context"]) == ("fake-model-1", "full_text")
    assert history(client, paper["id"]) == [question, answer]


def test_question_is_answered_from_the_paper(client, fake_llm):
    paper = upload_sample(client)

    ask(client, paper["id"], "What is the main idea of the proposed approach?")

    [call] = fake_llm.calls
    assert call.messages == [{"role": "user", "content": "What is the main idea of the proposed approach?"}]
    assert pdfs.BODY_MARKER in call.paper


def test_follow_up_questions_include_the_conversation_so_far(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.reply("It addresses hallucination.")
    fake_llm.reply("It retrieves passages first.")

    ask(client, paper["id"], "What problem does this paper address?")
    ask(client, paper["id"], "How does it solve it?")

    assert fake_llm.calls[1].messages == [
        {"role": "user", "content": "What problem does this paper address?"},
        {"role": "assistant", "content": "It addresses hallucination."},
        {"role": "user", "content": "How does it solve it?"},
    ]
    assert [m["content"] for m in history(client, paper["id"])] == [
        "What problem does this paper address?", "It addresses hallucination.",
        "How does it solve it?", "It retrieves passages first.",
    ]


def test_only_recent_turns_are_sent(client, fake_llm, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_history_messages", 2)
    paper = upload_sample(client)
    for n in (1, 2):
        fake_llm.reply(f"Answer {n}.")
        ask(client, paper["id"], f"Question {n}?")

    ask(client, paper["id"], "Question 3?")

    assert [m["content"] for m in fake_llm.calls[-1].messages] == ["Question 2?", "Answer 2.", "Question 3?"]


def test_history_never_starts_with_an_answer(client, fake_llm, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_history_messages", 3)  # would start mid-pair
    paper = upload_sample(client)
    for n in (1, 2):
        fake_llm.reply(f"Answer {n}.")
        ask(client, paper["id"], f"Question {n}?")

    ask(client, paper["id"], "Question 3?")

    assert [m["content"] for m in fake_llm.calls[-1].messages] == ["Question 2?", "Answer 2.", "Question 3?"]


def test_history_can_be_turned_off(client, fake_llm, settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_history_messages", 0)
    paper = upload_sample(client)
    ask(client, paper["id"], "First?")

    ask(client, paper["id"], "Second?")

    assert fake_llm.calls[-1].messages == [{"role": "user", "content": "Second?"}]


def test_question_whitespace_is_trimmed(client, fake_llm):
    paper = upload_sample(client)

    ask(client, paper["id"], "   What are the major limitations?\n ")

    assert fake_llm.calls[0].prompt == "What are the major limitations?"
    assert history(client, paper["id"])[0]["content"] == "What are the major limitations?"


def test_answer_about_a_paper_without_pdf_is_marked_as_abstract_only(client, fake_llm):
    paper = save(client, ARXIV_META)

    stream = events(ask(client, paper["id"], "How does this method compare with the baselines?"))

    assert stream[0]["context"] == "abstract"
    assert stream[-1]["messages"][1]["context"] == "abstract"
    assert ARXIV_META["abstract"] in fake_llm.calls[0].paper


def test_questions_about_an_unsaved_paper_work_and_are_kept_when_it_is_saved(client, fake_llm):
    opened = client.post("/api/papers/open", json=BERT_META).json()
    fake_llm.reply("A language representation model.")
    asked = events(ask(client, opened["id"], "What is BERT?"))
    assert asked[-1]["type"] == "done"

    response = client.post(f"/api/papers/{opened['id']}/save")

    assert response.status_code == 200
    assert response.json()["id"] == opened["id"] and response.json()["in_library"] is True
    assert [p["id"] for p in client.get("/api/papers").json()] == [opened["id"]]
    assert [(m["role"], m["content"]) for m in history(client, opened["id"])] == [
        ("user", "What is BERT?"), ("assistant", "A language representation model.")]


def test_a_paper_with_nothing_to_read_cannot_be_asked_about(client, fake_llm):
    paper = save(client, meta(BERT_META, abstract=None))  # no PDF link and no abstract

    response = ask(client, paper["id"], "What is it about?")

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "There is nothing to read for this paper: no full text and no abstract. Attach its PDF first.")
    assert fake_llm.calls == []


@pytest.mark.parametrize(("body", "invalid_field"), [
    ({"question": ""}, "question"),
    ({"question": "   \n  "}, "question"),
    ({"question": "x" * 4001}, "question"),  # the question box's maxLength is 4000
    ({}, "question"),
    ({"question": "Why?", "model": "x" * 101}, "model"),  # longer than any model id may be
])
def test_invalid_questions_are_rejected(client, fake_llm, body, invalid_field):
    paper = upload_sample(client)

    response = client.post(f"/api/papers/{paper['id']}/chat", json=body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list), detail  # request validation, before any model check
    assert [error["loc"] for error in detail] == [["body", invalid_field]]
    assert fake_llm.calls == []
    assert history(client, paper["id"]) == []


def test_longest_allowed_question_is_answered_and_saved(client, fake_llm):
    paper = upload_sample(client)
    question = "Is it " + "really " * 570 + "new?"  # 4,000 characters, the question box's maxLength

    stream = events(ask(client, paper["id"], question))

    assert len(question) == 4000
    assert stream[-1]["type"] == "done"
    assert fake_llm.calls[0].prompt == question
    assert [m["content"] for m in history(client, paper["id"])] == [question, "This is a fake answer."]


def test_question_with_an_unknown_model_is_rejected(client, fake_llm):
    paper = upload_sample(client)

    response = ask(client, paper["id"], "Why?", model="gpt-4o")

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown model “gpt-4o”."
    assert fake_llm.calls == []


def test_question_with_a_model_from_the_menu(client, fake_llm):
    paper = upload_sample(client)

    ask(client, paper["id"], "Why?", model="fable")

    assert fake_llm.calls[0].model == "fable"


def test_failed_answer_saves_nothing(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.fail(LlmError("Claude Code did not finish in time. Try again."), "Half an ")

    stream = events(ask(client, paper["id"], "What is the main idea?"))

    assert stream[-1] == {"type": "error", "message": "Claude Code did not finish in time. Try again."}
    assert history(client, paper["id"]) == []


def test_a_failed_turn_is_left_out_of_later_history(client, fake_llm):
    paper = upload_sample(client)
    fake_llm.fail(LlmError("The model declined to answer this request."))
    ask(client, paper["id"], "A question that failed?")

    ask(client, paper["id"], "A new question?")

    assert fake_llm.calls[-1].messages == [{"role": "user", "content": "A new question?"}]


def test_conversations_are_kept_per_paper(client, fake_llm):
    first = upload_sample(client)
    second = save(client, BERT_META)

    ask(client, first["id"], "About the first paper?")

    assert len(history(client, first["id"])) == 2
    assert history(client, second["id"]) == []


def test_clear_conversation(client, fake_llm):
    paper = upload_sample(client)
    ask(client, paper["id"], "First question?")

    response = client.delete(f"/api/papers/{paper['id']}/chat")

    assert response.status_code == 204
    assert history(client, paper["id"]) == []
    ask(client, paper["id"], "Fresh start?")
    assert fake_llm.calls[-1].messages == [{"role": "user", "content": "Fresh start?"}]


@pytest.mark.parametrize(("method", "kwargs"), [
    ("get", {}),
    ("post", {"json": {"question": "Why?"}}),
    ("delete", {}),
])
def test_chat_on_unknown_paper(client, fake_llm, method, kwargs):
    response = getattr(client, method)("/api/papers/999999/chat", **kwargs)

    assert response.status_code == 404
    assert fake_llm.calls == []


def test_paper_deleted_while_the_answer_was_written(client, fake_llm):
    paper = upload_sample(client)

    def delete_paper(call):
        with SessionLocal() as db:
            db.delete(db.get(Paper, paper["id"]))
            db.commit()

    fake_llm.reply("An answer nobody will see.", before=delete_paper)

    stream = events(ask(client, paper["id"], "Why?"))

    assert stream[-1] == {"type": "error", "message": "The paper was removed from the library."}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0


# --- Through the default Claude Code provider (fake `claude` executable) -------------------------


def test_follow_up_question_through_claude_code(client, fake_claude):
    paper = upload_sample(client)

    first = events(ask(client, paper["id"], "What problem does this paper address?"))
    second = events(ask(client, paper["id"], "What datasets are used?"))

    first_answer = first[-1]["messages"][1]
    assert f"about “{pdfs.SAMPLE_TITLE}”" in first_answer["content"]
    assert second[-1]["messages"][1]["model"] == "claude-fake-opus via Claude Code"
    first_prompt, second_prompt = [run["stdin"]["message"]["content"] for run in fake_claude.runs()[-2:]]
    assert first_prompt == "What problem does this paper address?"
    # Claude Code takes one prompt per run, so the earlier turns are quoted in it, each inside
    # a <turn-…> tag, and the prompt ends with the new question.
    quoted = re.findall(r'<(turn-[0-9a-f]+) role="(user|assistant)">\n(.*?)\n</\1>', second_prompt, re.DOTALL)
    assert [(role, text) for _, role, text in quoted] == [
        ("user", "What problem does this paper address?"), ("assistant", first_answer["content"])]
    assert second_prompt.endswith("\nWhat datasets are used?")


def test_claude_code_error_keeps_the_conversation_unchanged(client, fake_claude):
    paper = upload_sample(client)

    stream = events(ask(client, paper["id"], "[[fake:error]] Please fail."))

    assert stream[-1] == {"type": "error", "message": "Claude Code reported an error: Simulated failure"}
    assert history(client, paper["id"]) == []


@pytest.fixture
def live_server():
    """The app on a real local port, for a client that leaves in the middle of an answer."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "the test server did not start"
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
        server.should_exit = True
        thread.join(timeout=10)


def test_leaving_while_an_answer_streams_stops_claude_code_and_saves_nothing(fake_claude, live_server):
    # A long answer that would take about 25 s to arrive.
    fake_claude.set(reply="word " * 250, chunk_delay="0.5")
    with SessionLocal() as session:
        paper = Paper(source="upload", external_id="leave-test", title="A Paper", authors=[], in_library=True,
                      full_text="The full text. " * 20, full_text_status="ok", page_count=1)
        session.add(paper)
        session.commit()
        paper_id = paper.id

    with httpx.Client(base_url=live_server, timeout=30) as browser:
        with browser.stream("POST", f"/api/papers/{paper_id}/chat", json={"question": "Why?"}) as response:
            lines = response.iter_lines()
            assert json.loads(next(lines))["type"] == "meta"
            assert json.loads(next(lines))["type"] == "text"
        # The response is closed here: the user navigated away.

    [run] = fake_claude.runs()
    deadline = time.monotonic() + 5
    while fake_claude.is_running(run["pid"]) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not fake_claude.is_running(run["pid"])
    assert not Path(run["cwd"]).parent.exists()  # its scratch folder is gone too
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(ChatMessage)) == 0
