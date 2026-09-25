"""Pure time-series math for market data. Observations are (date, value), ascending."""

from __future__ import annotations

import calendar
from bisect import bisect_right
from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel

Obs = Sequence[tuple[date, float]]


class SeriesStats(BaseModel):
    latest: float
    latest_date: date
    previous: float | None = None  # prior observation, whatever the frequency
    change: float | None = None  # latest - previous
    change_pct: float | None = None
    yoy: float | None = None  # % change over 12 months
    yoy_abs: float | None = None  # absolute change over 12 months (for rates)
    cagr_3y: float | None = None
    cagr_5y: float | None = None


def shift_months(d: date, months: int) -> date:
    """Move by whole months; month-end dates stay month-end (Mar 31 - 1 → Feb 28)."""
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    last = calendar.monthrange(y, m + 1)[1]
    is_month_end = d.day == calendar.monthrange(d.year, d.month)[1]
    return date(y, m + 1, last if is_month_end else min(d.day, last))


def value_at(obs: Obs, when: date) -> float | None:
    """Latest value observed on or before `when`."""
    i = bisect_right([d for d, _ in obs], when)
    return obs[i - 1][1] if i else None


def pct_change(obs: Obs, months: int) -> float | None:
    if not obs:
        return None
    then = value_at(obs, shift_months(obs[-1][0], -months))
    return obs[-1][1] / then - 1 if then else None


def cagr(obs: Obs, years: int) -> float | None:
    change = pct_change(obs, years * 12)
    return None if change is None or change <= -1 else (1 + change) ** (1 / years) - 1


def stats(obs: Obs) -> SeriesStats | None:
    if not obs:
        return None
    latest_date, latest = obs[-1]
    previous = obs[-2][1] if len(obs) > 1 else None
    year_ago = value_at(obs, shift_months(latest_date, -12))
    return SeriesStats(
        latest=latest,
        latest_date=latest_date,
        previous=previous,
        change=None if previous is None else latest - previous,
        change_pct=latest / previous - 1 if previous else None,
        yoy=pct_change(obs, 12),
        yoy_abs=None if year_ago is None else latest - year_ago,
        cagr_3y=cagr(obs, 3),
        cagr_5y=cagr(obs, 5),
    )


def gross_yield(rent: Obs, home_value: Obs) -> float | None:
    """Annual rent / home value, both taken at the rent series' latest date."""
    if not rent or not home_value:
        return None
    when, monthly_rent = rent[-1]
    value = value_at(home_value, when)
    return monthly_rent * 12 / value if value else None
