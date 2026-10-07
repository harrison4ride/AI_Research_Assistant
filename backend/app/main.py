"""FastAPI entry point for the AI Research Assistant backend."""

from fastapi import FastAPI

app = FastAPI(title="AI Research Assistant")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
