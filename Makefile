.PHONY: setup api web test lint types ingest listings rents

setup:          ## Install backend and web dependencies, create the local DB
	cd backend && uv sync && uv run alembic upgrade head
	cd web && npm install

api:            ## Run the API on :8000 with reload
	cd backend && uv run uvicorn mogul.api.app:app --reload --port 8000

web:            ## Run the web app on :3000 (proxies /api to :8000)
	cd web && npm run dev

test:           ## Backend tests
	cd backend && uv run pytest

lint:           ## All static checks
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd web && npm run lint && npm run typecheck

types:          ## Regenerate web API types from the backend's OpenAPI schema
	cd web && npm run gen:api

ingest:         ## Download Zillow, FRED, Census ACS and (with MOGUL_HUD_API_TOKEN) HUD data
	cd backend && uv run python -m mogul.ingest run all

listings:       ## Fetch for-sale listings from RentCast (MOGUL_RENTCAST_API_KEY, MOGUL_LISTING_AREAS)
	cd backend && uv run python -m mogul.ingest listings rentcast

rents:          ## RentCast rent comps for up to 20 listings that pass a buy box (20 API calls)
	cd backend && uv run python -m mogul.ingest rents --limit 20
