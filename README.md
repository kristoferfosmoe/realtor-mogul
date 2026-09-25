# Realtor Mogul

A real-estate investment terminal. Underwrite rentals the way a trader watches
tickers: live IRR, ROIC, cash-on-cash and DSCR as you change assumptions,
sensitivity heatmaps, a watchlist screener, a Markets page tracking rent and
home-value trends by metro, and a Portfolio that tracks what you own: ledger
(with bank CSV import), rent roll, loan, market-indexed valuations, and actual
returns against the original projection. A Screener ranks for-sale listings
(RentCast or your own Redfin CSV export) against buy boxes with explained scores.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

```
backend/   FastAPI app + the pure underwriting engine (Python, uv)
  src/mogul/engine/   pro forma, IRR/XIRR, mortgage math, sensitivity. No I/O.
  src/mogul/api/      HTTP routes
  src/mogul/db/       SQLAlchemy models; migrations live in backend/alembic/
  src/mogul/ingest/   market-data source adapters + pipeline (python -m mogul.ingest)
  src/mogul/markets/  time-series analytics (YoY, CAGR, gross yield) and queries
  src/mogul/portfolio/ owned properties: ledger categories, CSV import, performance
  src/mogul/listings/ for-sale listings: sources, price history, rent estimates, screening
web/       Next.js terminal UI (TypeScript), proxies /api/* to the backend
docs/      architecture and decisions
```

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node 22.

```sh
make setup   # install deps, create a local SQLite DB
make api     # http://localhost:8000  (OpenAPI docs at /docs)
make web     # http://localhost:3000
make ingest  # pull market data: Zillow rents/home values + FRED indicators
make listings  # pull for-sale listings from RentCast (needs an API key; see backend/.env.example)
```

No network access to Zillow/FRED/RentCast? `make demo-data` loads a clearly
labeled synthetic set of market data and listings so every page has something to
show; the next real fetch replaces it.

Or run the whole stack on Postgres with Docker:

```sh
docker compose up --build   # web :3000, api :8000, postgres :5432, daily ingest worker
```

## Develop

```sh
make test    # backend tests
make lint    # ruff, mypy, eslint, tsc
make types   # regenerate web/src/lib/api-schema.d.ts after changing API models
```

New migration: `cd backend && uv run alembic revision --autogenerate -m "..."`.
Set `MOGUL_DATABASE_URL` to point anywhere other than the default `sqlite:///./mogul.db`.
