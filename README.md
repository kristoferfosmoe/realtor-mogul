# Realtor Mogul

A real-estate investment terminal. Underwrite rentals the way a trader watches
tickers: live IRR, ROIC, cash-on-cash and DSCR as you change assumptions,
sensitivity heatmaps, a watchlist screener, a Markets page tracking rent and
home-value trends by metro, and a Portfolio that tracks what you own: ledger
(bank CSV import, or rent recorded for whole periods at once), rent roll, loan,
market-indexed valuations, and actual returns against the original projection.
A Screener ranks for-sale listings (RentCast or your own Redfin CSV export)
against buy boxes with explained scores. Rent estimates draw on RentCast comps, Zillow,
HUD fair market rents and Census ZIP-level rents.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

```
backend/   FastAPI app + the pure underwriting engine (Python, uv)
  src/mogul/engine/   pro forma, IRR/XIRR, mortgage math, sensitivity. No I/O.
  src/mogul/api/      HTTP routes
  src/mogul/db/       SQLAlchemy models; migrations live in backend/alembic/
  src/mogul/ingest/   market-data sources (Zillow, FRED, HUD, Census) + pipeline (python -m mogul.ingest)
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
make ingest  # pull market data: Zillow, FRED, Census ACS, and HUD if MOGUL_HUD_API_TOKEN is set
make listings  # pull for-sale listings from RentCast (needs an API key; see backend/.env.example)
make rents   # RentCast rent comps for up to 20 listings that pass a buy box (20 API calls)
```

There is no demo data: every number comes from one of these sources or from you. Until
you run `make ingest`, the Markets page is empty, and the Screener only has what you
import. Keys go in `backend/.env` (see `backend/.env.example`):

| Setting | Needed for | Where to get it |
|---|---|---|
| `MOGUL_HUD_API_TOKEN` | HUD fair market rents | Free: https://www.huduser.gov/hudapi/public/register |
| `MOGUL_CENSUS_API_KEY` | Optional; raises Census rate limits | Free: https://api.census.gov/data/key_signup.html |
| `MOGUL_RENTCAST_API_KEY`, `MOGUL_LISTING_AREAS` | Listings and rent comps | https://app.rentcast.io/app/api |

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
