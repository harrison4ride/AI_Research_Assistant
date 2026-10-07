"""FastAPI entry point for the AI Research Assistant backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers import assistant, papers, search
from .services.http import close_client


# Show the app's own INFO logs (e.g. LLM token usage) next to uvicorn's.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    await close_client()


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
if settings.serve_frontend and (dist := settings.frontend_dist).is_dir():

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        # no-cache: after a rebuild the browser must fetch the page that names the new asset hashes.
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(dist / "favicon.svg")

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
