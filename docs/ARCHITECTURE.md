# Architecture

Realtor Mogul manages a portfolio of income properties. It follows market rent
trends, pulls residential and commercial properties listed for sale, runs
underwriting math (IRR, ROIC, cash-on-cash and more) and recommends what to buy.
The UI is modeled on a trading terminal: dark, dense, monospaced numbers, and
green or red coloring against target returns.

## Decisions (defaults until revisited)

| Topic | Decision |
|---|---|
| Users | Single user or small team. Auth is added before any public deployment. |
| Stack | Python 3.11 + FastAPI + SQLAlchemy/Alembic backend; Next.js (App Router) + TypeScript frontend. |
| Database | PostgreSQL (SQLite for zero-setup local dev and tests). PostGIS gets added along with geography. |
| Data sources | Free/bulk sources first (Zillow ZORI, HUD FMR, Census ACS, FRED), then one paid API for comps and listings. No scraping of sites whose terms forbid it. |
| Property types | Residential 1–4 units first. Commercial gets its own rent-roll model later. |
| Returns | Pre-tax. Depreciation and after-tax IRR come later. |

## System overview

```
 Web (Next.js)  ──/api/*──▶  API (FastAPI)  ──▶  PostgreSQL
                               │                    ▲
                               ▼                    │
                         engine (pure)       workers (ingestion, scoring)
                                                    │
                                                    ▼
                                    source adapters + raw object storage
```

The browser only talks to the Next.js origin, and Next proxies `/api/*` to FastAPI.
TypeScript types are generated from FastAPI's OpenAPI schema
(`npm run gen:api`), and CI fails if they drift.

## Modules

### `mogul.engine` (built)
A pure underwriting library: no database, network or clock access, and it is
deterministic and fully unit-tested. The API, future background workers and
notebooks all use it.

- `Deal`: every assumption, validated by pydantic (acquisition, income, fixed
  and variable opex, growth, exit, optional `Financing`).
- `analyze(deal)` returns an `Analysis`: a yearly schedule (`YearRow`), the sale (`Exit`),
  levered and unlevered cash flows, and `Metrics`.
- `sensitivity(deal, x_field, xs, y_field, ys, metric)` returns a two-way grid.
- `irr`, `xirr`, `npv`, `xnpv`: a bracketing solver (bisection) that never diverges.
  `xirr` is for dated flows from real transactions.

**Conventions**
- Year 0 is the acquisition. Years 1..N are operations, and the property is sold at the end of year N.
- Rent and other income grow at `rent_growth`, fixed expenses grow at `expense_growth`,
  and variable expenses (management, maintenance, capex reserve) are a percentage of effective gross income.
- Capex reserves count as an operating expense, so **NOI is after reserves**.
- The loan is sized off the purchase price, and rehab is paid with equity.
- The exit value is `(ARV or price) × (1 + appreciation)^N`. If `exit_cap_rate` is set,
  it is year N+1 NOI ÷ `exit_cap_rate` instead.
- Projections use floats (they are estimates). The future ledger of real
  transactions uses exact `Decimal`/`NUMERIC`.

**Metric definitions**

| Metric | Definition |
|---|---|
| Cap rate | Year-1 NOI ÷ purchase price |
| ROIC | Year-1 NOI ÷ total capital (price + closing + rehab), i.e. yield on cost, unlevered |
| Cash-on-cash | Year-1 cash flow after debt service ÷ equity invested |
| DSCR | Year-1 NOI ÷ year-1 debt service |
| Levered IRR | IRR of equity flows: −equity, annual cash flow, + net sale proceeds |
| Unlevered IRR | IRR of all-cash flows: −total capital, NOI, + sale net of costs |
| Equity multiple | Σ cash returned ÷ equity invested |
| Break-even occupancy | Occupancy at which income covers fixed opex and debt service |

### API (built)
- `GET /analysis/template` returns a starting deal. `POST /analysis` and `POST /analysis/sensitivity` run the engine.
- `/deals` supports CRUD for the watchlist. Inputs are stored as a JSON document (the
  model can change without a migration for every new assumption), and metrics are always
  recomputed on read.

### Web (built)
- **Analyzer** (`/`): the deal "ticket" (inputs) on the left. In the center, a live quote
  (levered IRR shown like a last price, with the change against the saved or opened
  version), KPI tiles, an equity-build chart (TradingView lightweight-charts) with annual
  cash flow shown as volume bars, and the pro forma table. On the right, a sensitivity
  heatmap and the exit breakdown. The analysis re-runs 150 ms after each edit.
- **Watchlist** (`/watchlist`): a sortable screener with a BUY/WATCH/PASS signal
  against target returns. Watchlist deals also scroll across the ticker tape.
- The targets and signal logic live in `web/src/lib/metrics.ts`. The recommendations
  module will replace them.

### Market data (next)
- `geography` (ZIP, county, MSA, tract; PostGIS shapes).
- `market_metric(geo_id, date, metric, segment, value, source_id, ingested_at)`: one
  long time-series table. `segment` holds property type and bedroom count, and `metric`
  holds values such as median rent, rent index and vacancy.
- Every raw download is saved to object storage before parsing, so history can be
  re-parsed and we build our own history for sources that only publish "current" values.
- Derived series (YoY, 3/5-year compound annual growth, rent-to-price) feed the engine's
  default growth assumptions.

### Ingestion workers (next)
Each source is an adapter: `fetch → store raw → parse → normalize → upsert`, with
scheduled runs, retries, rate limits and an `ingestion_run` log table. A Postgres-backed
job queue avoids adding Redis early on. Playwright is available for sources that
need a browser and allow automated access.

| Need | Sources |
|---|---|
| Rent trends | Zillow ZORI CSVs, Apartment List, HUD FMR API, Census ACS, FRED |
| Rent comps | RentCast API |
| Residential listings | RentCast / ATTOM, or MLS via RESO Web API (needs broker/IDX agreement) |
| Commercial listings | Paid (Crexi, CoStar, Reonomy) or manual/CSV import. LoopNet and Crexi forbid scraping. |

### Listings, portfolio, recommendations (later)
- **Listings:** for-sale listings plus their status and price history, duplicates merged
  across sources, a rent estimate (market rent by ZIP and bedroom count, adjusted with
  comps, a model later), and an automatic pro forma.
- **Portfolio:** owned properties, units, leases, loans, an exact-decimal ledger (CSV
  import), and actual vs. pro forma returns (`xirr` on real dated flows).
- **Recommendations:** a user-defined buy box filters listings, each gets a pro forma,
  then a score (returns, market rent trend, risk, portfolio concentration), then a
  ranking. Every result shows *why*. Alerts fire when a new listing matches.

## Roadmap

1. ✅ Foundation: monorepo, CI, Docker Compose, migrations.
2. ✅ Underwriting engine, deal analyzer, watchlist.
3. Market rent ingestion + Markets page (rent-trend charts, growth defaults).
4. Portfolio tracking (ledger, actual vs. projected).
5. Listings ingestion, rent estimation, screener and recommendations, alerts.
6. Commercial underwriting (rent roll, NNN, TI/LC), Monte Carlo, after-tax returns, auth.
