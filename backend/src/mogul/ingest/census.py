"""Census Bureau American Community Survey (ACS): median gross rent, 5-year estimates.

Table B25064 is the median gross rent (contract rent plus utilities) paid by renter
households, for the US, every metro area and every ZIP Code Tabulation Area (ZCTA).
It counts every renter, including long-tenured ones, so it runs below current asking
rents. It is used for how a ZIP compares with its metro, not as a rent level.

A 5-year vintage labeled Y covers Y-4 through Y and comes out in December of Y+1.
Observations are dated December 31 of Y. ZIP-level data is national (no state
needed) from the 2020 vintage on, so older vintages are fetched without ZIPs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

import httpx

from .base import US, GeoRef, ParsedSeries, RawFile, metro_name

API_URL = "https://api.census.gov/data/{year}/acs/acs5"
VARIABLE = "B25064_001E"
FIRST_NATIONAL_ZCTA_VINTAGE = 2020
# (file tag, the API's "for" clause)
GEOGRAPHIES = [
    ("us", "us:1"),
    ("metro", "metropolitan statistical area/micropolitan statistical area:*"),
    ("zip", "zip code tabulation area:*"),
]


class AcsSource:
    name = "census"
    attribution = "U.S. Census Bureau, American Community Survey 5-year estimates (B25064)"

    def __init__(self, api_key: str = "", years: int = 3, today: date | None = None) -> None:
        self.api_key, self.years = api_key, max(1, years)
        self.today = today or date.today()

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        files: list[RawFile] = []
        found = 0
        # The newest vintage may not be out yet; try one extra year back.
        for year in range(self.today.year - 1, self.today.year - 2 - self.years, -1):
            if found == self.years:
                break
            got = []
            for tag, clause in GEOGRAPHIES:
                if tag == "zip" and year < FIRST_NATIONAL_ZCTA_VINTAGE:
                    continue
                body = self._get(client, year, clause)
                if body is None:
                    break
                got.append(RawFile(f"{year}_{tag}.json", body))
            else:
                files += got
                found += 1
        if not files:
            raise RuntimeError("the Census API returned no ACS data")
        return files

    def _get(self, client: httpx.Client, year: int, clause: str) -> bytes | None:
        params = {"get": f"NAME,{VARIABLE}", "for": clause}
        if self.api_key:
            params["key"] = self.api_key
        resp = client.get(API_URL.format(year=year), params=params)
        if resp.status_code == 404:
            return None  # vintage not published
        resp.raise_for_status()
        if not isinstance(_json(resp.content), list):
            # A bad key gets an HTML page with status 200.
            raise ValueError(f"unexpected Census response: {resp.text[:200]!r}")
        return resp.content

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        series: dict[str, tuple[GeoRef, dict[date, float]]] = {}
        metro_codes: dict[str, str] = {}  # short name -> CBSA code, first one wins
        for f in sorted(files, key=lambda f: f.name):
            year_text, _, tag = f.name.removesuffix(".json").partition("_")
            rows = _json(f.content)
            if not year_text.isdigit() or not isinstance(rows, list) or len(rows) < 2:
                continue
            day = date(int(year_text), 12, 31)
            header = rows[0]
            try:
                i_name, i_value = header.index("NAME"), header.index(VARIABLE)
            except ValueError:
                continue
            for row in rows[1:]:
                value = _rent(row[i_value])
                if value is None:
                    continue
                code = str(row[-1])
                if tag == "us":
                    key, geo = "acs:us", US
                elif tag == "metro":
                    title = str(row[i_name])
                    named = metro_name(title)
                    if not named or not title.endswith("Metro Area"):
                        continue  # micropolitan areas are too small to screen
                    if metro_codes.setdefault(named[0], code) != code:
                        continue
                    key = f"acs:cbsa:{code}"
                    geo = GeoRef("msa", named[0], named[1], external_ids={"cbsa": code})
                elif tag == "zip":
                    key, geo = f"acs:zcta:{code}", GeoRef("zip", code)
                else:
                    continue
                series.setdefault(key, (geo, {}))[1][day] = value
        for key, (geo, obs) in series.items():
            yield ParsedSeries(
                source_key=key,
                metric="median_gross_rent",
                frequency="annual",
                geography=geo,
                observations=sorted(obs.items()),
            )


def _rent(v: Any) -> float | None:
    """Census marks missing estimates with large negative sentinels (-666666666)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _json(content: bytes) -> Any:
    try:
        return json.loads(content)
    except ValueError:
        return None
