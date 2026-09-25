"""Upsert parsed listings, recording price and status changes as events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from mogul.db.models import Geography, IngestionRun, Listing, ListingEvent
from mogul.ingest.pipeline import archive

from .normalize import address_key, match_market
from .sources import ListingSource, ParsedListing


@dataclass
class StoreResult:
    new: int = 0
    updated: int = 0
    price_changes: int = 0
    delisted: int = 0


def store_listings(
    session: Session,
    source: str,
    parsed: Iterable[ParsedListing],
    full_sweep: bool = False,
    now: datetime | None = None,
) -> StoreResult:
    now = now or datetime.now(UTC)
    today = now.date()
    metros = [
        (g.id, g.name) for g in session.scalars(select(Geography).where(Geography.kind == "msa"))
    ]
    existing = {
        row.source_id: row
        for row in session.scalars(select(Listing).where(Listing.source == source))
    }
    result = StoreResult()
    seen: set[str] = set()
    for p in parsed:
        seen.add(p.source_id)
        row = existing.get(p.source_id)
        if row is None:
            row = Listing(source=source, source_id=p.source_id, first_seen=now)
            session.add(row)
            existing[p.source_id] = row
            history = list(p.history) or [(p.listed_date or today, "listed", p.price)]
            row.events = [ListingEvent(date=d, event=e, price=pr) for d, e, pr in history]
            result.new += 1
        else:
            if row.price != p.price:
                row.events.append(ListingEvent(date=today, event="price_change", price=p.price))
                result.price_changes += 1
            if row.status != p.status:
                row.events.append(ListingEvent(date=today, event=p.status, price=p.price))
            result.updated += 1
        row.address = p.address
        row.city, row.state, row.zip = p.city, p.state, p.zip
        row.address_key = address_key(p.address, p.city, p.state, p.zip)
        row.latitude, row.longitude = p.latitude, p.longitude
        row.market_id = match_market(p.city, p.state, metros)
        row.property_type = p.property_type
        row.units, row.units_inferred = p.units, p.units_inferred
        row.beds, row.baths, row.sqft = p.beds, p.baths, p.sqft
        row.year_built, row.hoa_monthly = p.year_built, p.hoa_monthly
        row.price, row.status = p.price, p.status
        row.listed_date, row.days_on_market = p.listed_date, p.days_on_market
        row.url, row.stated_rent = p.url, p.stated_rent
        row.last_seen = now

    if full_sweep:
        for source_id, row in existing.items():
            if source_id not in seen and row.status == "active":
                row.status = "off_market"
                row.events.append(ListingEvent(date=today, event="delisted", price=row.price))
                result.delisted += 1
    return result


def run_listing_source(
    session: Session, source: ListingSource, client: httpx.Client, raw_dir: Path
) -> IngestionRun:
    """Like the market pipeline: archive raw files, store, log. For listing runs the
    run's series_count is listings seen and observation_count is price changes."""
    run = IngestionRun(source=source.name, status="running", started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    run_id = run.id
    try:
        files = source.fetch(client)
        if files:
            run.raw_path = str(archive(raw_dir, source.name, run.started_at, files))
        result = store_listings(session, source.name, source.parse(files), source.full_sweep)
        run.series_count = result.new + result.updated
        run.observation_count = result.price_changes
        run.status = "ok"
        run.finished_at = datetime.now(UTC)
        session.commit()
    except Exception as e:  # noqa: BLE001 - reported on the run
        session.rollback()
        run = session.get_one(IngestionRun, run_id)
        run.status = "error"
        run.error = f"{type(e).__name__}: {e}"[:2000]
        run.finished_at = datetime.now(UTC)
        session.commit()
    return run


def price_cut(listing: Listing) -> float | None:
    """Change from the original list price (negative = cut), if any."""
    first = next((e.price for e in listing.events if e.price), None)
    return listing.price / first - 1 if first and first != listing.price else None


def days_listed(listing: Listing, today: date) -> int | None:
    if listing.listed_date:
        return (today - listing.listed_date).days
    return listing.days_on_market
