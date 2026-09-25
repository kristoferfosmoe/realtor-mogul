"""Listing sources: RentCast API, CSV exports (Redfin or generic), and demo data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import httpx

from mogul.ingest.base import RawFile

from .normalize import default_units, property_type


@dataclass(frozen=True)
class ParsedListing:
    source_id: str
    address: str
    price: float
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_type: str = "single_family"
    units: int = 1
    units_inferred: bool = False
    beds: float | None = None
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    hoa_monthly: float | None = None
    status: str = "active"
    listed_date: date | None = None
    days_on_market: int | None = None
    url: str | None = None
    stated_rent: float | None = None
    history: Sequence[tuple[date, str, float | None]] = field(default_factory=tuple)


class ListingSource(Protocol):
    name: str
    # A full sweep returns every active listing in its areas, so listings it no
    # longer returns can be marked off-market. Partial sources (CSV) cannot.
    full_sweep: bool

    def fetch(self, client: httpx.Client) -> list[RawFile]: ...

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedListing]: ...


# ---------------------------------------------------------------- RentCast

RENTCAST_URL = "https://api.rentcast.io/v1/listings/sale"
_RENTCAST_STATUS = {"active": "active", "inactive": "off_market"}


class RentCastSource:
    """RentCast sale listings (https://developers.rentcast.io), swept per city."""

    name = "rentcast"
    full_sweep = True
    page_size = 500
    max_pages = 10

    def __init__(self, api_key: str, areas: Sequence[str]) -> None:
        if not api_key:
            raise ValueError("set MOGUL_RENTCAST_API_KEY to fetch RentCast listings")
        if not areas:
            raise ValueError('set MOGUL_LISTING_AREAS, e.g. ["Memphis, TN", "Indianapolis, IN"]')
        self.api_key, self.areas = api_key, list(areas)

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        files = []
        for area in self.areas:
            city, _, state = (x.strip() for x in area.rpartition(","))
            for page in range(self.max_pages):
                resp = client.get(
                    RENTCAST_URL,
                    params={
                        "city": city,
                        "state": state,
                        "status": "Active",
                        "limit": self.page_size,
                        "offset": page * self.page_size,
                    },
                    headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                )
                resp.raise_for_status()
                slug = f"{city}_{state}".replace(" ", "-").lower()
                files.append(RawFile(f"{slug}_{page}.json", resp.content))
                if len(resp.json()) < self.page_size:
                    break
        return files

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedListing]:
        for f in files:
            for item in json.loads(f.content):
                parsed = parse_rentcast(item)
                if parsed:
                    yield parsed


def parse_rentcast(item: dict[str, Any]) -> ParsedListing | None:
    price = item.get("price")
    if not item.get("id") or not price:
        return None
    raw_type = item.get("propertyType")
    kind = property_type(raw_type)
    units, inferred = default_units(kind, raw_type)
    history = []
    last_price = None
    for day, h in sorted((item.get("history") or {}).items()):
        p = h.get("price")
        event = "listed" if last_price is None else ("price_change" if p != last_price else None)
        if event:
            history.append((date.fromisoformat(day[:10]), event, p))
        last_price = p
    hoa = (item.get("hoa") or {}).get("fee")
    return ParsedListing(
        source_id=str(item["id"]),
        address=item.get("addressLine1") or item.get("formattedAddress") or str(item["id"]),
        city=item.get("city"),
        state=item.get("state"),
        zip=item.get("zipCode"),
        latitude=item.get("latitude"),
        longitude=item.get("longitude"),
        property_type=kind,
        units=units,
        units_inferred=inferred,
        beds=item.get("bedrooms"),
        baths=item.get("bathrooms"),
        sqft=item.get("squareFootage"),
        year_built=item.get("yearBuilt"),
        hoa_monthly=float(hoa) if hoa else None,
        price=float(price),
        status=_RENTCAST_STATUS.get(str(item.get("status", "")).lower(), "active"),
        listed_date=_date(item.get("listedDate")),
        days_on_market=item.get("daysOnMarket"),
        history=tuple(history),
    )


# ---------------------------------------------------------------- CSV

_CSV_ALIASES = {
    "address": {"address", "street address", "street", "property address"},
    "city": {"city"},
    "state": {"state", "state or province"},
    "zip": {"zip", "zip code", "zip or postal code", "postal code", "zipcode"},
    "price": {"price", "list price", "asking price", "listing price"},
    "beds": {"beds", "bedrooms", "bd"},
    "baths": {"baths", "bathrooms", "ba"},
    "sqft": {"square feet", "sqft", "sq ft", "living area", "building size"},
    "year_built": {"year built", "year"},
    "days_on_market": {"days on market", "dom"},
    "hoa": {"hoa/month", "hoa", "hoa fee", "hoa monthly"},
    "status": {"status"},
    "type": {"property type", "type"},
    "units": {"units", "unit count", "number of units"},
    "rent": {"rent", "monthly rent", "gross rent", "gross monthly rent", "rent/month"},
    "mls": {"mls#", "mls #", "mls number", "listing id", "id"},
    "lat": {"latitude", "lat"},
    "lon": {"longitude", "lon", "lng"},
}


