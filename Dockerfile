# Single-container deployment: build the React app, then serve it and the API
# from one FastAPI process. Data (SQLite DB + PDFs) lives in /data; mount a volume there.

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
COPY backend/app ./app
COPY --from=frontend /app/frontend/dist /app/frontend/dist

ENV DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend/dist
VOLUME /data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
