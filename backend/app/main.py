"""FastAPI entry point for the AI Research Assistant backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import search
from .services.http import close_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_client()


app = FastAPI(title="AI Research Assistant", lifespan=lifespan)
app.include_router(search.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