def parse_listing_csv(text: str) -> tuple[str, list[ParsedListing]]:
    """Returns (source name, listings). Redfin "Download All" exports are recognized."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if not header:
        raise ValueError("the file is empty")
    norm = [h.strip().lower() for h in header]
    cols: dict[str, int] = {}
    for i, name in enumerate(norm):
        if name.startswith("url"):
            cols.setdefault("url", i)
        for key, aliases in _CSV_ALIASES.items():
            if name in aliases:
                cols.setdefault(key, i)
    if "address" not in cols or "price" not in cols:
        raise ValueError(f"need at least Address and Price columns; got {header}")
    source = "redfin" if "sale type" in norm or any("redfin" in h for h in norm) else "csv"

    out = []
    for line_no, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue

        def get(key: str, row: list[str] = row) -> str:
            i = cols.get(key)
            return row[i].strip() if i is not None and i < len(row) else ""

        price = _num(get("price"))
        if not get("address") or price is None:
            if get("address") or get("price"):
                raise ValueError(f"line {line_no}: needs an address and a numeric price")
            continue  # Redfin appends a disclaimer row
        raw_type = get("type")
        kind = property_type(raw_type)
        units_given = _num(get("units"))
        units, inferred = (
            (int(units_given), False) if units_given else default_units(kind, raw_type)
        )
        key = (
            get("mls")
            or hashlib.sha256(
                f"{get('address')}|{get('city')}|{get('state')}|{get('zip')}".lower().encode()
            ).hexdigest()[:24]
        )
        sqft = _num(get("sqft"))
        year = _num(get("year_built"))
        dom = _num(get("days_on_market"))
        out.append(
            ParsedListing(
                source_id=key,
                address=get("address"),
                city=get("city") or None,
                state=(get("state") or "")[:2].upper() or None,
                zip=get("zip")[:10] or None,
                latitude=_num(get("lat")),
                longitude=_num(get("lon")),
                property_type=kind,
                units=units,
                units_inferred=inferred,
                beds=_num(get("beds")),
                baths=_num(get("baths")),
                sqft=int(sqft) if sqft else None,
                year_built=int(year) if year else None,
                hoa_monthly=_num(get("hoa")),
                price=price,
                status=_csv_status(get("status")),
                days_on_market=int(dom) if dom is not None else None,
                url=get("url") or None,
                stated_rent=_num(get("rent")),
            )
        )
    return source, out


def _csv_status(text: str) -> str:
    t = text.lower()
    if "pending" in t or "contingent" in t or "under contract" in t:
        return "pending"
    if "sold" in t or "closed" in t:
        return "sold"
    return "active"


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _date(text: str | None) -> date | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date() if text else None
    except ValueError:
        return None


# ---------------------------------------------------------------- demo

_STREETS = ["Maple", "Oak", "Cedar", "Pine", "Elm", "Birch", "Walnut", "Chestnut", "Willow",
            "Hickory", "Magnolia", "Sycamore", "Dogwood", "Poplar", "Aspen"]  # fmt: skip
_SUFFIX = ["St", "Ave", "Dr", "Ln", "Ct", "Rd", "Pl"]


class DemoListingSource:
    """Synthetic listings for the demo metros. Labeled DEMO; replaced by real sources."""

    name = "demo"
    full_sweep = True

    def __init__(self, today: date | None = None, seed: int = 11) -> None:
        self.today = today or date.today()
        self.seed = seed

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        return []

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedListing]:
        from mogul.ingest.demo import METROS

        rng = random.Random(self.seed)
        n = 0
        for name, state, _rent0, value0, tilt in METROS:
            city = name.split(",")[0]
            typical = value0 * (1.62 + tilt * 10)  # roughly where the demo index ends up
            for _ in range(rng.randint(4, 7)):
                n += 1
                kind = rng.choices(["single_family", "multi_2_4", "condo"], weights=[6, 2, 2])[0]
                units = rng.choice([2, 2, 3, 4]) if kind == "multi_2_4" else 1
                beds = (
                    float(units * rng.choice([1, 2, 2, 3]))
                    if units > 1
                    else float(
                        rng.choice([2, 3, 3, 3, 4, 4, 5])
                        if kind != "condo"
                        else rng.choice([1, 2, 2, 3])
                    )
                )
                sqft = int((beds * 480 + rng.randint(-150, 350)) * (1 if kind != "condo" else 0.85))
                size = (sqft / 1500) ** (0.8 if units > 1 else 0.6)
                price = round(typical * rng.uniform(0.85, 1.35) * size / 1000) * 1000
                dom = rng.choice([2, 5, 9, 14, 21, 35, 48, 60, 95])
                listed = self.today - timedelta(days=dom)
                history: list[tuple[date, str, float | None]] = [
                    (listed, "listed", price * (1.05 if dom > 30 else 1.0))
                ]
                if dom > 30 and rng.random() < 0.7:
                    history.append(
                        (listed + timedelta(days=dom // 2), "price_change", float(price))
                    )
                yield ParsedListing(
                    source_id=f"demo-{n}",
                    address=f"{rng.randint(100, 9900)} {rng.choice(_STREETS)} "
                    f"{rng.choice(_SUFFIX)}",
                    city=city,
                    state=state,
                    zip=f"{rng.randint(10000, 99999)}",
                    property_type=kind,
                    units=units,
                    beds=beds,
                    baths=max(1.0, round(beds * 0.6 * 2) / 2),
                    sqft=sqft,
                    year_built=rng.randint(1925, 2021),
                    hoa_monthly=float(rng.choice([180, 250, 320, 410]))
                    if kind == "condo"
                    else None,
                    price=float(price),
                    listed_date=listed,
                    days_on_market=dom,
                    stated_rent=float(round(units * rng.uniform(900, 1500), -1))
                    if units > 1 and rng.random() < 0.6
                    else None,
                    history=tuple(history),
                )
