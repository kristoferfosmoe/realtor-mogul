"""Inputs and outputs of the pro forma engine.

Rates are decimals (0.07 == 7%). Money is float: projections are estimates, so
float64 precision is far finer than the assumptions behind them. Recorded
transactions (the portfolio ledger) use exact decimals instead.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

Rate = float


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Financing(_Frozen):
    """A fixed-rate, fully amortizing acquisition loan sized off the purchase price."""

    down_payment_pct: Rate = Field(0.25, ge=0, le=1)
    interest_rate: Rate = Field(0.07, ge=0, le=0.5)
    amortization_years: int = Field(30, ge=1, le=40)
    points_pct: Rate = Field(0.0, ge=0, le=0.1, description="Loan fees as a share of the loan")


class Deal(_Frozen):
    """Everything needed to underwrite one income property over a hold period."""

    # Acquisition
    purchase_price: float = Field(gt=0)
    closing_costs_pct: Rate = Field(0.03, ge=0, le=0.25)
    rehab_cost: float = Field(0.0, ge=0)
    after_repair_value: float | None = Field(
        None, gt=0, description="Value after rehab; defaults to the purchase price"
    )

    # Income (monthly, year-one dollars)
    monthly_rent: float = Field(ge=0, description="Gross scheduled rent for all units")
    other_income_monthly: float = Field(0.0, ge=0)
    vacancy_rate: Rate = Field(0.05, ge=0, le=1)

    # Fixed operating expenses (year-one dollars)
    property_tax_annual: float = Field(0.0, ge=0)
    insurance_annual: float = Field(0.0, ge=0)
    hoa_monthly: float = Field(0.0, ge=0)
    utilities_monthly: float = Field(0.0, ge=0)
    other_expenses_annual: float = Field(0.0, ge=0)

    # Variable operating expenses, as a share of effective gross income
    management_pct: Rate = Field(0.08, ge=0, le=1)
    maintenance_pct: Rate = Field(0.05, ge=0, le=1)
    capex_reserve_pct: Rate = Field(0.05, ge=0, le=1)

    # Growth and exit
    rent_growth: Rate = Field(0.03, ge=-0.5, le=0.5)
    expense_growth: Rate = Field(0.03, ge=-0.5, le=0.5)
    appreciation: Rate = Field(0.03, ge=-0.5, le=0.5)
    hold_years: int = Field(10, ge=1, le=40)
    selling_costs_pct: Rate = Field(0.06, ge=0, le=0.25)
    exit_cap_rate: Rate | None = Field(
        None, gt=0, le=0.5, description="If set, exit value = next-year NOI / exit cap rate"
    )

    financing: Financing | None = Field(default_factory=Financing)

    @model_validator(mode="after")
    def _variable_expenses_below_income(self) -> Deal:
        if self.management_pct + self.maintenance_pct + self.capex_reserve_pct >= 1:
            raise ValueError("variable expenses must total less than 100% of income")
        return self


class YearRow(_Frozen):
    """One year of the pro forma. Balance and value are end-of-year figures."""

    year: int
    gross_potential_rent: float
    vacancy_loss: float
    other_income: float
    effective_gross_income: float
    fixed_expenses: float
    variable_expenses: float
    operating_expenses: float
    noi: float
    debt_service: float
    cash_flow: float
    loan_balance: float
    property_value: float
    equity: float


class Exit(_Frozen):
    year: int
    sale_price: float
    selling_costs: float
    loan_payoff: float
    net_proceeds: float = Field(description="Cash to the investor after costs and payoff")


class Metrics(_Frozen):
    """Headline return metrics. Ratios are None when undefined (e.g. no debt)."""

    total_capital: float = Field(description="Price + closing costs + rehab")
    loan_amount: float
    equity_invested: float = Field(description="Cash in: down payment, closing, rehab, points")
    noi_year1: float
    cash_flow_year1: float
    cap_rate: float | None = Field(description="Year-one NOI / purchase price")
    roic: float | None = Field(description="Year-one NOI / total capital (yield on cost)")
    cash_on_cash: float | None = Field(description="Year-one cash flow / equity invested")
    dscr: float | None = Field(description="Year-one NOI / debt service")
    levered_irr: float | None
    unlevered_irr: float | None
    equity_multiple: float | None = Field(description="Total cash returned / equity invested")
    total_profit: float = Field(description="Total cash returned minus equity invested")
    gross_rent_multiplier: float | None
    rent_to_price: float = Field(description="Monthly rent / purchase price (the '1% rule')")
    break_even_occupancy: float | None = Field(
        description="Occupancy at which income covers expenses and debt service"
    )


class Analysis(_Frozen):
    metrics: Metrics
    years: list[YearRow]
    exit: Exit
    levered_cash_flows: list[float] = Field(description="Year 0..N, investor perspective")
    unlevered_cash_flows: list[float] = Field(description="Year 0..N, all-cash perspective")
