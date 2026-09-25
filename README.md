# Realtor Mogul

A real-estate investment terminal. Underwrite rentals the way a trader watches
tickers: live IRR, ROIC, cash-on-cash and DSCR as you change assumptions,
sensitivity heatmaps, and a watchlist screener. Market rent trends, listings
and recommendations are next. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

```
backend/   FastAPI app + the pure underwriting engine (Python, uv)
  src/mogul/engine/   pro forma, IRR/XIRR, mortgage math, sensitivity. No I/O.
  src/mogul/api/      HTTP routes
  src/mogul/db/       SQLAlchemy models; migrations live in backend/alembic/
web/       Next.js terminal UI (TypeScript), proxies /api/* to the backend
docs/      architecture and decisions
```

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node 22.

```sh
make setup   # install deps, create a local SQLite DB
make api     # http://localhost:8000  (OpenAPI docs at /docs)
make web     # http://localhost:3000
```

Or run the whole stack on Postgres with Docker:

```sh
docker compose up --build   # web on :3000, api on :8000, postgres on :5432
```

## Develop

```sh
make test    # backend tests
make lint    # ruff, mypy, eslint, tsc
make types   # regenerate web/src/lib/api-schema.d.ts after changing API models
```

New migration: `cd backend && uv run alembic revision --autogenerate -m "..."`.
Set `MOGUL_DATABASE_URL` to point anywhere other than the default `sqlite:///./mogul.db`.
