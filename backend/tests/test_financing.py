import pytest

from mogul.engine import balance_after, monthly_payment
from mogul.engine.financing import debt_service_in_year


def test_monthly_payment_standard_mortgage() -> None:
    assert monthly_payment(200_000, 0.06, 30) == pytest.approx(1_199.10, abs=0.01)


def test_zero_rate_loan_is_straight_line() -> None:
    assert monthly_payment(120_000, 0.0, 10) == pytest.approx(1_000)
    assert balance_after(120_000, 0.0, 10, 60) == pytest.approx(60_000)


def test_balance_amortizes_to_zero() -> None:
    assert balance_after(200_000, 0.06, 30, 0) == pytest.approx(200_000)
    assert balance_after(200_000, 0.06, 30, 360) == 0
    assert balance_after(200_000, 0.06, 30, 359) == pytest.approx(1_193.13, abs=0.01)


def test_balance_after_first_payment() -> None:
    interest = 200_000 * 0.06 / 12
    principal = monthly_payment(200_000, 0.06, 30) - interest
    assert balance_after(200_000, 0.06, 30, 1) == pytest.approx(200_000 - principal)


def test_debt_service_stops_after_payoff() -> None:
    pmt = monthly_payment(100_000, 0.05, 15)
    assert debt_service_in_year(100_000, 0.05, 15, 1) == pytest.approx(pmt * 12)
    assert debt_service_in_year(100_000, 0.05, 15, 15) == pytest.approx(pmt * 12)
    assert debt_service_in_year(100_000, 0.05, 15, 16) == 0
