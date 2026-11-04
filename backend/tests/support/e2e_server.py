"""Run the real app for the Playwright end-to-end tests, with fake outside services.

    uv run python tests/support/e2e_server.py --port 8765 --run-dir /tmp/ra-e2e-xyz

frontend/e2e/support/serve.mjs starts this (after building the UI into RUN_DIR/dist)
and deletes RUN_DIR afterwards. What is real and what is fake:

- Real: the FastAPI app, SQLite, PDF extraction, the NDJSON streaming, and the
  Claude Code provider's subprocess handling. The built UI is served on the same port.
- Fake: OpenAlex and arXiv (a local server with canned results), and the `claude`
  CLI (tests/support/fake_claude.py), so no model is ever called. No canned result
  links to a PDF on the internet.
- The repository's .env is not read; the database lives in RUN_DIR/data.
- For the tests only, POST /__e2e__/reset deletes every paper (saved or only opened),
  its conversation and PDF, and forgets cached search results, so that no test sees
  what an earlier one left behind.
"""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TESTS_DIR.parent), str(TESTS_DIR)]

from support import fake_claude  # noqa: E402
from support.isolation import isolate_settings  # noqa: E402
from support.upstream import arxiv_entry, arxiv_feed, openalex_page, openalex_work  # noqa: E402

# What the fake OpenAlex returns for any query. No PDF links, so nothing is downloaded.
WORKS = [
    openalex_work(
        work_id="W3027879771",
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors=("Patrick Lewis", "Ethan Perez", "Aleksandra Piktus"),
        year=2020,
        abstract="Large pre-trained language models have been shown to store factual knowledge in their "
                 "parameters. We explore a fine-tuning recipe for retrieval-augmented generation.",
        doi="https://doi.org/10.48550/arxiv.2005.11401",
        landing_page="https://arxiv.org/abs/2005.11401",
        pdf_url=None,
        venue="Neural Information Processing Systems",
    ),
    openalex_work(
        work_id="W3099700870",
        title="Dense Passage Retrieval for Open-Domain Question Answering",
        authors=("Vladimir Karpukhin", "Barlas Oğuz"),
        year=2020,
        abstract="Open-domain question answering relies on efficient passage retrieval to select candidate "
                 "contexts. We show that retrieval can be practically implemented using dense representations.",
        doi="https://doi.org/10.18653/v1/2020.emnlp-main.550",
        landing_page="https://aclanthology.org/2020.emnlp-main.550",
        pdf_url=None,
        venue="Empirical Methods in Natural Language Processing",
    ),
]
# The PDF link is on a documentation-only address (RFC 5737): the app refuses it as
# non-public without connecting, so opening this result never uses the internet.
ARXIV_PDF_URL = "http://192.0.2.10/pdf/1706.03762v7"
ARXIV_FEED = arxiv_feed([arxiv_entry(pdf_url=ARXIV_PDF_URL)], total=1)


class FakeSearchApis(BaseHTTPRequestHandler):
    """OpenAlex at /openalex/works and arXiv at /arxiv/query. Queries with "fake-500"
    fail and queries with "fake-empty" find nothing, so tests can trigger both."""

    def do_GET(self):
        url = urlsplit(self.path)
        params = parse_qs(url.query)
        query = (params.get("search") or params.get("search_query") or [""])[0]
        if "fake-500" in query:
            self._send(500, b"{}", "application/json")
        elif url.path == "/openalex/works":
            works = [] if "fake-empty" in query else WORKS
            self._send(200, json.dumps(openalex_page(works)).encode(), "application/json")
        elif url.path == "/arxiv/query":
            body = arxiv_feed([], total=0) if "fake-empty" in query else ARXIV_FEED
            self._send(200, body.encode(), "application/atom+xml")
        else:
            self._send(404, b"{}", "application/json")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the test output quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True, help="temporary folder; the UI build is in dist/")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()

    fake_cli = fake_claude.install(run_dir / "bin")

    # Settings, before the app reads them.
    isolate_settings(
        data_dir=run_dir / "data",
        claude_code_path=fake_cli,
        frontend_dist=run_dir / "dist",
        serve_frontend="true",
    )

    fake_apis = ThreadingHTTPServer(("127.0.0.1", 0), FakeSearchApis)
    threading.Thread(target=fake_apis.serve_forever, daemon=True).start()
    from app.services import arxiv, openalex

    openalex.API_URL = f"http://127.0.0.1:{fake_apis.server_port}/openalex/works"
    arxiv.API_URL = f"http://127.0.0.1:{fake_apis.server_port}/arxiv/query"
    arxiv._MIN_INTERVAL = 0.0

    import uvicorn

    from app.main import app, frontend_built

    if not frontend_built:
        sys.exit(f"No frontend build in {run_dir / 'dist'}")
    add_reset_route(app)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def add_reset_route(app) -> None:
    """POST /__e2e__/reset: forget every paper, conversation, PDF, and cached search."""
    import shutil

    from fastapi import Response
    from sqlalchemy import delete

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import ChatMessage, Paper
    from app.routers import search

    @app.post("/__e2e__/reset", include_in_schema=False)
    def reset() -> Response:
        with SessionLocal() as db:
            db.execute(delete(ChatMessage))
            db.execute(delete(Paper))
            db.commit()
        shutil.rmtree(get_settings().pdf_dir, ignore_errors=True)
        search._cache.clear()
        return Response(status_code=204)


if __name__ == "__main__":
    main()
