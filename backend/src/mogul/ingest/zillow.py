"""Zillow Research public CSVs: ZORI (observed rents) and ZHVI (home values), by metro.

Files are wide: one row per region, one column per month-end date. Data is free
to use with attribution to Zillow.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date

import httpx

from .base import US, GeoRef, ParsedSeries, RawFile

BASE_URL = "https://files.zillowstatic.com/research/public_csvs"

# (file name, metric, URL path) — smoothed, all homes, metro level.
FILES = [
    ("metro_zori.csv", "rent_index", "zori/Metro_zori_uc_sfrcondomfr_sm_month.csv"),
    ("metro_zhvi.csv", "home_value", "zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"),
]
_KEY_PREFIX = {"rent_index": "zori", "home_value": "zhvi"}


class ZillowSource:
    name = "zillow"
    attribution = "Zillow Observed Rent Index (ZORI) and Home Value Index (ZHVI), Zillow Research"

    def __init__(self, max_metros: int = 150) -> None:
        self.max_metros = max_metros

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        files = []
        for name, _, path in FILES:
            resp = client.get(f"{BASE_URL}/{path}")
            resp.raise_for_status()
            files.append(RawFile(name, resp.content))
        return files

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        metric_by_file = {name: metric for name, metric, _ in FILES}
        for f in files:
            metric = metric_by_file.get(f.name)
            if metric:
                yield from parse_wide_csv(f.content, metric, self.max_metros)


def parse_wide_csv(content: bytes, metric: str, max_metros: int) -> Iterable[ParsedSeries]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    date_cols = [c for c in reader.fieldnames or [] if _is_date(c)]
    for row in reader:
        region_type = row.get("RegionType", "").lower()
        rank = _int(row.get("SizeRank"))
        if region_type == "country":
            geo = US
        elif region_type == "msa" and rank is not None and rank <= max_metros:
            geo = GeoRef(
                kind="msa",
                name=row["RegionName"],
                state=row.get("StateName") or None,
                size_rank=rank,
                external_ids={"zillow": int(row["RegionID"])},
            )
        else:
            continue
        observations = [
            (date.fromisoformat(c), float(row[c])) for c in date_cols if row.get(c, "").strip()
        ]
        if observations:
            yield ParsedSeries(
                source_key=f"{_KEY_PREFIX[metric]}:{row['RegionID']}",
                metric=metric,
                frequency="monthly",
                geography=geo,
                observations=observations,
            )


def _is_date(col: str) -> bool:
    try:
        date.fromisoformat(col)
    except ValueError:
        return False
    return True


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None
