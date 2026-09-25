from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mogul.config import get_settings
from mogul.db.models import BuyBox, IngestionRun, Listing, SavedDeal
from mogul.db.session import get_session
from mogul.listings.buybox import Assumptions, Criteria
from mogul.listings.rent import RentEstimate
from mogul.listings.scoring import Evaluation
from mogul.listings.service import (
    Summary,
    ensure_default_box,
    evaluate_listing,
    load_context,
    market_names,
    recommend,
)
from mogul.listings.sources import parse_listing_csv
from mogul.listings.store import price_cut, store_listings

router = APIRouter(tags=["screener"])
DbSession = Annotated[Session, Depends(get_session)]


class BuyBoxIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    criteria: Criteria = Field(default_factory=Criteria)
    assumptions: Assumptions = Field(default_factory=Assumptions)


class BuyBoxOut(BuyBoxIn):
    id: int
    last_viewed_at: datetime | None


class ListingEventOut(BaseModel):
    date: date
    event: str
    price: float | None


class ListingOut(BaseModel):
    id: int
    source: str
    address: str
    city: str | None
    state: str | None
    zip: str | None
    market_id: int | None
    market_name: str | None
    property_type: str
    units: int
    units_inferred: bool
    beds: float | None
    baths: float | None
    sqft: int | None
    year_built: int | None
    hoa_monthly: float | None
    price: float
    status: str
    days_on_market: int | None
    url: str | None
    stated_rent: float | None
    rent_override: float | None
    price_change: float | None  # vs original list price
    first_seen: datetime


class RecommendationOut(BaseModel):
    listing: ListingOut
    rent: RentEstimate
    evaluation: Evaluation
    is_new: bool


class RecommendationsOut(BaseModel):
    buy_box: BuyBoxOut
    summary: Summary
    rows: list[RecommendationOut]


class ListingDetail(BaseModel):
    listing: ListingOut
    events: list[ListingEventOut]
    rent: RentEstimate | None
    evaluation: Evaluation | None
    filtered_because: list[str]


class ListingPatch(BaseModel):
    rent_override: float | None = Field(None, gt=0)
    units: int | None = Field(None, ge=1, le=1000)


class ListingImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=20_000_000)


class ListingImportOut(BaseModel):
    source: str
    new: int
    updated: int
    price_changes: int


class Alerts(BaseModel):
    total_new: int
    by_box: dict[int, int]


class SourceStatus(BaseModel):
    rentcast_configured: bool
    listing_areas: list[str]
    active_listings: int
    runs: list[dict[str, object]]


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _box_out(b: BuyBox) -> BuyBoxOut:
    return BuyBoxOut(
        id=b.id,
        name=b.name,
        criteria=Criteria.model_validate(b.criteria),
        assumptions=Assumptions.model_validate(b.assumptions),
        last_viewed_at=_utc(b.last_viewed_at) if b.last_viewed_at else None,
    )


def _listing_out(x: Listing, names: dict[int, str]) -> ListingOut:
    return ListingOut(
        id=x.id,
        source=x.source,
        address=x.address,
        city=x.city,
        state=x.state,
        zip=x.zip,
        market_id=x.market_id,
        market_name=names.get(x.market_id) if x.market_id else None,
        property_type=x.property_type,
        units=x.units,
        units_inferred=x.units_inferred,
        beds=x.beds,
        baths=x.baths,
        sqft=x.sqft,
        year_built=x.year_built,
        hoa_monthly=x.hoa_monthly,
        price=x.price,
        status=x.status,
        days_on_market=x.days_on_market,
        url=x.url,
        stated_rent=x.stated_rent,
        rent_override=x.rent_override,
        price_change=price_cut(x),
        first_seen=_utc(x.first_seen),
    )


def _box(db: Session, box_id: int) -> BuyBox:
    box = db.get(BuyBox, box_id)
    if box is None:
        raise HTTPException(404, detail="buy box not found")
    return box


def _listing(db: Session, listing_id: int) -> Listing:
    x = db.scalar(
        select(Listing).options(selectinload(Listing.events)).where(Listing.id == listing_id)
    )
    if x is None:
        raise HTTPException(404, detail="listing not found")
    return x


# ---------- buy boxes ----------


@router.get("/buy-boxes")
def list_boxes(db: DbSession) -> list[BuyBoxOut]:
    ensure_default_box(db)
    return [_box_out(b) for b in db.scalars(select(BuyBox).order_by(BuyBox.id))]


@router.post("/buy-boxes", status_code=201)
def create_box(body: BuyBoxIn, db: DbSession) -> BuyBoxOut:
    box = BuyBox(
        name=body.name,
        criteria=body.criteria.model_dump(),
        assumptions=body.assumptions.model_dump(),
        last_viewed_at=datetime.now(UTC),
    )
    db.add(box)
    db.commit()
    return _box_out(box)


