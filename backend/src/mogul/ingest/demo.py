"""Synthetic market data for trying the app without network access.

Everything it writes is tagged source="demo" and labeled DEMO in the UI, and any
real ingestion run deletes it. The shapes loosely follow the 2015–2026 US cycle
(steady growth, the 2021–22 rent surge, the 2022 rate shock) but the numbers are
invented and must not be used for decisions.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from datetime import date, timedelta

import httpx

from .base import US, GeoRef, ParsedSeries, RawFile

# name, state, 2015 rent, 2015 home value, local growth tilt
METROS = [
    ("New York, NY", "NY", 2350, 390_000, -0.004),
    ("Los Angeles, CA", "CA", 2150, 520_000, 0.0),
    ("Chicago, IL", "IL", 1500, 215_000, -0.006),
    ("Dallas, TX", "TX", 1350, 190_000, 0.004),
    ("Houston, TX", "TX", 1300, 180_000, -0.002),
    ("Atlanta, GA", "GA", 1150, 175_000, 0.006),
    ("Phoenix, AZ", "AZ", 1000, 200_000, 0.008),
    ("Tampa, FL", "FL", 1150, 165_000, 0.010),
    ("Austin, TX", "TX", 1400, 260_000, 0.002),
    ("Columbus, OH", "OH", 1000, 150_000, 0.004),
    ("Indianapolis, IN", "IN", 950, 140_000, 0.005),
    ("Kansas City, MO", "MO", 950, 160_000, 0.002),
    ("Memphis, TN", "TN", 900, 120_000, 0.003),
    ("Cleveland, OH", "OH", 900, 120_000, 0.001),
]


def _rent_growth(year: int) -> float:
    return {2020: 0.02, 2021: 0.12, 2022: 0.08, 2023: 0.035, 2024: 0.03}.get(
        year, 0.035 if year < 2020 else 0.025
    )


def _value_growth(year: int) -> float:
    return {2020: 0.08, 2021: 0.17, 2022: 0.08, 2023: 0.02, 2024: 0.03}.get(
        year, 0.055 if year < 2020 else 0.02
    )


def _month_ends(start: date, end: date) -> list[date]:
    out: list[date] = []
    y, m = start.year, start.month
    while True:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        d = nxt - timedelta(days=1)
        if d > end:
            return out
        out.append(d)
        y, m = nxt.year, nxt.month


class DemoSource:
    name = "demo"
    attribution = "Synthetic demo data (not real)"

    def __init__(self, end: date | None = None, seed: int = 7) -> None:
        self.end = end or date.today()
        self.seed = seed

    def fetch(self, client: httpx.Client) -> list[RawFile]:
        return []

    def parse(self, files: Sequence[RawFile]) -> Iterable[ParsedSeries]:
        rng = random.Random(self.seed)
        months = _month_ends(date(2015, 1, 1), self.end)
        national_rent: dict[date, list[float]] = {}
        national_value: dict[date, list[float]] = {}
        for rank, (name, state, rent0, value0, tilt) in enumerate(METROS, start=1):
            geo = GeoRef("msa", name, state, size_rank=rank)
            rent, value = float(rent0), float(value0)
            rents, values = [], []
            for d in months:
                rent *= (1 + _rent_growth(d.year) + tilt + rng.gauss(0, 0.012)) ** (1 / 12)
                value *= (1 + _value_growth(d.year) + tilt + rng.gauss(0, 0.015)) ** (1 / 12)
                rents.append((d, round(rent, 2)))
                values.append((d, round(value, -2)))
                national_rent.setdefault(d, []).append(rent)
                national_value.setdefault(d, []).append(value)
            yield ParsedSeries(f"rent:{name}", "rent_index", "monthly", geo, rents)
            yield ParsedSeries(f"value:{name}", "home_value", "monthly", geo, values)

        yield ParsedSeries(
            "rent:US",
            "rent_index",
            "monthly",
            US,
            [(d, round(sum(v) / len(v), 2)) for d, v in sorted(national_rent.items())],
        )
        yield ParsedSeries(
            "value:US",
            "home_value",
            "monthly",
            US,
            [(d, round(sum(v) / len(v), -2)) for d, v in sorted(national_value.items())],
        )
        yield ParsedSeries("mortgage", "mortgage_rate_30y", "weekly", US, self._mortgage(rng))
        yield ParsedSeries(
            "cpi_rent",
            "cpi_rent",
            "monthly",
            US,
            self._compound(months, 280.0, lambda y: _rent_growth(y) * 0.8 + 0.01, rng),
        )
        yield ParsedSeries("vacancy", "rental_vacancy", "quarterly", US, self._vacancy(rng))

    def _mortgage(self, rng: random.Random) -> list[tuple[date, float]]:
        anchors = {
            2015: 0.039,
            2019: 0.042,
            2020: 0.031,
            2021: 0.029,
            2022: 0.053,
            2023: 0.068,
            2024: 0.067,
            2025: 0.065,
            2026: 0.062,
            2027: 0.061,
        }
        out, d = [], date(2015, 1, 1)
        while d <= self.end:
            lo = max(y for y in anchors if y <= d.year)
            hi = min((y for y in anchors if y > d.year), default=lo)
            frac = (d.timetuple().tm_yday / 365) if hi != lo else 0
            base = anchors[lo] + (anchors[hi] - anchors[lo]) * frac
            out.append((d, round(base + rng.gauss(0, 0.0008), 4)))
            d += timedelta(days=7)
        return out

    def _compound(
        self,
        months: Sequence[date],
        start: float,
        growth: Callable[[int], float],
        rng: random.Random,
    ) -> list[tuple[date, float]]:
        v, out = start, []
        for d in months:
            v *= (1 + growth(d.year) + rng.gauss(0, 0.004)) ** (1 / 12)
            out.append((d, round(v, 3)))
        return out

    def _vacancy(self, rng: random.Random) -> list[tuple[date, float]]:
        out = []
        for y in range(2015, self.end.year + 1):
            for q, m in enumerate((1, 4, 7, 10)):
                d = date(y, m, 1)
                if d > self.end:
                    break
                base = 0.071 - 0.004 * min(max(y - 2015, 0), 6) + 0.003 * max(y - 2022, 0)
                out.append((d, round(base + q * 0.0005 + rng.gauss(0, 0.002), 4)))
        return out
