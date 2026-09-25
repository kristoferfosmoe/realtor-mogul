from datetime import date
from decimal import Decimal

import pytest

from mogul.portfolio.rent_schedule import month_start, months_between, schedule


def test_month_parsing_and_ranges() -> None:
    assert month_start("2024-02") == date(2024, 2, 1)
    with pytest.raises(ValueError, match="YYYY-MM"):
        month_start("Feb 2024")
    months = months_between(date(2023, 11, 1), date(2024, 2, 1))
    assert months == [date(2023, 11, 1), date(2023, 12, 1), date(2024, 1, 1), date(2024, 2, 1)]
    assert months_between(date(2024, 3, 1), date(2024, 2, 1)) == []
    with pytest.raises(ValueError, match="at most 600"):
        months_between(date(1970, 1, 1), date(2030, 1, 1))


def test_long_range_with_annual_step_up() -> None:
    lines = schedule(
        start=date(2020, 7, 1),
        end=date(2030, 6, 1),
        monthly=Decimal("1500"),
        annual_increase=0.03,
        source_key="flat-rent",
    )
    assert len(lines) == 120
    assert lines[0].amount == Decimal("1500.00") and lines[11].amount == Decimal("1500.00")
    assert lines[12].amount == Decimal("1545.00")  # first step, 12 months in
    assert lines[-1].amount == (Decimal("1500") * Decimal(str(1.03**9))).quantize(Decimal("0.01"))
    assert all(ln.status == "new" for ln in lines)


def test_day_of_month_is_clamped() -> None:
    lines = schedule(
        start=date(2024, 1, 1), end=date(2024, 4, 1), monthly=Decimal(1000), day_of_month=31,
        source_key="x",
    )  # fmt: skip
    assert [ln.date.day for ln in lines] == [31, 29, 31, 30]


def test_skips_recorded_months_and_months_with_rent() -> None:
    first = schedule(
        start=date(2024, 1, 1), end=date(2024, 3, 1), monthly=Decimal(900), source_key="lease-1"
    )
    again = schedule(
        start=date(2024, 1, 1),
        end=date(2024, 5, 1),
        monthly=Decimal(900),
        source_key="lease-1",
        recorded_hashes={ln.import_hash for ln in first},
        months_with_rent={(2024, 4)},
    )
    assert [ln.status for ln in again] == [
        "already_recorded", "already_recorded", "already_recorded", "month_has_rent", "new",
    ]  # fmt: skip
    # A different source (another unit's lease) is a different key, so no collision.
    other = schedule(
        start=date(2024, 1, 1),
        end=date(2024, 1, 1),
        monthly=Decimal(900),
        source_key="lease-2",
        recorded_hashes={ln.import_hash for ln in first},
    )
    assert other[0].status == "new"
