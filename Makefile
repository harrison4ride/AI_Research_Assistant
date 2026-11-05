# Common tasks. Requires uv (Python) and Node.js 22.13 or later with npm; see INSTALL.md.
.PHONY: install check dev backend frontend build start test test-backend test-frontend test-e2e \
	coverage coverage-backend coverage-frontend

install:            ## Check requirements, install all packages, create .env
	./scripts/setup.sh

check:              ## Report which requirements are met; changes nothing
	./scripts/setup.sh --check

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

# Tests never call a real LLM or an outside service (test-e2e downloads Chromium once);
# see docs/TESTING.md. The end-to-end tests use port 8765 (E2E_PORT).
test: test-backend test-frontend test-e2e  ## Run every test suite

test-backend:       ## Backend tests (pytest): API, PDF extraction, LLM plumbing with fakes
	cd backend && uv run pytest

test-frontend:      ## Frontend tests (Vitest + React Testing Library, mocked API)
	cd frontend && npm test

test-e2e:           ## Browser tests (Playwright) against the built app with fake search APIs and LLM
	cd frontend && npm run test:e2e:install && npm run test:e2e

coverage: coverage-backend coverage-frontend  ## Line and branch coverage of the backend and frontend tests

coverage-backend:   ## Backend coverage (coverage.py): table in the terminal, HTML in backend/htmlcov/
	cd backend && uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=html \
		--cov-report=json:htmlcov/coverage.json
	@# The table's TOTAL combines statements and branches; print the two separately.
	@cd backend && uv run python -c 'import json; t = json.load(open("htmlcov/coverage.json"))["totals"]; \
		print("Backend coverage: lines {:.1f}% ({}/{}), branches {:.1f}% ({}/{})".format( \
		t["percent_statements_covered"], t["covered_lines"], t["num_statements"], \
		t["percent_branches_covered"], t["covered_branches"], t["num_branches"]))'

coverage-frontend:  ## Frontend coverage (V8): table in the terminal, HTML in frontend/coverage/
	cd frontend && npm run test:coverage
