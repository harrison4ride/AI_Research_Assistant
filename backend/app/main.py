"""FastAPI entry point for the AI Research Assistant backend."""

import html
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import BACKEND_DIR, get_settings
from .db import init_db
from .routers import assistant, papers, search
from .services.cache import prune_cached_papers
from .services.http import close_client


# Show the app's own INFO logs (e.g. LLM token usage) next to uvicorn's.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if (BACKEND_DIR / ".env").exists():
        logging.getLogger(__name__).warning(
            "backend/.env is not read; move its settings into .env in the project root."
        )
    init_db()
    prune_cached_papers()
    pruner = asyncio.create_task(_prune_periodically())
    yield
    pruner.cancel()
    with suppress(asyncio.CancelledError):
        await pruner
    await close_client()


async def _prune_periodically() -> None:
    """Also clean up unsaved papers while the server keeps running (not only at startup)."""
    while True:
        await asyncio.sleep(12 * 3600)
        try:
            await asyncio.to_thread(prune_cached_papers)
        except Exception:
            logging.getLogger(__name__).exception("Pruning unsaved papers failed")


app = FastAPI(title="AI Research Assistant", lifespan=lifespan)
app.include_router(search.router)
app.include_router(papers.router)
app.include_router(assistant.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Production: serve the built frontend from the same origin. The app uses hash
# routing, so "/" is its only page; mounting just /assets (instead of a
# catch-all at "/") leaves /api paths with FastAPI's normal JSON 404/405 handling.
settings = get_settings()
dist = settings.frontend_dist
# A complete build has both; an interrupted build or a wrong FRONTEND_DIST falls
# through to the explanation page below instead of crashing at startup.
frontend_built = (dist / "index.html").is_file() and (dist / "assets").is_dir()

if settings.serve_frontend and frontend_built:

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        # no-cache: after a rebuild the browser must fetch the page that names the new asset hashes.
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(dist / "favicon.svg")

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

else:
    # No UI on this port (development mode, or no usable build). Explain where
    # the app is instead of answering "/" with a bare 404.
    DEV_UI = "<a href='http://localhost:5173'>http://localhost:5173</a>"  # port set in frontend/vite.config.ts
    if not settings.serve_frontend:
        _hint = f"In development mode the app runs at {DEV_UI} (started by <code>make dev</code>)."
    else:
        _hint = (
            f"No frontend build was found in <code>{html.escape(str(dist))}</code>. "
            "Run <code>make build</code> (it builds into <code>frontend/dist</code>) and restart this "
            "server, or check <code>FRONTEND_DIST</code> in <code>.env</code>. "
            f"Alternatively, run <code>make dev</code> and open {DEV_UI}."
        )

    @app.get("/", include_in_schema=False)
    def api_only_index() -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>AI Research Assistant API</title>"
            "<body style='font-family:system-ui;max-width:40rem;margin:3rem auto;line-height:1.5'>"
            "<h1>AI Research Assistant: API server</h1>"
            f"<p>This port serves only the API. {_hint}</p>"
            "<p>API documentation: <a href='/docs'>/docs</a></p></body>"
        )
