"""Rent estimates for listings.

Priority: the user's override, then the rent stated in the listing, then comparable
rentals (RentCast's AVM, fetched on request), then a model estimate. The model is
deliberately simple and labeled low confidence. It starts from, in order:
1. the metro's typical rent (Zillow ZORI), scaled by bedrooms and size;
2. the metro's HUD Fair Market Rent for the unit's bedroom count, scaled by size;
3. the national typical rent (ZORI), scaled by bedrooms and size.
When Census data covers the listing's ZIP, the result is scaled by how the ZIP's
median gross rent compares with the metro's (or the nation's, for 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple

from pydantic import BaseModel

# Rent relative to the market's "typical" unit, by bedrooms (rough US ratios).
BED_FACTOR = {0: 0.75, 1: 0.85, 2: 1.0, 3: 1.2, 4: 1.35, 5: 1.5}
TYPICAL_SQFT = {0: 500, 1: 700, 2: 950, 3: 1400, 4: 1900, 5: 2400}
# Units in small multifamily rent below the all-homes typical, which leans on houses.
MULTI_UNIT_FACTOR = 0.9
# HUD derives a 5-bedroom FMR as the 4-bedroom FMR plus 15%.
FMR_FIVE_BR_FACTOR = 1.15
# ACS medians are 5-year averages over all renters: trust them for relative
# position, within limits.
ZIP_FACTOR_RANGE = (0.75, 1.35)


class RentEstimate(BaseModel):
    monthly: float
    source: Literal["override", "stated", "comps", "model"]
    confidence: Literal["high", "medium", "low"]
    basis: str


class Comp(BaseModel):
    address: str
    rent: float
    beds: float | None = None
    baths: float | None = None
    sqft: int | None = None
    distance_mi: float | None = None
    days_old: int | None = None
    correlation: float | None = None


class CompsEstimate(BaseModel):
    """RentCast's rent AVM for one unit, and the comparable rentals behind it."""

    per_unit: float
    low: float | None
    high: float | None
    units: int  # the whole property rents for per_unit × units
    comps: list[Comp]
    fetched_at: datetime


class ZipFactor(NamedTuple):
    zip: str
    ratio: float  # ZIP median gross rent ÷ the reference area's (ACS)


def estimate_rent(
    *,
    override: float | None,
    stated: float | None,
    typical_rent: float | None,
    market_label: str,
    units: int,
    beds: float | None,
    sqft: int | None,
    comps: CompsEstimate | None = None,
    fmr: dict[str, float] | None = None,
    zip_factor: ZipFactor | None = None,
) -> RentEstimate | None:
    """`fmr` (HUD, by "0br".."4br") is used only when `typical_rent` is missing."""
    if override:
        return RentEstimate(
            monthly=override, source="override", confidence="high", basis="your override"
        )
    if stated:
        return RentEstimate(
            monthly=stated, source="stated", confidence="medium", basis="rent stated in the listing"
        )
    if comps:
        rng = f" (range ${comps.low:,.0f}–${comps.high:,.0f})" if comps.low and comps.high else ""
        basis = (
            f"RentCast AVM ${comps.per_unit:,.0f}{rng} from {len(comps.comps)} comps, "
            f"{comps.fetched_at:%Y-%m-%d}"
        )
        if comps.units > 1:
            basis += f" · {comps.units} units"
        return RentEstimate(
            monthly=round(comps.per_unit * comps.units, -1),
            source="comps",
            confidence="medium",
            basis=basis,
        )
    units = max(1, units)
    beds_known = beds is not None
    per_unit_beds = min(5, max(0, round((beds if beds is not None else 2 * units) / units)))
    f_size = 1.0
    if sqft:
        ratio = (sqft / units) / TYPICAL_SQFT[per_unit_beds]
        f_size = min(1.2, max(0.85, ratio**0.3))
    if typical_rent:
        f_beds = BED_FACTOR[per_unit_beds]
        f_multi = MULTI_UNIT_FACTOR if units > 1 else 1.0
        per_unit = typical_rent * f_beds * f_size * f_multi
        parts = [
            f"{market_label} typical rent ${typical_rent:,.0f}",
            f"{per_unit_beds}BR ×{f_beds:.2f}",
        ]
    else:
        fmr_beds = min(4, per_unit_beds)
        base = (fmr or {}).get(f"{fmr_beds}br")
        if not base:
            return None
        f_beds = FMR_FIVE_BR_FACTOR if per_unit_beds == 5 else 1.0
        per_unit = base * f_beds * f_size
        parts = [f"{market_label} HUD fair market rent {fmr_beds}BR ${base:,.0f}"]
        if f_beds != 1.0:
            parts.append(f"5BR ×{f_beds:.2f}")
        f_multi = 1.0  # FMRs are per unit already
    if sqft:
        parts.append(f"size ×{f_size:.2f}")
    if zip_factor:
        lo, hi = ZIP_FACTOR_RANGE
        f_zip = min(hi, max(lo, zip_factor.ratio))
        per_unit *= f_zip
        parts.append(f"ZIP {zip_factor.zip} ×{f_zip:.2f}")
    if units > 1:
        parts.append(f"{units} units" + (f" ×{f_multi:.2f}" if f_multi != 1.0 else ""))
    if not beds_known:
        parts.append("beds unknown")
    return RentEstimate(
        monthly=round(per_unit * units, -1),
        source="model",
        confidence="low",
        basis=" · ".join(parts),
    )
