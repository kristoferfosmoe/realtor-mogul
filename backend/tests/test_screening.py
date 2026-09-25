from datetime import date

import pytest

from mogul.listings.buybox import Assumptions, Criteria
from mogul.listings.rent import estimate_rent
from mogul.listings.scoring import ListingFacts, evaluate, filter_reasons
from mogul.markets.analytics import SeriesStats

FACTS = ListingFacts(
    price=180_000,
    property_type="single_family",
    status="active",
    market_id=1,
    market_label="Memphis",
    beds=3,
    days_on_market=10,
    year_built=1990,
    hoa_monthly=None,
)
RENT_STATS = SeriesStats(latest=1500, latest_date=date(2026, 8, 31), cagr_5y=0.025)


def _rent(monthly: float, confidence: str = "low"):  # type: ignore[no-untyped-def]
    source = {"high": "override", "medium": "stated", "low": "model"}[confidence]
    return estimate_rent(
        override=monthly if source == "override" else None,
        stated=monthly if source == "stated" else None,
        typical_rent=monthly if source == "model" else None,
        market_label="Memphis",
        units=1,
        beds=2,
        sqft=None,
    )


def test_rent_priority_and_model() -> None:
    kw = dict(market_label="Memphis", units=1, beds=3, sqft=1400)
    assert estimate_rent(override=2000, stated=1800, typical_rent=1500, **kw).source == "override"
    assert estimate_rent(override=None, stated=1800, typical_rent=1500, **kw).source == "stated"
    model = estimate_rent(override=None, stated=None, typical_rent=1500, **kw)
    assert model is not None and model.monthly == 1800  # 1500 x 1.2 (3BR), size x1.0
    assert model.confidence == "low" and "3BR" in model.basis
    assert estimate_rent(override=None, stated=None, typical_rent=None, **kw) is None


def test_multi_unit_rent_scales_per_unit() -> None:
    r = estimate_rent(
        override=None, stated=None, typical_rent=1000, market_label="X", units=3, beds=6, sqft=None
    )
    assert r is not None and r.monthly == 2700  # 3 units x 2BR x 0.9 multifamily factor
    assert "3 units ×0.90" in r.basis


def test_size_adjustment_is_clamped() -> None:
    tiny = estimate_rent(
        override=None, stated=None, typical_rent=1000, market_label="X", units=1, beds=2, sqft=100
    )
    assert tiny is not None and tiny.monthly == 850  # floor 0.85


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"status": "pending"}, "status pending"),
        ({"price": 900_000}, "above max price"),
        ({"property_type": "land"}, "type land"),
        ({"market_id": 2}, "outside selected markets"),
    ],
)
def test_filters(change: dict, reason: str) -> None:  # type: ignore[type-arg]
    facts = ListingFacts(**{**FACTS.__dict__, **change})
    assert reason in filter_reasons(facts, Criteria(market_ids=[1]))


def test_passing_listing_has_no_filter_reasons() -> None:
    assert filter_reasons(FACTS, Criteria()) == []


def _eval(monthly_rent: float, confidence: str = "high", share: float = 0.0):  # type: ignore[no-untyped-def]
    return evaluate(
        FACTS,
        _rent(monthly_rent, confidence),
        Criteria(),
        Assumptions(),
        interest_rate=0.07,
        rent_stats=RENT_STATS,
        value_stats=None,
        market_share=share,
    )


def test_strong_rent_is_a_buy() -> None:
    ev = _eval(2400)
    assert all(c.passed for c in ev.checks)
    assert ev.signal in ("BUY", "STRONG BUY")
    assert ev.deal.rent_growth == pytest.approx(0.025)  # market 5y CAGR, within the cap
    assert ev.deal.property_tax_annual == pytest.approx(180_000 * 0.011)


def test_weak_rent_is_a_pass() -> None:
    ev = _eval(1100)
    assert ev.signal == "PASS"
    assert any(r.tone == "down" and r.text.startswith("Levered IRR") for r in ev.reasons)


def test_score_rewards_confidence_and_diversification() -> None:
    sure, unsure = _eval(2000, "high"), _eval(2000, "low")
    assert sure.score > unsure.score
    concentrated = _eval(2000, "high", share=0.8)
    assert concentrated.score < sure.score
    assert any("already in Memphis" in r.text for r in concentrated.reasons)


def test_growth_is_capped_and_fixed_mode_ignores_market() -> None:
    hot = SeriesStats(latest=1, latest_date=date(2026, 1, 1), cagr_5y=0.12)
    ev = evaluate(FACTS, _rent(2000, "high"), Criteria(), Assumptions(), interest_rate=0.07,
                  rent_stats=hot, value_stats=hot)  # fmt: skip
    assert ev.deal.rent_growth == 0.03 and ev.deal.appreciation == 0.03
    fixed = evaluate(FACTS, _rent(2000, "high"), Criteria(), Assumptions(growth="fixed"),
                     interest_rate=0.07, rent_stats=hot, value_stats=hot)  # fmt: skip
    assert fixed.deal.rent_growth == 0.025 and fixed.deal.appreciation == 0.03


def test_all_cash_buy_box_has_no_loan() -> None:
    ev = evaluate(FACTS, _rent(2000, "high"), Criteria(), Assumptions(down_payment_pct=1),
                  interest_rate=0.07, rent_stats=None, value_stats=None)  # fmt: skip
    assert ev.deal.financing is None and ev.metrics.dscr is None
    assert next(c for c in ev.checks if c.name == "DSCR").passed
