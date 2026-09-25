from datetime import date

import pytest

from mogul.markets.analytics import cagr, gross_yield, pct_change, shift_months, stats, value_at

MONTHLY = [(shift_months(date(2019, 1, 31), i), 1000 * 1.01**i) for i in range(73)]


@pytest.mark.parametrize(
    ("d", "months", "expected"),
    [
        (date(2024, 3, 31), -1, date(2024, 2, 29)),
        (date(2024, 2, 29), -12, date(2023, 2, 28)),
        (date(2023, 2, 28), 12, date(2024, 2, 29)),  # month-end stays month-end
        (date(2024, 1, 15), -1, date(2023, 12, 15)),
        (date(2024, 1, 1), -12, date(2023, 1, 1)),
    ],
)
def test_shift_months(d: date, months: int, expected: date) -> None:
    assert shift_months(d, months) == expected


def test_value_at_takes_last_on_or_before() -> None:
    weekly = [(date(2024, 1, 4), 1.0), (date(2024, 1, 11), 2.0)]
    assert value_at(weekly, date(2024, 1, 10)) == 1.0
    assert value_at(weekly, date(2024, 1, 11)) == 2.0
    assert value_at(weekly, date(2024, 1, 1)) is None


def test_growth_rates() -> None:
    assert pct_change(MONTHLY, 12) == pytest.approx(1.01**12 - 1)
    assert cagr(MONTHLY, 5) == pytest.approx(1.01**12 - 1)
    assert cagr(MONTHLY, 7) is None  # not enough history


def test_stats() -> None:
    s = stats(MONTHLY)
    assert s is not None
    assert s.latest_date == date(2025, 1, 31)
    assert s.change_pct == pytest.approx(0.01)
    assert s.yoy == pytest.approx(1.01**12 - 1)
    assert s.yoy_abs == pytest.approx(MONTHLY[-1][1] - MONTHLY[-13][1])
    assert s.cagr_3y == pytest.approx(1.01**12 - 1)
    assert stats([]) is None


def test_single_observation_stats() -> None:
    s = stats([(date(2024, 1, 31), 5.0)])
    assert s is not None and s.previous is None and s.yoy is None


def test_gross_yield_aligns_dates() -> None:
    rent = [(date(2024, 1, 31), 2000.0), (date(2024, 2, 29), 2100.0)]
    value = [(date(2024, 1, 31), 400_000.0)]  # value lags rent by a month
    assert gross_yield(rent, value) == pytest.approx(2100 * 12 / 400_000)
    assert gross_yield(rent, []) is None
