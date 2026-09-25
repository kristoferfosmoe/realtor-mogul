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
| Database | PostgreSQL (SQLite for zero-setup local dev and tests). PostGIS gets added once ZIP/tract shapes are needed. |
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

### Market data (built)
Tables:
- `geography`: the country, metros (MSAs) and ZIPs (ZCTAs). A metro's name follows
  Zillow's style ("Austin, TX"). HUD and Census metro titles are shortened to it (first
  principal city, first state: "Memphis, TN-MS-AR Metro Area" becomes "Memphis, TN"), so
  their series land on the same place as Zillow's. `external_ids` keeps per-source ids
  (Zillow RegionID, CBSA code, HUD FMR area code).
- `market_series`: one series per `(source, source_key)`, e.g. Zillow's rent index for
  Austin, tagged with `metric`, `segment` (e.g. bedroom count), `unit` and `frequency`.
- `market_observation(series_id, date, value)`: the history. Re-running an ingest
  updates values in place rather than adding duplicates, so revised numbers overwrite old ones.
- `ingestion_run`: every attempt, with status, counts, the raw-archive path and any error.

Metrics and units: `rent_index` (USD/mo, ZORI), `home_value` (USD, ZHVI),
`mortgage_rate_30y` and `rental_vacancy` (decimal rates, like the engine), `cpi_rent`
(an index, shown as YoY), `fair_market_rent` (USD/mo, HUD, segments `0br`–`4br`) and
`median_gross_rent` (USD/mo, Census ACS).

`mogul.markets.analytics` holds pure time-series math: YoY, 3/5-year compound annual
growth (month-end aware), latest-on-or-before lookups for weekly and quarterly series,
and gross yield (rent × 12 ÷ home value). Each metric comes from one source, so a place
has at most one series per metric and segment.

There is no demo or synthetic data. Every number on screen came from a source in the
table below or from the user. Migration 0005 deletes demo data left by earlier versions.

API: `GET /markets` (screener rows with stats and a 24-month sparkline),
`GET /markets/{id}` (full history, plus the latest HUD and Census rents as
`benchmarks`), `GET /markets/indicators` (national macro for the
ticker tape), `GET /markets/sources` (run log and attributions).

