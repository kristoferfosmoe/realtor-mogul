"""FRED (Federal Reserve Bank of St. Louis) national indicators, via keyless CSV export."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

import httpx

from .base import US, ParsedSeries, RawFile

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    metric: str
    frequency: str
    percent: bool  # FRED publishes rates in percent; we store decimals


SERIES = [
    FredSeries("MORTGAGE30US", "mortgage_rate_30y", "weekly", percent=True),
    FredSeries("CUSR0000SEHA", "cpi_rent", "monthly", percent=False),
    FredSeries("RRVRUSQ156N", "rental_vacancy", "quarterly", percent=True),
]


class FredSource:
    name = "fred"
    attribution = "FRED, Federal Reserve Bank of St. Louis (Freddie Mac PMMS, BLS CPI, Census HVS)"

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        files = []
        for s in SERIES:
            resp = client.get(CSV_URL, params={"id": s.series_id})
            resp.raise_for_status()
            files.append(RawFile(f"{s.series_id}.csv", resp.content))
        return files

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        by_name = {f"{s.series_id}.csv": s for s in SERIES}
        for f in files:
            spec = by_name.get(f.name)
            if spec is None:
                continue
            observations = parse_csv(f.content, spec.series_id)
            if spec.percent:
                observations = [(d, v / 100) for d, v in observations]
            yield ParsedSeries(
                source_key=spec.series_id,
                metric=spec.metric,
                frequency=spec.frequency,
                geography=US,
                observations=observations,
            )


def parse_csv(content: bytes, series_id: str) -> list[tuple[date, float]]:
    """Two columns: a date ("observation_date", formerly "DATE") and the series id.

    Missing values are published as ".".
    """
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
    header = next(reader, None)
    if not header or len(header) < 2 or header[1] != series_id:
        raise ValueError(f"unexpected FRED header for {series_id}: {header}")
    out = []
    for row in reader:
        if len(row) >= 2 and row[1].strip() not in ("", "."):
            out.append((date.fromisoformat(row[0]), float(row[1])))
    return out
