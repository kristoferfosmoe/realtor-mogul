"""Assemble recommendations: listings + market context + portfolio + buy box."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mogul.db.models import BuyBox, Geography, Listing
from mogul.markets.analytics import SeriesStats, stats
from mogul.markets.queries import best_series, latest_values, observations
from mogul.portfolio.service import evaluate as evaluate_portfolio
from mogul.portfolio.service import load_properties

from .buybox import Assumptions, Criteria
from .rent import CompsEstimate, RentEstimate, ZipFactor, estimate_rent
from .scoring import Evaluation, ListingFacts, evaluate, filter_reasons
from .store import days_listed

FALLBACK_RATE = 0.07


@dataclass(frozen=True)
class MarketContext:
    label: str
    rent: SeriesStats | None
    value: SeriesStats | None


@dataclass
class Context:
    markets: dict[int | None, MarketContext]  # None = national
    mortgage_rate: float | None
    shares: dict[int | None, float]  # share of held portfolio value by market
    # HUD fair market rents: metro id -> {"0br".."4br": rent}, with the metro's label.
    fmr: dict[int, tuple[str, dict[str, float]]] = field(default_factory=dict)
    # Census ACS median gross rent: by metro id (None = US), and by ZIP.
    acs: dict[int | None, float] = field(default_factory=dict)
    zip_rents: dict[str, float] = field(default_factory=dict)


def _label(geo: Geography) -> str:
    return "US" if geo.kind == "country" else geo.name.split(",")[0].split("-")[0]


def load_context(session: Session, zips: Iterable[str] = ()) -> Context:
    """Market data for screening. `zips` limits the ZIP-level data loaded."""
    chosen = best_series(session, ["rent_index", "home_value", "mortgage_rate_30y"])
    obs = observations(session, [s.id for s in chosen.values()])
    geos = {s.geography_id: s.geography for s in chosen.values()}
    markets: dict[int | None, MarketContext] = {}
    rate = None
    for gid, geo in geos.items():
        rent = chosen.get((gid, "rent_index"))
        value = chosen.get((gid, "home_value"))
        ctx = MarketContext(
            label=_label(geo),
            rent=stats(obs.get(rent.id, [])) if rent else None,
            value=stats(obs.get(value.id, [])) if value else None,
        )
        markets[None if geo.kind == "country" else gid] = ctx
        mort = chosen.get((gid, "mortgage_rate_30y"))
        if mort and obs.get(mort.id):
            rate = obs[mort.id][-1][1]

    shares: dict[int | None, float] = {}
    held = [
        (p.market_id, perf.value)
        for p, _, perf in evaluate_portfolio(session, load_properties(session), date.today())
        if not perf.sold
    ]
    total = sum(v for _, v in held)
    for mid, v in held:
        shares[mid] = shares.get(mid, 0.0) + v / total

    fmr: dict[int, tuple[str, dict[str, float]]] = {}
    for x in latest_values(session, "fair_market_rent", kind="msa"):
        fmr.setdefault(x.geography.id, (_label(x.geography), {}))[1][x.segment] = x.value
    acs: dict[int | None, float] = {}
    for x in latest_values(session, "median_gross_rent", kind="msa"):
        acs.setdefault(x.geography.id, x.value)
    for x in latest_values(session, "median_gross_rent", kind="country"):
        acs.setdefault(None, x.value)
    wanted = {z[:5] for z in zips if z}
    zip_rents = (
        {
            x.geography.name: x.value
            for x in latest_values(session, "median_gross_rent", kind="zip", names=wanted)
        }
        if wanted
        else {}
    )
    return Context(
        markets=markets, mortgage_rate=rate, shares=shares, fmr=fmr, acs=acs, zip_rents=zip_rents
    )


def interest_rate(a: Assumptions, ctx: Context) -> float:
    if a.interest_rate is not None:
        return a.interest_rate
    return (ctx.mortgage_rate + a.rate_spread) if ctx.mortgage_rate else FALLBACK_RATE


def active_listings(session: Session) -> list[Listing]:
    """Active listings, one per property: the most recently seen source wins."""
    rows = session.scalars(
        select(Listing).options(selectinload(Listing.events)).where(Listing.status == "active")
    )
    best: dict[str, Listing] = {}
    for row in rows:
        cur = best.get(row.address_key)
        if cur is None or _utc(row.last_seen) > _utc(cur.last_seen):
            best[row.address_key] = row
    return list(best.values())


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def facts(listing: Listing, ctx: Context, today: date) -> ListingFacts:
    market = ctx.markets.get(listing.market_id) if listing.market_id else None
    return ListingFacts(
        price=listing.price,
        property_type=listing.property_type,
        status=listing.status,
        market_id=listing.market_id,
        market_label=market.label if market else (listing.city or "US"),
        beds=listing.beds,
        days_on_market=days_listed(listing, today),
        year_built=listing.year_built,
        hoa_monthly=listing.hoa_monthly,
    )


def rent_for(listing: Listing, ctx: Context) -> RentEstimate | None:
    """See mogul.listings.rent for the order sources are tried in."""
    mid = listing.market_id
    market = ctx.markets.get(mid) if mid else None
    national = ctx.markets.get(None)
    typical: float | None = None
    fmr: dict[str, float] | None = None
    label, reference = "US", ctx.acs.get(None)
    if market and market.rent:
        typical, label, reference = market.rent.latest, market.label, ctx.acs.get(mid)
    elif mid and mid in ctx.fmr:
        (label, fmr), reference = ctx.fmr[mid], ctx.acs.get(mid)
    elif national and national.rent:
        typical, label = national.rent.latest, national.label
    zip5 = (listing.zip or "")[:5]
    zip_rent = ctx.zip_rents.get(zip5)
    return estimate_rent(
        override=listing.rent_override,
        stated=listing.stated_rent,
        comps=CompsEstimate.model_validate(listing.rent_comps) if listing.rent_comps else None,
        typical_rent=typical,
        fmr=fmr,
        zip_factor=ZipFactor(zip5, zip_rent / reference) if zip_rent and reference else None,
        market_label=label,
        units=listing.units,
        beds=listing.beds,
        sqft=listing.sqft,
    )


def evaluate_listing(
    listing: Listing, box: BuyBox, ctx: Context, today: date
) -> tuple[RentEstimate | None, Evaluation | None, list[str]]:
    criteria = Criteria.model_validate(box.criteria)
    assumptions = Assumptions.model_validate(box.assumptions)
    f = facts(listing, ctx, today)
    rent = rent_for(listing, ctx)
    if rent is None:
        return None, None, [*filter_reasons(f, criteria), "no rent estimate (load market data)"]
    market = ctx.markets.get(listing.market_id) or ctx.markets.get(None)
    ev = evaluate(
        f,
        rent,
        criteria,
        assumptions,
        interest_rate=interest_rate(assumptions, ctx),
        rent_stats=market.rent if market else None,
        value_stats=market.value if market else None,
        market_share=ctx.shares.get(listing.market_id, 0.0) if listing.market_id else 0.0,
    )
    return rent, ev, filter_reasons(f, criteria)


class Summary(BaseModel):
    scanned: int
    filtered_out: int
    evaluated: int
    strong_buy: int
    buy: int
    watch: int
    new_matches: int
    interest_rate: float


@dataclass
class Row:
    listing: Listing
    rent: RentEstimate
    evaluation: Evaluation
    is_new: bool


def recommend(
    session: Session, box: BuyBox, today: date | None = None
) -> tuple[Summary, list[Row]]:
    today = today or date.today()
    listings = active_listings(session)
    ctx = load_context(session, zips=[x.zip for x in listings if x.zip])
    criteria = Criteria.model_validate(box.criteria)
    seen_at = _utc(box.last_viewed_at) if box.last_viewed_at else None
    rows: list[Row] = []
    filtered = 0
    for listing in listings:
        if filter_reasons(facts(listing, ctx, today), criteria):
            filtered += 1
            continue
        rent, ev, _ = evaluate_listing(listing, box, ctx, today)
        if rent is None or ev is None:
            filtered += 1
            continue
        is_new = seen_at is not None and _utc(listing.first_seen) > seen_at
        rows.append(Row(listing, rent, ev, is_new))
    rows.sort(key=lambda r: -r.evaluation.score)
    signals = [r.evaluation.signal for r in rows]
    summary = Summary(
        scanned=len(listings),
        filtered_out=filtered,
        evaluated=len(rows),
        strong_buy=signals.count("STRONG BUY"),
        buy=signals.count("BUY"),
        watch=signals.count("WATCH"),
        new_matches=sum(r.is_new and r.evaluation.signal in ("BUY", "STRONG BUY") for r in rows),
        interest_rate=interest_rate(Assumptions.model_validate(box.assumptions), ctx),
    )
    return summary, rows


def ensure_default_box(session: Session) -> None:
    if session.scalar(select(BuyBox.id).limit(1)) is None:
        session.add(
            BuyBox(
                name="Cash-flowing rentals",
                criteria=Criteria().model_dump(),
                assumptions=Assumptions().model_dump(),
                last_viewed_at=datetime.now(UTC),
            )
        )
        session.commit()


def market_names(session: Session) -> dict[int, str]:
    return {g.id: g.name for g in session.scalars(select(Geography).where(Geography.kind == "msa"))}
