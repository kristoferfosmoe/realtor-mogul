"""Shared vocabulary for ingestion: what a source produces and how it is described."""

from __future__ import annotations

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
}


@dataclass(frozen=True)
class GeoRef:
    kind: str  # country | msa
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
