"""Sample papers and small helpers for calling the API in tests."""

import json

from fastapi.testclient import TestClient
from httpx import Response

from . import pdfs

# A search result as the arXiv client returns it.
ARXIV_META = {
    "source": "arxiv",
    "external_id": "1706.03762",
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
    "year": 2017,
    "abstract": (
        "The dominant sequence transduction models are based on complex recurrent or convolutional "
        "neural networks. We propose a new simple network architecture, the Transformer, based solely "
        "on attention mechanisms."
    ),
    "url": "https://arxiv.org/abs/1706.03762",
    "pdf_url": None,  # no download in tests that don't ask for one
    "venue": "arXiv",
    "doi": "10.48550/arXiv.1706.03762",
}

# The same paper as OpenAlex returns it (other source, other id, same arXiv DOI).
OPENALEX_META = {
    "source": "openalex",
    "external_id": "W2741809807",
    "title": "Attention is All you Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "year": 2017,
    "abstract": "The dominant sequence transduction models are based on complex recurrent networks.",
    "url": "https://arxiv.org/abs/1706.03762",
    "pdf_url": None,
    "venue": "arXiv (Cornell University)",
    "doi": "10.48550/arxiv.1706.03762",
}

# A different paper.
BERT_META = {
    "source": "openalex",
    "external_id": "W2963341956",
    "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
    "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
    "year": 2019,
    "abstract": "We introduce a new language representation model called BERT.",
    "url": "https://aclanthology.org/N19-1423",
    "pdf_url": None,
    "venue": "NAACL",
    "doi": "10.18653/v1/N19-1423",
}


def meta(base: dict, **changes) -> dict:
    return {**base, **changes}


def save(client: TestClient, paper_meta: dict) -> dict:
    response = client.post("/api/papers", json=paper_meta)
    assert response.status_code in (200, 201), response.text
    return response.json()


def open_unsaved(client: TestClient, paper_meta: dict) -> dict:
    response = client.post("/api/papers/open", json=paper_meta)
    assert response.status_code in (200, 201), response.text
    return response.json()


def upload(client: TestClient, data: bytes | None = None, name: str = "paper.pdf",
           content_type: str = "application/pdf") -> Response:
    return client.post("/api/papers/upload", files={"file": (name, pdfs.sample_pdf() if data is None else data,
                                                             content_type)})


def upload_sample(client: TestClient) -> dict:
    """Upload the sample paper (full text available) and return the new library entry."""
    response = upload(client)
    assert response.status_code == 201, response.text
    return response.json()


def events(response: Response) -> list[dict]:
    """The events of a newline-delimited JSON stream (summary and chat endpoints)."""
    assert response.headers["content-type"].startswith("application/x-ndjson"), response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def streamed_text(stream: list[dict]) -> str:
    """The answer text a client would show: text deltas, minus anything before a reset."""
    text = ""
    for event in stream:
        if event["type"] == "reset":
            text = ""
        elif event["type"] == "text":
            text += event["text"]
    return text
