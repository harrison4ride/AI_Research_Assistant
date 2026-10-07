"""FastAPI entry point for the AI Research Assistant backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