UI: the **Markets** page has a market-watch list (sort by size, rent YoY or yield), a
quote header, a rent vs. home-value chart with 1Y–MAX ranges, published rents (HUD fair
market rents by bedroom and the Census median, each as a % of Zillow's typical rent), a
year-by-year table, a
US macro panel and data-source health. The analyzer can apply a market's 5-year compound
growth rates to a deal (or start one with `/?market=<id>`) and use the current 30-year
mortgage rate.

### Ingestion (built)
`python -m mogul.ingest run {zillow|fred|hud|census|all}` (or `make ingest`; `all` skips
sources that are not configured and says why). Each source is an
adapter with `fetch()` (download) and `parse()` (to `ParsedSeries`). The pipeline archives
the raw files under `MOGUL_RAW_DATA_DIR/<source>/<timestamp>/` before parsing, upserts,
and logs the run. A failed fetch is recorded on the run and leaves existing data untouched.
`reparse <source> <folder>` rebuilds from an archive. In Compose, an `ingest` service runs
it daily.

| Source | Series | Notes |
|---|---|---|
| Zillow Research CSVs | ZORI rent, ZHVI home value; US + top `MOGUL_ZILLOW_MAX_METROS` metros | Free with attribution |
| FRED CSV export (no key) | 30Y mortgage (PMMS), CPI rent of primary residence, rental vacancy | Public; attribution shown |
| HUD USER FMR API | Fair market rents, studio–4BR, every metro FMR area; last `MOGUL_HUD_FMR_YEARS` fiscal years | Free token in `MOGUL_HUD_API_TOKEN`. One `statedata` call per state and year. A CBSA split into several FMR areas keeps its principal area |
| Census ACS 5-year API | Median gross rent (B25064) for the US, metro areas and every ZIP (ZCTA); last `MOGUL_ACS_YEARS` vintages | Key optional (`MOGUL_CENSUS_API_KEY`). About 33,000 ZIP series. ZIPs only from the 2020 vintage on |

How to read them: FMRs are HUD's 40th-percentile *gross* rent (rent plus utilities) and
set Section 8 payment standards. FY N takes effect October 1 of N-1, the date stored. ACS
medians cover every renter, including long-time tenants, so they run below asking rents.
They are used for a ZIP's position relative to its metro, not as a rent level. A vintage
labeled Y covers Y-4 to Y and is dated December 31 of Y.

Listings, rent comps and commercial sources are covered below. Next: tract-level ACS
and a ZIP→CBSA crosswalk so suburbs match their metro.

### Portfolio (built)
Tables (money is exact `NUMERIC(14,2)`; it records real transactions):
- `property`: purchase (date, price, closing, rehab), optional sale, `market_id` (for
  valuation indexing) and `deal_id` (the watchlist underwriting, for actual vs. projected).
- `loan`: one fixed-rate amortizing loan per property. The balance and scheduled payments
  come from the engine's mortgage math.
- `lease`: the rent roll. Occupancy and scheduled rent are read from active leases.
- `ledger_transaction`: signed amounts (+ in, − out) with a category. CSV imports store
  a hash per line, so re-importing the same statement skips lines already imported.
- `valuation`: appraisals and estimates.

`mogul.portfolio`:
- `categories`: income / operating / capital / debt service / transfer / uncategorized,
  plus keyword rules that guess a category from a bank description.
- `statement`: CSV parser for bank and property-manager exports (signed Amount or
  Debit/Credit columns, US or ISO dates, `$1,234` and `(12.00)` style amounts).
- `rent_schedule`: expands "rent of X/month from month A to month B" (flat or from a
  lease, optional yearly step-up) into one ledger line per month. The API endpoint
  `POST /portfolio/properties/{id}/transactions/rent-range`:
  - **Preview:** `dry_run` returns every month without saving anything.
  - **Duplicates:** each line carries a per-source, per-month hash, so re-running never
    double-records. It can also skip months that already hold any rent.
  - **Limits:** stops at the current month and covers up to 600 months per range.
  - **Undo:** `bulk-delete` removes the lines it created.
- `performance` (pure, given an as-of date):
  - **NOI** = income − operating expenses. Capex, debt service and uncategorized lines sit
    below NOI but count in cash flow; owner transfers are ignored.
  - **Debt service:** if the ledger has no mortgage payments, scheduled payments are
    imputed (flagged in the UI).
  - **T12:** trailing twelve months, annualized when the history is shorter.
  - **Value:** the latest valuation (the purchase price is the first), carried forward
    with the market's home-value index, or the national index when the market has none.
  - **IRR:** XIRR of −equity at purchase, then monthly net cash, then terminal equity.
    Terminal equity is the actual sale, or a **mark-to-market** sale today at estimated
    value less 6% selling costs. Not shown until 6 months of history.
- `service`: loads the database rows into the pure model, compares T12 actuals with the
  linked deal's projection for the same hold year, and sums monthly rows into the
  portfolio equity curve.

API under `/portfolio`: portfolio summary; property CRUD plus `from-deal/{id}` (copies
price, costs and loan from a watchlist deal and marks it owned); leases; transactions
(add, patch category, delete, CSV import); valuations.

UI:
- **Portfolio:** net equity quote, KPIs, a value/debt/equity chart with monthly
  cash-flow bars, a positions table, and allocation by market and type.
- **Property page:** KPIs with data-quality warnings, chart, actual vs. projected,
  ledger (add, paste/upload CSV, recategorize inline, filter uncategorized), rent roll,
  loan and valuations.

### Listings and screener (built)
Tables: `listing` (one row per source listing; `address_key` is a normalized address
for spotting the same property across sources; `rent_override` is set by the user),
`listing_event` (listed / price_change / pending / sold / delisted history) and
`buy_box` (criteria + assumptions as JSON documents, plus `last_viewed_at` for alerts).

Sources (`mogul.listings.sources`), run by `python -m mogul.ingest listings …`:

| Source | How | Notes |
|---|---|---|
| RentCast `/v1/listings/sale` | `MOGUL_RENTCAST_API_KEY` + `MOGUL_LISTING_AREAS` | Full sweep per city: listings missing from a sweep are marked delisted |
| CSV upload | Screener → Import | Redfin "Download All" exports are recognized; generic columns work too, including stated rent and units for multifamily and commercial |

Metro matching is by principal city in the metro's name ("Fort Lauderdale" matches
"Miami-Fort Lauderdale-…, FL"). Suburbs fall back to national data until a ZIP→CBSA
crosswalk is added.

