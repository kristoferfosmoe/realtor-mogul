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


def test_comps_rank_below_stated_rent_and_above_the_model() -> None:
    from datetime import UTC, datetime

    from mogul.listings.rent import Comp, CompsEstimate

    comps = CompsEstimate(
        per_unit=1450,
        low=1300,
        high=1600,
        units=2,
        comps=[Comp(address="a", rent=1400), Comp(address="b", rent=1500)],
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    kw = dict(market_label="Memphis", units=2, beds=4, sqft=None, comps=comps)
    assert estimate_rent(override=None, stated=2500, typical_rent=1000, **kw).source == "stated"
    r = estimate_rent(override=None, stated=None, typical_rent=1000, **kw)
    assert r is not None and (r.source, r.confidence, r.monthly) == ("comps", "medium", 2900)
    assert r.basis == (
        "RentCast AVM $1,450 (range $1,300–$1,600) from 2 comps, 2026-09-01 · 2 units"
    )


def test_hud_fair_market_rent_fallback() -> None:
    from mogul.listings.rent import ZipFactor

    fmr = {"0br": 900, "1br": 1000, "2br": 1200, "3br": 1500, "4br": 1700}
    kw = dict(override=None, stated=None, typical_rent=None, market_label="Jackson", fmr=fmr)
    three = estimate_rent(units=1, beds=3, sqft=None, **kw)
    assert three is not None and three.monthly == 1500
    assert three.basis == "Jackson HUD fair market rent 3BR $1,500"
    # HUD's own rule: 5BR = 4BR + 15%. Duplex: per-unit FMR, no multifamily discount.
    five = estimate_rent(units=1, beds=5, sqft=None, **kw)
    assert five is not None and five.monthly == 1950  # 1700 × 1.15 = 1955
    duplex = estimate_rent(units=2, beds=4, sqft=None, **kw)
    assert duplex is not None and duplex.monthly == 2400 and "2 units" in duplex.basis
    # The ZIP adjustment is clamped.
    rich = estimate_rent(units=1, beds=2, sqft=None, zip_factor=ZipFactor("1", 3.0), **kw)
    assert rich is not None and rich.monthly == 1620 and "ZIP 1 ×1.35" in rich.basis
    assert estimate_rent(units=1, beds=2, sqft=None, **{**kw, "fmr": None}) is None
