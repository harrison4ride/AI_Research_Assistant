"""A stand-in for the LLM, used by the `fake_llm` fixture (see conftest.py)."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.services import llm

RESET = object()  # in a fake reply: the model restarted (fallback), so the client drops its text


@dataclass
class LlmCall:
    context: llm.PaperContext
    messages: list[dict]
    model: str

    @property
    def paper(self) -> str:
        """The <paper> block the model was given."""
        return self.context.paper

    @property
    def prompt(self) -> str:
        """The newest user turn."""
        return self.messages[-1]["content"]


@dataclass
class _Reply:
    chunks: Callable[[LlmCall], list]
    model: str | None = None
    stop_reason: str = "end_turn"
    error: BaseException | None = None
    before: Callable[[LlmCall], None] | None = None


@dataclass
class FakeLLM:
    """Stands in for the model.

    Replaces llm.stream_reply (summaries, answers, section summaries) and
    llm.extract_metadata (uploads), and records what the app sent. Unless a test
    queues replies, every call answers "This is a fake answer.".
    """

    model: str = "fake-model-1"
    calls: list[LlmCall] = field(default_factory=list)
    metadata: llm.ExtractedMetadata | None = None
    metadata_requests: list[str] = field(default_factory=list)
    _replies: list[_Reply] = field(default_factory=list)

    def reply(self, *chunks, model: str | None = None, stop_reason: str = "end_turn",
              before: Callable[[LlmCall], None] | None = None) -> None:
        """Queue an answer streamed as `chunks` (strings, or RESET)."""
        self._replies.append(_Reply(lambda call: list(chunks), model, stop_reason, None, before))

    def reply_with(self, make_text: Callable[[LlmCall], str]) -> None:
        """Queue an answer computed from the call (e.g. from the prompt)."""
        self._replies.append(_Reply(lambda call: [make_text(call)]))

    def fail(self, error: BaseException, *after: str) -> None:
        """Queue a failure, raised after streaming the `after` chunks."""
        self._replies.append(_Reply(lambda call: list(after), error=error))

    async def stream_reply(self, context, messages, result, model=None):
        chosen = llm.resolve_model(model)  # the same validation as the real call
        call = LlmCall(context, [dict(m) for m in messages], chosen)
        self.calls.append(call)
        reply = self._replies.pop(0) if self._replies else _Reply(lambda call: ["This is a fake ", "answer."])
        if reply.before:
            reply.before(call)
        text = ""
        for chunk in reply.chunks(call):
            if chunk is RESET:
                text = ""
                yield llm.StreamEvent("reset")
            else:
                text += chunk
                yield llm.StreamEvent("text", chunk)
        if reply.error:
            raise reply.error
        result.append(llm.StreamResult(text=text, model=reply.model or self.model, stop_reason=reply.stop_reason))

    async def extract_metadata(self, first_pages: str) -> llm.ExtractedMetadata | None:
        self.metadata_requests.append(first_pages)
        return self.metadata
