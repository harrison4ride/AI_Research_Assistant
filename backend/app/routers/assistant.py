"""LLM features: paper summaries (F4) and Q&A about a paper (F5).

Both endpoints stream newline-delimited JSON events:
  {"type": "meta", "context": "full_text" | "abstract", "truncated": bool}
  {"type": "text", "text": "..."}         repeated, answer text deltas
  {"type": "reset"}                       discard text so far (fallback model restarted)
  {"type": "done", ...}                   the saved summary / chat messages
  {"type": "error", "message": "..."}     failure; nothing was saved
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import ChatMessage, Paper
from ..schemas import AppConfig, AskRequest, ChatMessageOut, PaperDetail
from ..services.fulltext import ensure_full_text
from ..services.llm import (
    SUMMARY_REQUEST,
    LlmError,
    PaperContext,
    StreamResult,
    build_context,
    llm_status,
    model_label,
    stream_reply,
)
from .papers import get_paper_or_404

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["assistant"])


def _event(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode()


def _ndjson_response(events: AsyncIterator[bytes]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _paper_context(paper_id: int, db: Session) -> PaperContext:
    """Load the paper, fetching its full text first if that was never tried."""
    paper = get_paper_or_404(paper_id, db)
    if not await ensure_full_text(paper, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found.")
    if not paper.full_text and not paper.abstract:
        raise HTTPException(
            422, "There is nothing to read for this paper: no full text and no abstract. Attach its PDF first."
        )
    return build_context(
        title=paper.title,
        authors=paper.authors or [],
        year=paper.year,
        abstract=paper.abstract,
        full_text=paper.full_text,
        page_count=paper.page_count,
    )


async def _stream_and_save(
    context: PaperContext,
    messages: list[dict[str, Any]],
    save: Callable[[StreamResult], dict[str, Any] | None],
) -> AsyncIterator[bytes]:
    yield _event({"type": "meta", "context": context.kind, "truncated": context.truncated})
    result: list[StreamResult] = []
    try:
        async for event in stream_reply(context, messages, result):
            yield _event({"type": event.type, "text": event.text} if event.type == "text" else {"type": event.type})
        # Saved only after the whole answer arrived, so no partial text is stored.
        done = save(result[0])
    except LlmError as exc:
        yield _event({"type": "error", "message": str(exc)})
        return
    except Exception:
        # The response has already started, so report failures in-band.
        log.exception("LLM stream failed")
        yield _event({"type": "error", "message": "Something went wrong while generating the answer. Please try again."})
        return
    if done is None:
        yield _event({"type": "error", "message": "The paper was removed from the library."})
    else:
        yield _event({"type": "done", **done})


@router.get("/config", response_model=AppConfig)
async def app_config() -> AppConfig:
    ready, hint = await llm_status()
    return AppConfig(
        llm_provider=get_settings().llm_provider,
        llm_model=model_label(),
        llm_ready=ready,
        llm_hint=hint,
    )


@router.post("/papers/{paper_id}/summary")
async def summarize(paper_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    """Generate (or regenerate) a summary of the paper's content and save it."""
    context = await _paper_context(paper_id, db)

    def save(result: StreamResult) -> dict[str, Any] | None:
        with SessionLocal() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                return None
            paper.summary = result.text
            paper.summary_model = result.model
            paper.summary_context = context.kind
            paper.summary_created_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(paper)
            return {"paper": PaperDetail.model_validate(paper).model_dump(mode="json")}

    return _ndjson_response(
        _stream_and_save(context, [{"role": "user", "content": SUMMARY_REQUEST}], save)
    )


@router.get("/papers/{paper_id}/chat", response_model=list[ChatMessageOut])
def chat_history(paper_id: int, db: Session = Depends(get_db)) -> list[ChatMessage]:
    get_paper_or_404(paper_id, db)
    return list(db.scalars(select(ChatMessage).where(ChatMessage.paper_id == paper_id).order_by(ChatMessage.id)))


@router.post("/papers/{paper_id}/chat")
async def ask(paper_id: int, body: AskRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """Answer a question about the paper, with earlier Q&A turns as context."""
    context = await _paper_context(paper_id, db)
    limit = get_settings().llm_history_messages
    recent = list(db.scalars(
        select(ChatMessage).where(ChatMessage.paper_id == paper_id).order_by(ChatMessage.id.desc()).limit(limit)
    ))[::-1]
    # Turns are stored in user/assistant pairs; never start the history mid-pair.
    while recent and recent[0].role != "user":
        recent.pop(0)
    messages = [{"role": m.role, "content": m.content} for m in recent]
    messages.append({"role": "user", "content": body.question})

    def save(result: StreamResult) -> dict[str, Any] | None:
        with SessionLocal() as session:
            if session.get(Paper, paper_id) is None:
                return None
            question = ChatMessage(paper_id=paper_id, role="user", content=body.question)
            answer = ChatMessage(
                paper_id=paper_id, role="assistant", content=result.text,
                model=result.model, context=context.kind,
            )
            session.add_all([question, answer])
            try:
                session.commit()
            except IntegrityError:  # the paper was deleted after the check above
                return None
            return {
                "messages": [
                    ChatMessageOut.model_validate(m).model_dump(mode="json") for m in (question, answer)
                ]
            }

    return _ndjson_response(_stream_and_save(context, messages, save))


@router.delete("/papers/{paper_id}/chat", status_code=status.HTTP_204_NO_CONTENT)
def clear_chat(paper_id: int, db: Session = Depends(get_db)) -> Response:
    get_paper_or_404(paper_id, db)
    db.execute(delete(ChatMessage).where(ChatMessage.paper_id == paper_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
