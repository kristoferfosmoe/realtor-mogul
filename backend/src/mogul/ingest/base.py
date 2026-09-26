"""Shared vocabulary for ingestion: what a source produces and how it is described."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import httpx

# Metrics a series can carry, with the unit values are stored in.
# Rates are decimals (0.065 == 6.5%), matching the underwriting engine.
METRICS: dict[str, str] = {
    "rent_index": "usd",  # typical monthly market rent (Zillow ZORI)
    "home_value": "usd",  # typical home value (Zillow ZHVI)
    "mortgage_rate_30y": "rate",
    "cpi_rent": "index",  # CPI: rent of primary residence
    "rental_vacancy": "rate",
    "fair_market_rent": "usd",  # HUD FMR, gross rent by bedroom (segment 0br..4br)
    "median_gross_rent": "usd",  # Census ACS 5-year median gross rent (B25064)
}


@dataclass(frozen=True)
class GeoRef:
    kind: str  # country | msa | zip
    name: str
    state: str | None = None
    size_rank: int | None = None
    external_ids: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedSeries:
    source_key: str
    metric: str
    frequency: str
    geography: GeoRef
    observations: Sequence[tuple[date, float]]
    segment: str = "all"

    @property
    def unit(self) -> str:
        return METRICS[self.metric]


@dataclass(frozen=True)
class RawFile:
    name: str
    content: bytes


class Source(Protocol):
    """A data source adapter: download raw files, then parse them into series.

    Fetching and parsing are separate so raw files can be archived and re-parsed.
    """

    name: str
    attribution: str

    def fetch(self, client: httpx.Client) -> list[RawFile]: ...

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]: ...


US = GeoRef(kind="country", name="United States")


_METRO_NAME = re.compile(r"^\s*([^,]+),\s*([A-Z]{2})\b")


def metro_name(full: str) -> tuple[str, str] | None:
    """Zillow-style "City, ST" from an official metro title, or None if unrecognized.

    Zillow names a metro by its first principal city and state, so HUD's
    "Memphis, TN-MS-AR HUD Metro FMR Area" and Census's "Memphis, TN-MS-AR Metro Area"
    both become "Memphis, TN" and land on the same geography as Zillow's series.
    """
    m = _METRO_NAME.match(full)
    if not m:
        return None
    city = re.split(r"-|/", m.group(1))[0].strip()
    return (f"{city}, {m.group(2)}", m.group(2)) if city else None
