import pytest
from pydantic import ValidationError

from mogul.engine import Deal, Financing, analyze

# All-cash, frictionless property: easy to verify by hand.
BARE = dict(
    purchase_price=100_000,
    monthly_rent=1_000,
    closing_costs_pct=0,
    vacancy_rate=0,
    management_pct=0,
    maintenance_pct=0,
    capex_reserve_pct=0,
    rent_growth=0,
    expense_growth=0,
    appreciation=0,
    selling_costs_pct=0,
    hold_years=1,
    financing=None,
)


def test_all_cash_one_year_hold() -> None:
    a = analyze(Deal(**BARE))
    m = a.metrics
    assert m.noi_year1 == pytest.approx(12_000)
    assert m.cap_rate == pytest.approx(0.12)
    assert m.roic == pytest.approx(0.12)
    assert m.cash_on_cash == pytest.approx(0.12)
    assert m.unlevered_irr == pytest.approx(0.12)
    assert m.levered_irr == pytest.approx(0.12)
    assert m.equity_multiple == pytest.approx(1.12)
    assert m.total_profit == pytest.approx(12_000)
    assert m.dscr is None
    assert m.loan_amount == 0
    assert a.levered_cash_flows == pytest.approx([-100_000, 112_000])


def test_income_and_expense_waterfall() -> None:
    deal = Deal(
        **{
            **BARE,
            "vacancy_rate": 0.05,
            "other_income_monthly": 100,
            "property_tax_annual": 1_200,
            "insurance_annual": 600,
            "hoa_monthly": 50,
            "management_pct": 0.10,
        }
    )
    y1 = analyze(deal).years[0]
    assert y1.gross_potential_rent == pytest.approx(12_000)
    assert y1.vacancy_loss == pytest.approx(600)
    assert y1.effective_gross_income == pytest.approx(12_600)
    assert y1.fixed_expenses == pytest.approx(2_400)
    assert y1.variable_expenses == pytest.approx(1_260)
    assert y1.noi == pytest.approx(8_940)


def test_growth_compounds_from_year_two() -> None:
    deal = Deal(
        **{
            **BARE,
            "hold_years": 3,
            "rent_growth": 0.10,
            "expense_growth": 0.05,
            "property_tax_annual": 1_000,
            "appreciation": 0.02,
        }
    )
    years = analyze(deal).years
    assert [y.gross_potential_rent for y in years] == pytest.approx([12_000, 13_200, 14_520])
    assert [y.fixed_expenses for y in years] == pytest.approx([1_000, 1_050, 1_102.5])
    assert years[-1].property_value == pytest.approx(100_000 * 1.02**3)


def test_levered_deal_uses_equity_and_debt_service() -> None:
    deal = Deal(
        **{
            **BARE,
            "closing_costs_pct": 0.02,
            "rehab_cost": 5_000,
            "financing": Financing(
                down_payment_pct=0.2, interest_rate=0.0, amortization_years=10, points_pct=0.01
            ),
        }
    )
    a = analyze(deal)
    m = a.metrics
    assert m.total_capital == pytest.approx(107_000)
    assert m.loan_amount == pytest.approx(80_000)
    assert m.equity_invested == pytest.approx(27_800)  # 20k down + 2k closing + 5k rehab + 800
    assert a.years[0].debt_service == pytest.approx(8_000)
    assert m.dscr == pytest.approx(1.5)
    assert m.cash_flow_year1 == pytest.approx(4_000)
    # Sale at purchase price with 72k left on the loan.
    assert a.exit.net_proceeds == pytest.approx(28_000)
    assert a.levered_cash_flows == pytest.approx([-27_800, 32_000])
    assert m.levered_irr == pytest.approx(32_000 / 27_800 - 1)
    assert m.unlevered_irr == pytest.approx(112_000 / 107_000 - 1)


def test_exit_cap_rate_values_forward_noi() -> None:
    deal = Deal(**{**BARE, "hold_years": 2, "rent_growth": 0.05, "exit_cap_rate": 0.08})
    a = analyze(deal)
    forward_noi = 12_000 * 1.05**2
    assert a.exit.sale_price == pytest.approx(forward_noi / 0.08)


def test_after_repair_value_drives_appreciation_base() -> None:
    deal = Deal(**{**BARE, "rehab_cost": 20_000, "after_repair_value": 150_000})
    assert analyze(deal).exit.sale_price == pytest.approx(150_000)


def test_break_even_occupancy_zeroes_cash_flow() -> None:
    deal = Deal(
        purchase_price=300_000,
        monthly_rent=2_400,
        property_tax_annual=3_600,
        insurance_annual=1_500,
        hoa_monthly=40,
    )
    be = analyze(deal).metrics.break_even_occupancy
    assert be is not None
    at_break_even = deal.model_copy(update={"vacancy_rate": 1 - be})
    assert analyze(at_break_even).metrics.cash_flow_year1 == pytest.approx(0, abs=1e-6)


def test_loan_paid_off_before_exit() -> None:
    deal = Deal(
        **{
            **BARE,
            "hold_years": 5,
            "financing": Financing(interest_rate=0.06, amortization_years=3),
        }
    )
    a = analyze(deal)
    assert a.years[3].debt_service == 0
    assert a.exit.loan_payoff == 0


def test_rejects_variable_expenses_consuming_all_income() -> None:
    with pytest.raises(ValidationError):
        Deal(**{**BARE, "management_pct": 0.5, "maintenance_pct": 0.3, "capex_reserve_pct": 0.2})


def test_rejects_non_positive_price() -> None:
    with pytest.raises(ValidationError):
        Deal(**{**BARE, "purchase_price": 0})