@router.put("/buy-boxes/{box_id}")
def update_box(box_id: int, body: BuyBoxIn, db: DbSession) -> BuyBoxOut:
    box = _box(db, box_id)
    box.name = body.name
    box.criteria = body.criteria.model_dump()
    box.assumptions = body.assumptions.model_dump()
    db.commit()
    return _box_out(box)


@router.delete("/buy-boxes/{box_id}", status_code=204)
def delete_box(box_id: int, db: DbSession) -> None:
    db.delete(_box(db, box_id))
    db.commit()


@router.get("/buy-boxes/{box_id}/recommendations")
def recommendations(box_id: int, db: DbSession) -> RecommendationsOut:
    box = _box(db, box_id)
    summary, rows = recommend(db, box)
    names = market_names(db)
    return RecommendationsOut(
        buy_box=_box_out(box),
        summary=summary,
        rows=[
            RecommendationOut(
                listing=_listing_out(r.listing, names),
                rent=r.rent,
                evaluation=r.evaluation,
                is_new=r.is_new,
            )
            for r in rows
        ],
    )


@router.post("/buy-boxes/{box_id}/seen", status_code=204)
def mark_seen(box_id: int, db: DbSession) -> None:
    _box(db, box_id).last_viewed_at = datetime.now(UTC)
    db.commit()


@router.get("/screener/alerts")
def alerts(db: DbSession) -> Alerts:
    """New BUY-or-better matches per buy box since each was last viewed."""
    ensure_default_box(db)
    by_box = {b.id: recommend(db, b)[0].new_matches for b in db.scalars(select(BuyBox))}
    return Alerts(total_new=sum(by_box.values()), by_box=by_box)


# ---------- listings ----------


@router.get("/listings/sources")
def listing_sources(db: DbSession) -> SourceStatus:
    settings = get_settings()
    runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.source.in_(["rentcast", "demo-listings", "csv", "redfin"]))
        .order_by(IngestionRun.id.desc())
        .limit(10)
    )
    return SourceStatus(
        rentcast_configured=bool(settings.rentcast_api_key),
        listing_areas=settings.listing_areas,
        active_listings=len(db.scalars(select(Listing.id).where(Listing.status == "active")).all()),
        runs=[
            {
                "source": r.source,
                "status": r.status,
                "started_at": _utc(r.started_at),
                "listings": r.series_count,
                "price_changes": r.observation_count,
                "error": r.error,
            }
            for r in runs
        ],
    )


@router.post("/listings/import")
def import_listings(body: ListingImportIn, db: DbSession) -> ListingImportOut:
    """Import a listings CSV (e.g. a Redfin "Download All" export of your search)."""
    try:
        source, parsed = parse_listing_csv(body.csv)
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from e
    now = datetime.now(UTC)
    result = store_listings(db, source, parsed, full_sweep=False, now=now)
    db.add(
        IngestionRun(
            source=source,
            status="ok",
            started_at=now,
            finished_at=now,
            series_count=result.new + result.updated,
            observation_count=result.price_changes,
        )
    )
    db.commit()
    return ListingImportOut(
        source=source, new=result.new, updated=result.updated, price_changes=result.price_changes
    )


@router.get("/listings/{listing_id}")
def listing_detail(listing_id: int, buy_box_id: int, db: DbSession) -> ListingDetail:
    x = _listing(db, listing_id)
    box = _box(db, buy_box_id)
    rent, ev, reasons = evaluate_listing(x, box, load_context(db), date.today())
    return ListingDetail(
        listing=_listing_out(x, market_names(db)),
        events=[ListingEventOut(date=e.date, event=e.event, price=e.price) for e in x.events],
        rent=rent,
        evaluation=ev,
        filtered_because=reasons,
    )


@router.patch("/listings/{listing_id}")
def patch_listing(listing_id: int, body: ListingPatch, db: DbSession) -> ListingOut:
    """Override the rent estimate or the unit count. Send rent_override=null to clear."""
    x = _listing(db, listing_id)
    fields = body.model_fields_set
    if "rent_override" in fields:
        x.rent_override = body.rent_override
    if "units" in fields and body.units is not None:
        x.units, x.units_inferred = body.units, False
    db.commit()
    return _listing_out(x, market_names(db))


@router.post("/listings/{listing_id}/watchlist", status_code=201)
def add_to_watchlist(listing_id: int, buy_box_id: int, db: DbSession) -> dict[str, int]:
    """Save the listing, underwritten with the buy box's assumptions, as a watchlist deal."""
    x = _listing(db, listing_id)
    rent, ev, _ = evaluate_listing(x, _box(db, buy_box_id), load_context(db), date.today())
    if ev is None:
        raise HTTPException(422, detail="cannot underwrite this listing (no rent estimate)")
    deal = SavedDeal(
        name=x.address,
        address=", ".join(p for p in (x.address, x.city, x.state) if p),
        status="watching",
        inputs=ev.deal.model_dump(),
    )
    db.add(deal)
    db.commit()
    return {"deal_id": deal.id}
