"""Expand "rent of X per month from A to B" into one ledger line per month.

Pure: callers supply the months already holding rent, and decide what to store.
"""

from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

MAX_MONTHS = 600  # 50 years
CENT = Decimal("0.01")

LineStatus = Literal["new", "already_recorded", "month_has_rent"]


@dataclass(frozen=True)
class RentLine:
    date: date
    amount: Decimal
    import_hash: str
    status: LineStatus


def month_start(text: str) -> date:
    """Parse "YYYY-MM" to the first of that month."""
    try:
        year, month = (int(x) for x in text.split("-"))
        return date(year, month, 1)
    except ValueError as e:
        raise ValueError(f"expected YYYY-MM, got {text!r}") from e


def months_between(start: date, end: date) -> list[date]:
    """First-of-month dates from start's month through end's month, inclusive."""
    first = date(start.year, start.month, 1)
    count = (end.year - first.year) * 12 + end.month - first.month + 1
    if count <= 0:
        return []
    if count > MAX_MONTHS:
        raise ValueError(f"a range can cover at most {MAX_MONTHS} months")
    return [date(first.year + (first.month - 1 + i) // 12, (first.month - 1 + i) % 12 + 1, 1)
            for i in range(count)]  # fmt: skip


def schedule(
    *,
    start: date,
    end: date,
    monthly: Decimal,
    day_of_month: int = 1,
    annual_increase: float = 0.0,
    source_key: str,
    recorded_hashes: set[str] = frozenset(),  # type: ignore[assignment]
    months_with_rent: set[tuple[int, int]] = frozenset(),  # type: ignore[assignment]
) -> list[RentLine]:
    """One line per month. Rent steps up by `annual_increase` every 12 months from `start`.

    `source_key` identifies what generated the rent (a lease, or a flat amount), so the
    same month from the same source is never recorded twice, however often it's re-run.
    """
    lines = []
    for i, first in enumerate(months_between(start, end)):
        day = min(day_of_month, calendar.monthrange(first.year, first.month)[1])
        amount = (monthly * Decimal(str((1 + annual_increase) ** (i // 12)))).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        digest = hashlib.sha256(f"rent-range|{source_key}|{first:%Y-%m}".encode()).hexdigest()
        status: LineStatus = (
            "already_recorded"
            if digest in recorded_hashes
            else "month_has_rent"
            if (first.year, first.month) in months_with_rent
            else "new"
        )
        lines.append(RentLine(first.replace(day=day), amount, digest, status))
    return lines
