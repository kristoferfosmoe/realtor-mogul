from datetime import date

import pytest

from mogul.engine import monthly_payment, xirr
from mogul.portfolio.performance import (
    Holding,
    LeaseFacts,
    LoanFacts,
    cash_flows,
    mark,
    monthly,
    performance,
)

START = date(2023, 1, 1)


def rent_ledger(months: int, amount: float = 1000.0) -> list[tuple[date, str, float]]:
    return [(date(2023 + (m // 12), m % 12 + 1, 5), "rent", amount) for m in range(months)]


def test_loan_payment_count() -> None:
    loan = LoanFacts(100_000, 0.06, 30, date(2024, 1, 15))
    assert loan.payments_made(date(2024, 1, 31)) == 0
    assert loan.payments_made(date(2024, 2, 14)) == 0
    assert loan.payments_made(date(2024, 2, 15)) == 1
    assert loan.payments_made(date(2025, 1, 15)) == 12
    month_end_loan = LoanFacts(100_000, 0.06, 30, date(2024, 1, 31))
    assert month_end_loan.payments_made(date(2024, 2, 29)) == 1


def test_all_cash_trailing_twelve() -> None:
    h = Holding(
        purchase_date=START,
        purchase_price=100_000,
        ledger=rent_ledger(24) + [(date(2024, 6, 1), "property_tax", -1200.0)],
    )
    p = performance(h, date(2025, 1, 1))
    assert p.t12.income == 12_000 and p.t12.operating_expenses == 1200
    assert p.t12.noi == 10_800 and p.t12.cash_flow == 10_800
    assert p.t12.months == pytest.approx(12, abs=0.05)
    assert p.cap_rate_on_cost == pytest.approx(0.108, rel=0.01)
    assert p.value == 100_000 and p.value_source == "purchase"
    assert p.equity_invested == 100_000 and p.loan_balance == 0 and p.ltv == 0
    assert not p.debt_service_imputed
    assert p.distributions == pytest.approx(24_000 - 1200)


def test_irr_matches_xirr_of_dated_flows() -> None:
    h = Holding(purchase_date=START, purchase_price=100_000, ledger=rent_ledger(24))
    as_of = date(2025, 1, 1)
    flows = cash_flows(h, as_of)
    assert flows[0] == (START, -100_000)
    assert flows[-1] == (as_of, pytest.approx(94_000))  # 6% assumed selling costs
    assert performance(h, as_of).irr == pytest.approx(xirr(flows))


def test_imputes_scheduled_debt_service_only_without_ledger_payments() -> None:
    loan = LoanFacts(75_000, 0.07, 30, START)
    imputed = performance(
        Holding(START, 100_000, loan=loan, ledger=rent_ledger(12)), date(2024, 1, 1)
    )
    assert imputed.debt_service_imputed
    assert imputed.t12.debt_service == pytest.approx(12 * monthly_payment(75_000, 0.07, 30))

    recorded = performance(
        Holding(
            START,
            100_000,
            loan=loan,
            ledger=[*rent_ledger(12), (date(2023, 2, 1), "debt_service", -500.0)],
        ),
        date(2024, 1, 1),
    )
    assert not recorded.debt_service_imputed
    assert recorded.t12.debt_service == 500


def test_transfers_ignored_and_uncategorized_below_noi() -> None:
    h = Holding(
        START,
        100_000,
        ledger=[
            (date(2023, 3, 1), "rent", 1000.0),
            (date(2023, 3, 2), "transfer", 50_000.0),
            (date(2023, 3, 3), "uncategorized", -40.0),
        ],
    )
    p = performance(h, date(2023, 12, 31))
    assert p.t12.noi == 1000
    assert p.t12.cash_flow == 960
    assert p.uncategorized_count == 1


def test_value_is_indexed_from_latest_valuation() -> None:
    index = [(date(2023, 1, 31), 100.0), (date(2024, 1, 31), 110.0), (date(2024, 12, 31), 121.0)]
    h = Holding(START, 200_000, index=index)
    assert mark(h, date(2024, 2, 15)) == (pytest.approx(220_000), "indexed")
    appraised = Holding(START, 200_000, index=index, valuations=[(date(2024, 1, 31), 250_000.0)])
    assert mark(appraised, date(2024, 1, 31)) == (250_000, "valuation")
    assert mark(appraised, date(2025, 1, 15))[0] == pytest.approx(250_000 * 1.1)


def test_sold_property_uses_actual_sale() -> None:
    loan = LoanFacts(80_000, 0.0, 10, START)
    h = Holding(
        START,
        100_000,
        loan=loan,
        sale_date=date(2025, 1, 1),
        sale_price=130_000,
        selling_costs=7_800,
        ledger=[(date(2023, 6, 1), "debt_service", -1.0)],
    )
    p = performance(h, date(2025, 6, 1))
    assert p.sold and p.value_source == "sale"
    assert p.gain == pytest.approx(130_000 - 7_800 - 100_000)
    assert p.equity == 0 and p.occupancy is None
    terminal = cash_flows(h, date(2025, 6, 1))[-1]
    assert terminal == (
        date(2025, 1, 1),
        pytest.approx(130_000 - 7_800 - loan.balance(date(2025, 1, 1))),
    )
    assert monthly(h, date(2025, 6, 1))[-1].month == date(2025, 1, 1)


def test_no_irr_for_short_holds() -> None:
    assert performance(Holding(START, 100_000), date(2023, 4, 1)).irr is None


def test_occupancy_from_active_leases() -> None:
    h = Holding(
        START,
        300_000,
        units=3,
        leases=[
            LeaseFacts("A", date(2023, 1, 1), None, 1000),
            LeaseFacts("B", date(2023, 1, 1), date(2023, 6, 30), 900),
            LeaseFacts("C", date(2023, 7, 1), date(2024, 6, 30), 950),
        ],
    )
    p = performance(h, date(2023, 12, 1))
    assert (p.occupied_units, p.occupancy, p.scheduled_rent) == (2, pytest.approx(2 / 3), 1950)


def test_monthly_rows_span_purchase_to_as_of() -> None:
    h = Holding(date(2024, 1, 20), 100_000, ledger=[(date(2024, 1, 20), "capex", -5000.0)])
    rows = monthly(h, date(2024, 3, 10))
    assert [r.month for r in rows] == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 10)]
    assert rows[0].capex == 5000  # purchase-day spend lands in month one


def test_no_indexing_when_anchor_long_predates_the_index() -> None:
    index = [(date(2020, 1, 31), 100.0), (date(2021, 1, 31), 120.0)]
    h = Holding(date(2015, 6, 1), 150_000, index=index)
    assert mark(h, date(2021, 2, 1)) == (150_000, "purchase")
