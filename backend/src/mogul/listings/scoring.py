"""Screen, underwrite and score a listing against a buy box. Pure: no database access.

Score (0-100) = weighted components, each 0-1:
  returns 40   levered IRR vs target (target = 0.5, +10 pts IRR = 1.0)
  cash 20      cash-on-cash vs target, same scale
  market 15    market rent growth (5y CAGR; 5%/yr = 1.0)
  risk 15      IRR if rent is 10% lower, DSCR headroom, and rent-estimate confidence
  fit 10       1 - share of your portfolio already in this market
Signal: STRONG BUY (all targets met, score >= 85), BUY (all targets met),
WATCH (IRR within 2 pts of target, or one target missed), PASS otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from mogul.engine import Deal, Financing, Metrics, analyze
from mogul.markets.analytics import SeriesStats

from .buybox import Assumptions, Criteria
from .rent import RentEstimate

Signal = Literal["STRONG BUY", "BUY", "WATCH", "PASS"]
Tone = Literal["up", "down", "flat"]
WEIGHTS = {"returns": 40, "cash": 20, "market": 15, "risk": 15, "fit": 10}
CONFIDENCE = {"high": 1.0, "medium": 0.75, "low": 0.45}
STRONG_BUY_SCORE = 85  # meeting every target typically lands 60-90; this marks clear winners


@dataclass(frozen=True)
class ListingFacts:
    price: float
    property_type: str
    status: str
    market_id: int | None
    market_label: str
    beds: float | None
    days_on_market: int | None
    year_built: int | None
    hoa_monthly: float | None


class Check(BaseModel):
    name: str
    value: float | None
    target: float
    passed: bool


class Reason(BaseModel):
    text: str
    tone: Tone


class Evaluation(BaseModel):
    score: float
    signal: Signal
    components: dict[str, float]
    checks: list[Check]
    reasons: list[Reason]
    metrics: Metrics
    stress_irr: float | None
    deal: Deal


def filter_reasons(f: ListingFacts, c: Criteria) -> list[str]:
    """Why a listing fails the hard filters (empty = passes)."""
    out = []
    if f.status != "active":
        out.append(f"status {f.status}")
    if c.market_ids and f.market_id not in c.market_ids:
        out.append("outside selected markets")
    if c.property_types and f.property_type not in c.property_types:
        out.append(f"type {f.property_type}")
    if c.min_price is not None and f.price < c.min_price:
        out.append("below min price")
    if c.max_price is not None and f.price > c.max_price:
        out.append("above max price")
    if c.min_beds is not None and (f.beds or 0) < c.min_beds:
        out.append("too few beds")
    if c.max_days_on_market is not None and (f.days_on_market or 0) > c.max_days_on_market:
        out.append("on market too long")
    if (
        c.min_year_built is not None
        and f.year_built is not None
        and f.year_built < c.min_year_built
    ):
        out.append("too old")
    return out


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _growth(stats: SeriesStats | None, fallback: float, a: Assumptions) -> float:
    if a.growth == "fixed" or stats is None:
        return fallback
    g = stats.cagr_5y if stats.cagr_5y is not None else stats.cagr_3y
    return fallback if g is None else _clamp(g, a.growth_floor, a.growth_cap)


def build_deal(
    f: ListingFacts,
    rent: RentEstimate,
    a: Assumptions,
    interest_rate: float,
    rent_stats: SeriesStats | None,
    value_stats: SeriesStats | None,
) -> Deal:
    return Deal(
        purchase_price=f.price,
        closing_costs_pct=a.closing_costs_pct,
        rehab_cost=f.price * a.rehab_pct,
        monthly_rent=rent.monthly,
        vacancy_rate=a.vacancy_rate,
        property_tax_annual=f.price * a.property_tax_rate,
        insurance_annual=f.price * a.insurance_rate,
        hoa_monthly=f.hoa_monthly or 0.0,
        management_pct=a.management_pct,
        maintenance_pct=a.maintenance_pct,
        capex_reserve_pct=a.capex_reserve_pct,
        rent_growth=_growth(rent_stats, a.rent_growth, a),
        expense_growth=0.03,
        appreciation=_growth(value_stats, a.appreciation, a),
        hold_years=a.hold_years,
        selling_costs_pct=a.selling_costs_pct,
        financing=Financing(
            down_payment_pct=a.down_payment_pct,
            interest_rate=interest_rate,
            amortization_years=a.amortization_years,
        )
        if a.down_payment_pct < 1
        else None,
    )


def evaluate(
    f: ListingFacts,
    rent: RentEstimate,
    c: Criteria,
    a: Assumptions,
    *,
    interest_rate: float,
    rent_stats: SeriesStats | None,
    value_stats: SeriesStats | None,
    market_share: float = 0.0,
) -> Evaluation:
    deal = build_deal(f, rent, a, interest_rate, rent_stats, value_stats)
    m = analyze(deal).metrics
    stress = analyze(deal.model_copy(update={"monthly_rent": rent.monthly * 0.9})).metrics

    checks = [
        Check(name="Levered IRR", value=m.levered_irr, target=c.min_levered_irr,
              passed=(m.levered_irr or -1) >= c.min_levered_irr),
        Check(name="Cash on cash", value=m.cash_on_cash, target=c.min_cash_on_cash,
              passed=(m.cash_on_cash or -1) >= c.min_cash_on_cash),
        Check(name="DSCR", value=m.dscr, target=c.min_dscr,
              passed=m.dscr is None or m.dscr >= c.min_dscr),
    ]  # fmt: skip
    if c.min_cap_rate is not None:
        checks.append(
            Check(
                name="Cap rate",
                value=m.cap_rate,
                target=c.min_cap_rate,
                passed=(m.cap_rate or 0) >= c.min_cap_rate,
            )  # fmt: skip
        )

    irr = m.levered_irr if m.levered_irr is not None else -1.0
    coc = m.cash_on_cash if m.cash_on_cash is not None else -1.0
    rent_growth = None
    if rent_stats:
        rent_growth = rent_stats.cagr_5y if rent_stats.cagr_5y is not None else rent_stats.yoy
    s_irr = stress.levered_irr if stress.levered_irr is not None else -1.0
    dscr_room = 1.0 if m.dscr is None else _clamp((m.dscr - 1.0) / 0.5)
    components = {
        "returns": _clamp(0.5 + (irr - c.min_levered_irr) / 0.10),
        "cash": _clamp(0.5 + (coc - c.min_cash_on_cash) / 0.10),
        "market": _clamp((rent_growth or 0.0) / 0.05),
        "risk": (
            _clamp(0.5 + (s_irr - c.min_levered_irr) / 0.10)
            + dscr_room
            + CONFIDENCE[rent.confidence]
        )
        / 3,  # fmt: skip
        "fit": _clamp(1 - market_share),
    }
    score = round(sum(WEIGHTS[k] * v for k, v in components.items()), 1)

    failed = [ch for ch in checks if not ch.passed]
    signal: Signal
    if not failed:
        signal = "STRONG BUY" if score >= STRONG_BUY_SCORE else "BUY"
    elif irr >= c.min_levered_irr - 0.02 or len(failed) == 1:
        signal = "WATCH"
    else:
        signal = "PASS"

    return Evaluation(
        score=score,
        signal=signal,
        components=components,
        checks=checks,
        reasons=_reasons(f, rent, m, stress.levered_irr, checks, rent_growth, market_share, deal),
        metrics=m,
        stress_irr=stress.levered_irr,
        deal=deal,
    )


def _pct(v: float | None, digits: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def _reasons(
    f: ListingFacts,
    rent: RentEstimate,
    m: Metrics,
    stress_irr: float | None,
    checks: list[Check],
    rent_growth: float | None,
    market_share: float,
    deal: Deal,
) -> list[Reason]:
    out = []
    for ch in checks:
        fmt = (lambda v: "—" if v is None else f"{v:.2f}x") if ch.name == "DSCR" else _pct
        out.append(
            Reason(
                text=f"{ch.name} {fmt(ch.value)} vs {fmt(ch.target)} target",
                tone="up" if ch.passed else "down",
            )
        )
    conf_tone: Tone = (
        "up" if rent.confidence == "high" else "flat" if rent.confidence == "medium" else "down"
    )
    out.append(
        Reason(
            text=f"Rent ${rent.monthly:,.0f}/mo from {rent.basis} ({rent.confidence} confidence)",
            tone=conf_tone,
        )
    )
    if stress_irr is not None:
        out.append(
            Reason(
                text=f"If rent comes in 10% lower, IRR is {_pct(stress_irr)}",
                tone="up" if stress_irr >= 0.08 else "down",
            )
        )
    if rent_growth is not None:
        out.append(
            Reason(
                text=f"{f.market_label} rents growing {_pct(rent_growth)}/yr (5y); "
                f"underwritten at {_pct(deal.rent_growth)} rent growth, "
                f"{_pct(deal.appreciation)} appreciation",
                tone="up" if rent_growth >= 0.03 else "flat" if rent_growth >= 0 else "down",
            )
        )
    else:
        out.append(
            Reason(text="No market rent history; using fixed growth assumptions", tone="flat")
        )
    if market_share >= 0.4:
        out.append(
            Reason(
                text=f"{_pct(market_share, 0)} of your portfolio is already in {f.market_label}",
                tone="down",
            )  # fmt: skip
        )
    rtp = deal.monthly_rent / deal.purchase_price
    out.append(
        Reason(
            text=f"Rent-to-price {_pct(rtp, 2)} (1% rule {'met' if rtp >= 0.01 else 'not met'})",
            tone="up" if rtp >= 0.01 else "flat",
        )  # fmt: skip
    )
    if f.days_on_market is not None and f.days_on_market >= 45:
        out.append(Reason(text=f"{f.days_on_market} days on market: room to negotiate", tone="up"))
    return out
