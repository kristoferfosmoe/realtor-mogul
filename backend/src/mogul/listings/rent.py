"""Rent estimates for listings.

Priority: the user's override, then the rent stated in the listing, then a model
estimate. The model is deliberately simple and labeled low confidence: the market's
typical rent (Zillow ZORI) scaled by bedrooms and size. A comps-based estimate
(RentCast AVM or rental listings) is the planned upgrade.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Rent relative to the market's "typical" unit, by bedrooms (rough US ratios).
BED_FACTOR = {0: 0.75, 1: 0.85, 2: 1.0, 3: 1.2, 4: 1.35, 5: 1.5}
TYPICAL_SQFT = {0: 500, 1: 700, 2: 950, 3: 1400, 4: 1900, 5: 2400}
# Units in small multifamily rent below the all-homes typical, which leans on houses.
MULTI_UNIT_FACTOR = 0.9


class RentEstimate(BaseModel):
    monthly: float
    source: Literal["override", "stated", "model"]
    confidence: Literal["high", "medium", "low"]
    basis: str


def estimate_rent(
    *,
    override: float | None,
    stated: float | None,
    typical_rent: float | None,
    market_label: str,
    units: int,
    beds: float | None,
    sqft: int | None,
) -> RentEstimate | None:
    if override:
        return RentEstimate(
            monthly=override, source="override", confidence="high", basis="your override"
        )
    if stated:
        return RentEstimate(
            monthly=stated, source="stated", confidence="medium", basis="rent stated in the listing"
        )
    if not typical_rent:
        return None
    units = max(1, units)
    beds_known = beds is not None
    per_unit_beds = min(5, max(0, round((beds if beds is not None else 2 * units) / units)))
    f_beds = BED_FACTOR[per_unit_beds]
    f_size = 1.0
    if sqft:
        ratio = (sqft / units) / TYPICAL_SQFT[per_unit_beds]
        f_size = min(1.2, max(0.85, ratio**0.3))
    f_multi = MULTI_UNIT_FACTOR if units > 1 else 1.0
    monthly = typical_rent * f_beds * f_size * f_multi * units
    parts = [
        f"{market_label} typical rent ${typical_rent:,.0f}",
        f"{per_unit_beds}BR ×{f_beds:.2f}",
    ]
    if sqft:
        parts.append(f"size ×{f_size:.2f}")
    if units > 1:
        parts.append(f"{units} units ×{f_multi:.2f}")
    if not beds_known:
        parts.append("beds unknown")
    return RentEstimate(
        monthly=round(monthly, -1), source="model", confidence="low", basis=" · ".join(parts)
    )
