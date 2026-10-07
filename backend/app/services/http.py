"""Shared HTTP helpers for calling external services."""

import httpx

USER_AGENT = "AI-Research-Assistant/0.1 (course project)"

_client: httpx.AsyncClient | None = None


class UpstreamError(Exception):
    """An external service failed or returned something unusable."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def get_client() -> httpx.AsyncClient:
    """One pooled client for the whole app, so connections are reused across requests."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
