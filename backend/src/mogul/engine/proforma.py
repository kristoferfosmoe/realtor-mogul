"""Annual pro forma: turns a Deal into a cash-flow schedule and return metrics.

Conventions:
- Year 0 is acquisition; years 1..N are operations, with the sale at the end of year N.
- Rent and other income grow at `rent_growth`; fixed expenses at `expense_growth`.
- Capex reserves are an operating expense, so NOI is after reserves.
- The loan is sized off the purchase price; rehab is funded with equity.
"""

from __future__ import annotations

from .financing import balance_after, debt_service_in_year
from .models import Analysis, Deal, Exit, Metrics, YearRow
from .returns import irr


def _income_and_expenses(deal: Deal, year: int) -> tuple[float, float, float, float, float]:
    """(gross potential rent, vacancy loss, other income, fixed opex, variable opex)."""
    rent_factor = (1 + deal.rent_growth) ** (year - 1)
    expense_factor = (1 + deal.expense_growth) ** (year - 1)

    gpr = deal.monthly_rent * 12 * rent_factor
    vacancy = gpr * deal.vacancy_rate
    other = deal.other_income_monthly * 12 * rent_factor
    egi = gpr - vacancy + other

    fixed = (
        deal.property_tax_annual
        + deal.insurance_annual
        + (deal.hoa_monthly + deal.utilities_monthly) * 12
        + deal.other_expenses_annual
    ) * expense_factor
    variable = egi * (deal.management_pct + deal.maintenance_pct + deal.capex_reserve_pct)
    return gpr, vacancy, other, fixed, variable


def _noi(deal: Deal, year: int) -> float:
    gpr, vacancy, other, fixed, variable = _income_and_expenses(deal, year)
    return gpr - vacancy + other - fixed - variable


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def analyze(deal: Deal) -> Analysis:
    closing_costs = deal.purchase_price * deal.closing_costs_pct
    total_capital = deal.purchase_price + closing_costs + deal.rehab_cost

    fin = deal.financing
    loan = deal.purchase_price * (1 - fin.down_payment_pct) if fin else 0.0
    points = loan * fin.points_pct if fin else 0.0
    equity_invested = total_capital - loan + points

    base_value = deal.after_repair_value or deal.purchase_price

    years: list[YearRow] = []
    for y in range(1, deal.hold_years + 1):
        gpr, vacancy, other, fixed, variable = _income_and_expenses(deal, y)
        egi = gpr - vacancy + other
        opex = fixed + variable
        noi = egi - opex
        if fin:
            ds = debt_service_in_year(loan, fin.interest_rate, fin.amortization_years, y)
            balance = balance_after(loan, fin.interest_rate, fin.amortization_years, y * 12)
        else:
            ds = balance = 0.0
        value = base_value * (1 + deal.appreciation) ** y
        years.append(
            YearRow(
                year=y,
                gross_potential_rent=gpr,
                vacancy_loss=vacancy,
                other_income=other,
                effective_gross_income=egi,
                fixed_expenses=fixed,
                variable_expenses=variable,
                operating_expenses=opex,
                noi=noi,
                debt_service=ds,
                cash_flow=noi - ds,
                loan_balance=balance,
                property_value=value,
                equity=value - balance,
            )
        )

    last = years[-1]
    if deal.exit_cap_rate:
        sale_price = max(0.0, _noi(deal, deal.hold_years + 1) / deal.exit_cap_rate)
    else:
        sale_price = last.property_value
    selling_costs = sale_price * deal.selling_costs_pct
    exit_ = Exit(
        year=deal.hold_years,
        sale_price=sale_price,
        selling_costs=selling_costs,
        loan_payoff=last.loan_balance,
        net_proceeds=sale_price - selling_costs - last.loan_balance,
    )

    levered = [-equity_invested] + [r.cash_flow for r in years]
    levered[-1] += exit_.net_proceeds
    unlevered = [-total_capital] + [r.noi for r in years]
    unlevered[-1] += sale_price - selling_costs

    first = years[0]
    gross_income = first.gross_potential_rent + first.other_income
    returned = sum(levered[1:])
    metrics = Metrics(
        total_capital=total_capital,
        loan_amount=loan,
        equity_invested=equity_invested,
        noi_year1=first.noi,
        cash_flow_year1=first.cash_flow,
        cap_rate=_ratio(first.noi, deal.purchase_price),
        roic=_ratio(first.noi, total_capital),
        cash_on_cash=_ratio(first.cash_flow, equity_invested),
        dscr=_ratio(first.noi, first.debt_service),
        levered_irr=irr(levered),
        unlevered_irr=irr(unlevered),
        equity_multiple=_ratio(returned, equity_invested),
        total_profit=returned - equity_invested,
        gross_rent_multiplier=_ratio(deal.purchase_price, first.gross_potential_rent),
        rent_to_price=deal.monthly_rent / deal.purchase_price,
        break_even_occupancy=_break_even_occupancy(deal, first, gross_income),
    )
    return Analysis(
        metrics=metrics,
        years=years,
        exit=exit_,
        levered_cash_flows=levered,
        unlevered_cash_flows=unlevered,
    )


def _break_even_occupancy(deal: Deal, first: YearRow, gross_income: float) -> float | None:
    """Occupancy o where o*G*(1 - v%) = fixed + debt service, v% being variable opex rates.

    Variable expenses scale with collected income, so they come off the top.
    """
    variable_share = deal.management_pct + deal.maintenance_pct + deal.capex_reserve_pct
    return _ratio(first.fixed_expenses + first.debt_service, gross_income * (1 - variable_share))