**Rent estimate** (`rent.py`), in order of priority:
1. The user's override (high confidence).
2. Rent stated in the listing (medium).
3. Comparable rentals (medium): RentCast's long-term rent AVM (`/v1/avm/rent/long-term`),
   stored on the listing with its comps (`listing.rent_comps`). Each lookup is a paid
   API call, so it runs only on request: the listing panel's "Get rent comps" button
   (`POST /listings/{id}/rent-comps`), or `python -m mogul.ingest rents --limit N`
   (`make rents`). That command picks active listings with no override, stated rent or
   comps from the last 90 days that pass at least one buy box's hard filters, newest
   first. A 2–4 unit building is looked up as one unit (beds, baths and size ÷ units)
   and multiplied by the number of units.
4. A model estimate (low). It starts from the first of these that exists:
   - the metro's typical rent (ZORI), × a bedroom factor, × 0.9 per unit for multifamily;
   - the metro's HUD fair market rent for that bedroom count (5BR = 4BR × 1.15, HUD's
     rule), for metros Zillow does not cover;
   - the national typical rent, as in the first case.

   Then it applies a size factor clamped to 0.85–1.2 and, when Census covers the ZIP, the
   ZIP's median gross rent ÷ the metro's (or the nation's), clamped to 0.75–1.35. It
   shows its basis, e.g. "Memphis typical rent $1,340 · 3BR ×1.20 · ZIP 38117 ×1.20".

**Screening** (`scoring.py`, pure):
1. **Hard filters:** status, markets, property types, price, beds, days on market, year built.
2. **Underwriting:** each remaining listing goes through the engine using the buy box's
   assumptions. Tax and insurance are a percentage of price; HOA comes from the listing.
   The interest rate is the current 30-year average plus an investor spread. Growth is
   the market's 5-year compound growth, clamped to 0–3% by default, or a fixed rate.
3. **Checks:** IRR, cash-on-cash, DSCR and (optionally) cap rate against the targets.
4. **Score (0–100):**

   | Component | Weight | Measures |
   |---|---|---|
   | Returns | 40 | IRR vs. target |
   | Cash | 20 | Cash-on-cash vs. target |
   | Market | 15 | Market rent growth |
   | Risk | 15 | IRR if rent is 10% lower, DSCR headroom, rent-estimate confidence |
   | Fit | 10 | 1 − share of your portfolio already in that market |

5. **Signal:**
   - STRONG BUY: all targets met and score ≥ 85.
   - BUY: all targets met.
   - WATCH: IRR within 2 points of target, or only one target missed.
   - PASS: everything else.

   Every result carries plain-language reasons.

**Alerts:** BUY-or-better matches first seen after a buy box was last viewed. The
Screener tab shows the count; viewing the box clears it.

UI: the **Screener** page has buy-box tabs and an editor, a ranked results grid
(signal, score, price and price cuts, estimated rent with a confidence dot, cap,
cash-on-cash, IRR, DSCR, days on market, NEW), and a listing panel with score
components, reasons, a rent override, price history, and "Open in analyzer" (which
saves the listing as a watchlist deal using the buy box's assumptions).

## Roadmap

1. ✅ Foundation: monorepo, CI, Docker Compose, migrations.
2. ✅ Underwriting engine, deal analyzer, watchlist.
3. ✅ Market rent ingestion + Markets page (rent-trend charts, growth defaults).
4. ✅ Portfolio tracking (ledger, CSV import, rent roll, valuations, actual vs. projected).
5. ✅ Listings (RentCast, CSV), rent estimation, screener and recommendations, alerts.
   HUD fair market rents, Census ZIP rents and RentCast rent comps.
6. Commercial underwriting (rent roll, NNN, TI/LC), Monte Carlo, after-tax returns, auth.
