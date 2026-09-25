"""Buy-box criteria and the underwriting assumptions applied to every listing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PropertyType = Literal["single_family", "multi_2_4", "condo", "multifamily", "commercial", "land"]


DEFAULT_TYPES: tuple[PropertyType, ...] = ("single_family", "multi_2_4", "condo")


class Criteria(BaseModel):
    # Hard filters: a listing failing any of these is not underwritten.
    market_ids: list[int] = Field(default_factory=list, description="Empty = any market")
    property_types: list[PropertyType] = Field(default_factory=lambda: list(DEFAULT_TYPES))
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(500_000, ge=0)
    min_beds: float | None = Field(None, ge=0)
    max_days_on_market: int | None = Field(None, ge=0)
    min_year_built: int | None = None
    # Return targets: checked after underwriting, and they drive the signal.
    min_levered_irr: float = Field(0.12, ge=-1, le=1)
    min_cash_on_cash: float = Field(0.06, ge=-1, le=1)
    min_dscr: float = Field(1.2, ge=0, le=5)
    min_cap_rate: float | None = Field(None, ge=0, le=1)


class Assumptions(BaseModel):
    down_payment_pct: float = Field(0.25, ge=0, le=1)
    interest_rate: float | None = Field(
        None, ge=0, le=0.5, description="None = current 30Y average plus rate_spread"
    )
    rate_spread: float = Field(0.0075, ge=0, le=0.05, description="Investor-loan premium")
    amortization_years: int = Field(30, ge=1, le=40)
    closing_costs_pct: float = Field(0.03, ge=0, le=0.25)
    rehab_pct: float = Field(0.02, ge=0, le=1, description="Make-ready budget, % of price")
    vacancy_rate: float = Field(0.06, ge=0, le=1)
    management_pct: float = Field(0.08, ge=0, le=1)
    maintenance_pct: float = Field(0.06, ge=0, le=1)
    capex_reserve_pct: float = Field(0.06, ge=0, le=1)
    property_tax_rate: float = Field(0.011, ge=0, le=0.1, description="Annual, % of price")
    insurance_rate: float = Field(0.005, ge=0, le=0.1, description="Annual, % of price")
    growth: Literal["market", "fixed"] = "market"
    rent_growth: float = Field(0.025, ge=-0.2, le=0.2)
    appreciation: float = Field(0.03, ge=-0.2, le=0.2)
    growth_floor: float = Field(0.0, ge=-0.2, le=0.2)
    # Conservative by default: recent 5-year CAGRs include the 2021-22 surge.
    growth_cap: float = Field(0.03, ge=-0.2, le=0.3)
    hold_years: int = Field(7, ge=1, le=40)
    selling_costs_pct: float = Field(0.06, ge=0, le=0.25)
