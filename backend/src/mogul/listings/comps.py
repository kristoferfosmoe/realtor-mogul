"""Rent from comparable rentals: RentCast's long-term rent AVM.

Every lookup costs one RentCast API call, so estimates are only fetched on request
(the listing panel's button, or `python -m mogul.ingest rents`) and are kept on the
listing. For 2–4 unit buildings it asks for one unit (beds, baths and size divided
by the unit count) and multiplies by the number of units.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mogul.db.models import BuyBox, IngestionRun, Listing
from mogul.ingest.base import RawFile
from mogul.ingest.pipeline import archive

from .buybox import Criteria
from .rent import Comp, CompsEstimate
from .scoring import filter_reasons
from .service import facts, load_context

AVM_URL = "https://api.rentcast.io/v1/avm/rent/long-term"
RUN_SOURCE = "rentcast-rents"
COMP_COUNT = 15
# RentCast property types; land and commercial have no rent AVM.
_TYPES = {
    "single_family": "Single Family",
    "condo": "Condo",
    "multi_2_4": "Multi-Family",
    "multifamily": "Apartment",
}


def avm_params(listing: Listing) -> dict[str, Any] | None:
    """Query for one unit of the listing, or None if RentCast cannot estimate it."""
    kind = _TYPES.get(listing.property_type)
    if kind is None:
        return None
    units = max(1, listing.units)
    tail = " ".join(p for p in (listing.state, listing.zip) if p)
    address = ", ".join(p for p in (listing.address, listing.city, tail) if p)
    params: dict[str, Any] = {"address": address, "propertyType": kind, "compCount": COMP_COUNT}
    if listing.beds is not None:
        params["bedrooms"] = round(listing.beds / units)
    if listing.baths is not None:
        params["bathrooms"] = max(1.0, round(listing.baths / units * 2) / 2)
    if listing.sqft:
        params["squareFootage"] = round(listing.sqft / units)
    return params


def parse_avm(content: bytes, units: int, fetched_at: datetime) -> CompsEstimate:
    body = json.loads(content)
    rent = body.get("rent") if isinstance(body, dict) else None
    if not rent:
        raise ValueError("RentCast returned no rent estimate for this address")
    comps = [
        Comp(
            address=c.get("formattedAddress") or c.get("addressLine1") or "unknown",
            rent=float(c["price"]),
            beds=c.get("bedrooms"),
            baths=c.get("bathrooms"),
            sqft=c.get("squareFootage"),
            distance_mi=c.get("distance"),
            days_old=c.get("daysOld"),
            correlation=c.get("correlation"),
        )
        for c in body.get("comparables") or []
        if c.get("price")
    ]
    return CompsEstimate(
        per_unit=float(rent),
        low=body.get("rentRangeLow"),
        high=body.get("rentRangeHigh"),
        units=max(1, units),
        comps=comps,
        fetched_at=fetched_at,
    )


def fetch_comps(
    session: Session, listing: Listing, client: httpx.Client, api_key: str, raw_dir: Path
) -> CompsEstimate:
    """Look up, archive and store the AVM for one listing. Raises on any failure."""
    if not api_key:
        raise ValueError("set MOGUL_RENTCAST_API_KEY to fetch rent comps")
    params = avm_params(listing)
    if params is None:
        raise ValueError(f"RentCast has no rent estimates for {listing.property_type} property")
    resp = client.get(
        AVM_URL, params=params, headers={"X-Api-Key": api_key, "Accept": "application/json"}
    )
    resp.raise_for_status()
    now = datetime.now(UTC)
    archive(raw_dir, "rentcast-avm", now, [RawFile(f"listing-{listing.id}.json", resp.content)])
    estimate = parse_avm(resp.content, listing.units, now)
    listing.rent_comps = estimate.model_dump(mode="json")
    return estimate


def candidates(session: Session, max_age_days: int, today: date) -> list[Listing]:
    """Active listings worth spending a lookup on, newest first: no rent from the user
    or the listing, no recent comps, and inside at least one buy box's hard filters."""
    ctx = load_context(session)
    boxes = [Criteria.model_validate(b.criteria) for b in session.scalars(select(BuyBox))]
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    rows = session.scalars(
        select(Listing)
        .options(selectinload(Listing.events))
        .where(Listing.status == "active")
        .order_by(Listing.first_seen.desc())
    )
    out = []
    for x in rows:
        if x.rent_override or x.stated_rent or avm_params(x) is None:
            continue
        if x.rent_comps and _fetched(x.rent_comps) > cutoff:
            continue
        f = facts(x, ctx, today)
        if boxes and all(filter_reasons(f, c) for c in boxes):
            continue
        out.append(x)
    return out


def run_comps(
    session: Session,
    client: httpx.Client,
    api_key: str,
    raw_dir: Path,
    limit: int,
    max_age_days: int = 90,
) -> IngestionRun:
    """Fetch comps for up to `limit` candidates. series_count = listings updated.

    Stops at the first failure (a bad key or an exhausted quota would fail every
    lookup) and keeps what was already fetched.
    """
    run = IngestionRun(source=RUN_SOURCE, status="running", started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    done = 0
    try:
        if not api_key:
            raise ValueError("set MOGUL_RENTCAST_API_KEY to fetch rent comps")
        for listing in candidates(session, max_age_days, date.today())[:limit]:
            fetch_comps(session, listing, client, api_key, raw_dir)
            done += 1
            session.commit()
        run.status = "ok"
    except Exception as e:  # noqa: BLE001 - reported on the run
        session.rollback()
        run.status = "error"
        run.error = f"{type(e).__name__}: {e}"[:2000]
    run.series_count = done
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run


def _fetched(doc: dict[str, Any]) -> datetime:
    at = datetime.fromisoformat(str(doc.get("fetched_at")))
    return at if at.tzinfo else at.replace(tzinfo=UTC)
