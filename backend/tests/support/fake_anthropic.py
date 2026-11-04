"""A stand-in for the parts of anthropic.AsyncAnthropic that the app uses (LLM_PROVIDER=api).

Install it with monkeypatch.setattr(llm, "get_client", lambda: fake). It records the
parameters of every call and answers with the stream or parse result a test set.
"""

from types import SimpleNamespace


class FakeMessageStream:
    def __init__(self, events, final, error=None):
        self.events, self.final, self.error = events, final, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def __aiter__(self):
        for event in self.events:
            yield event
        if self.error:
            raise self.error

    async def get_final_message(self):
        return self.final


class FakeAnthropic:
    def __init__(self):
        self.stream = None  # the FakeMessageStream to return next
        self.streams: list[FakeMessageStream] = []  # or several, one per call
        self.stream_error = None
        self.stream_params: list[dict] = []
        self.parse_result = None
        self.parse_error = None
        self.parse_params: list[dict] = []
        self.options: dict | None = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream, parse=self._parse))

    def with_options(self, **options):
        self.options = options
        return self

    def _stream(self, **params):
        self.stream_params.append(params)
        if self.stream_error:
            raise self.stream_error
        return self.streams.pop(0) if self.streams else self.stream

    async def _parse(self, **params):
        self.parse_params.append(params)
        if self.parse_error:
            raise self.parse_error
        return self.parse_result


def text_event(text):
    return SimpleNamespace(type="text", text=text)


def fallback_event():
    return SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="fallback"))


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def final(*blocks, stop_reason="end_turn", model="claude-opus-5"):
    usage = SimpleNamespace(input_tokens=10, cache_read_input_tokens=0, cache_creation_input_tokens=8, output_tokens=4)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, model=model, usage=usage)


def answer(text, model="claude-opus-5", stop_reason="end_turn"):
    """A stream that sends `text` in two pieces and ends normally."""
    half = len(text) // 2
    return FakeMessageStream([text_event(text[:half]), text_event(text[half:])],
                             final(text_block(text), stop_reason=stop_reason, model=model))
