# Common tasks. Requires uv (Python) and npm (Node.js).
.PHONY: install dev backend frontend build start

install:            ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && npm ci

backend:            ## Run the API with auto-reload on :8000 (UI comes from `make frontend`)
	cd backend && SERVE_FRONTEND=false uv run uvicorn app.main:app --reload --port 8000

frontend:           ## Run the Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

# `exec` makes uv and npm the background jobs themselves; both forward the
# signal to uvicorn / vite. Only these two jobs are signalled (never `kill 0`,
# which would also hit whatever started make).
dev:                ## Run backend and frontend together; Ctrl+C stops both
	@trap 'trap - INT TERM EXIT; kill $$(jobs -p) 2>/dev/null' INT TERM EXIT; \
	(cd backend && SERVE_FRONTEND=false exec uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && exec npm run dev) & \
	wait

build:              ## Build the frontend into frontend/dist
	cd frontend && npm run build

start: build        ## Production mode: one process serving the API and the built UI on :8000
	cd backend && uv run uvicorn app.main:app --port 8000
