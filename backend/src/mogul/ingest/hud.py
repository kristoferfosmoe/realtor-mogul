"""HUD Fair Market Rents (FMRs) by metro, from the HUD USER API (free token).

An FMR is HUD's estimate of the 40th-percentile gross rent (rent plus utilities)
for a standard-quality unit, by bedroom count. FMRs set Housing Choice Voucher
(Section 8) payment standards, so they are a useful benchmark, and a per-bedroom
rent for metros Zillow does not cover. HUD publishes them once per federal fiscal
year; FY N takes effect on October 1 of year N-1, and that is the observation date.

One `statedata` call per state and year returns every metro FMR area in the state.
Metros that span states appear once per state and are stored once.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Any

import httpx

from .base import GeoRef, ParsedSeries, RawFile, metro_name

API_URL = "https://www.huduser.gov/hudapi/public/fmr"
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY", "PR",
]  # fmt: skip
BEDROOMS = {
    "Efficiency": "0br",
    "One-Bedroom": "1br",
    "Two-Bedroom": "2br",
    "Three-Bedroom": "3br",
    "Four-Bedroom": "4br",
}
# "METRO32820M32820": CBSA 32820, HUD area 32820. A CBSA HUD splits into several
# FMR areas has one whose area code equals the CBSA: the principal one.
_CODE = re.compile(r"^METRO(\d{5})M(\d{5})$")
_MAX_RETRIES = 4
TOKEN_HELP = "set MOGUL_HUD_API_TOKEN (free at https://www.huduser.gov/hudapi/public/register)"


class HudFmrSource:
    name = "hud"
    attribution = "HUD Fair Market Rents, U.S. Department of Housing and Urban Development"

    def __init__(
        self,
        token: str,
        years: int = 5,
        today: date | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.token, self.years = token, max(1, years)
        self.today = today or date.today()
        self.sleep = sleep

    def fiscal_years(self) -> list[int]:
        """Newest first. The next FY is usually published in August or September."""
        current = self.today.year + (1 if self.today.month >= 10 else 0)
        return [current + 1 - i for i in range(self.years + 1)]

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        if not self.token:
            raise ValueError(TOKEN_HELP)
        files: list[RawFile] = []
        years_found = 0
        for year in self.fiscal_years():
            if years_found == self.years:
                break
            for i, state in enumerate(STATES):
                body = self._get(client, f"{API_URL}/statedata/{state}", {"year": year})
                if body is None:
                    if i == 0:
                        break  # this year is not published (yet)
                    continue
                files.append(RawFile(f"{year}_{state}.json", body))
            else:
                years_found += 1
        if not files:
            raise RuntimeError("HUD returned no Fair Market Rent data")
        return files

    def _get(self, client: httpx.Client, url: str, params: dict[str, Any]) -> bytes | None:
        """The response body, or None when HUD has no data for the request."""
        for attempt in range(_MAX_RETRIES):
            resp = client.get(url, params=params, headers={"Authorization": f"Bearer {self.token}"})
            if resp.status_code == 429 and attempt < _MAX_RETRIES - 1:
                retry_after = resp.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 15.0 * 2**attempt)
                continue
            if resp.status_code in (401, 403):
                raise PermissionError(f"HUD rejected the API token ({resp.status_code})")
            if 400 <= resp.status_code < 500:
                return None
            resp.raise_for_status()
            data = _json(resp.content)
            if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
                return None  # e.g. {"error": "..."} for a year HUD has not published
            return resp.content
        raise RuntimeError("HUD rate limit: too many retries")

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        areas: dict[str, _Area] = {}
        for f in files:
            data = _json(f.content)
            data = data.get("data") if isinstance(data, dict) else None
            if not isinstance(data, dict):
                continue
            year = _int(data.get("year")) or _int(f.name.split("_")[0])
            if year is None:
                continue
            for row in data.get("metroareas") or []:
                code = str(row.get("code") or "")
                title = row.get("metro_name") or row.get("area_name") or ""
                named = metro_name(title)
                if not code or not named:
                    continue
                area = areas.setdefault(code, _Area(code, named[0], named[1]))
                for field, segment in BEDROOMS.items():
                    value = _float(row.get(field))
                    if value:
                        area.obs.setdefault(segment, {})[date(year - 1, 10, 1)] = value

        # Several HUD areas can share a short name (a CBSA split into FMR areas).
        # Keep one per name: the principal area, else the lowest code.
        by_name: dict[str, _Area] = {}
        for area in sorted(areas.values(), key=lambda a: (not a.principal, a.code)):
            by_name.setdefault(area.name, area)

        for area in sorted(by_name.values(), key=lambda a: a.code):
            ids: dict[str, Any] = {"hud_fmr": area.code}
            if area.cbsa:
                ids["cbsa"] = area.cbsa
            geo = GeoRef(kind="msa", name=area.name, state=area.state, external_ids=ids)
            for segment, obs in sorted(area.obs.items()):
                yield ParsedSeries(
                    source_key=f"fmr:{area.code}:{segment}",
                    metric="fair_market_rent",
                    frequency="annual",
                    geography=geo,
                    observations=sorted(obs.items()),
                    segment=segment,
                )


class _Area:
    def __init__(self, code: str, name: str, state: str) -> None:
        self.code, self.name, self.state = code, name, state
        m = _CODE.match(code)
        self.cbsa = m.group(1) if m else None
        self.principal = bool(m and m.group(1) == m.group(2))
        self.obs: dict[str, dict[date, float]] = {}


def _json(content: bytes) -> Any:
    try:
        return json.loads(content)
    except ValueError:
        return None


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
