"""Load portfolio rows from the database into the pure performance model."""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mogul.db.models import Geography, Property, SavedDeal
from mogul.engine import Deal, analyze
from mogul.markets.analytics import Obs
from mogul.markets.queries import best_series, observations

from .performance import Holding, LeaseFacts, LoanFacts, MonthRow, Performance, performance


def load_properties(session: Session, ids: list[int] | None = None) -> list[Property]:
    q = select(Property).options(
        selectinload(Property.loan),
        selectinload(Property.leases),
        selectinload(Property.transactions),
        selectinload(Property.valuations),
        selectinload(Property.market),
    )
    if ids is not None:
        q = q.where(Property.id.in_(ids))
    return list(session.scalars(q.order_by(Property.purchase_date, Property.id)))


def value_indexes(session: Session, props: list[Property]) -> dict[int | None, Obs]:
    """Home-value index per market id; the national series stands in when a market has none."""
    us = session.scalar(select(Geography.id).where(Geography.kind == "country"))
    wanted = {p.market_id for p in props if p.market_id} | ({us} if us else set())
    chosen = best_series(session, ["home_value"], wanted)
    obs = observations(session, [s.id for s in chosen.values()])
    by_geo = {gid: obs.get(s.id, []) for (gid, _), s in chosen.items()}
    national = by_geo.get(us, []) if us else []
    return {p.market_id: by_geo.get(p.market_id or -1, []) or national for p in props}


def to_holding(p: Property, index: Obs) -> Holding:
    loan = p.loan
    return Holding(
        purchase_date=p.purchase_date,
        purchase_price=float(p.purchase_price),
        closing_costs=float(p.closing_costs),
        rehab_cost=float(p.rehab_cost),
        units=p.units,
        loan=LoanFacts(
            float(loan.original_amount),
            loan.interest_rate,
            loan.amortization_years,
            loan.start_date,
        )
        if loan
        else None,
        sale_date=p.sale_date,
        sale_price=float(p.sale_price) if p.sale_price is not None else None,
        selling_costs=float(p.selling_costs) if p.selling_costs is not None else None,
        ledger=[(t.date, t.category, float(t.amount)) for t in p.transactions],
        leases=[
            LeaseFacts(x.unit or str(x.id), x.start_date, x.end_date, float(x.monthly_rent))
            for x in p.leases
        ],
        valuations=[(v.date, float(v.value)) for v in p.valuations],
        index=index,
    )


class VarianceRow(BaseModel):
    label: str
    projected: float
    actual: float | None
    variance: float | None
    variance_pct: float | None
    higher_is_better: bool


class ProFormaComparison(BaseModel):
    deal_id: int
    deal_name: str
    projection_year: int
    rows: list[VarianceRow]


def compare_to_pro_forma(
    session: Session, prop: Property, perf: Performance
) -> ProFormaComparison | None:
    """Actual trailing-12 results against the linked deal's projection for the same year."""
    if prop.deal_id is None:
        return None
    saved = session.get(SavedDeal, prop.deal_id)
    if saved is None:
        return None
    deal = Deal.model_validate(saved.inputs)
    analysis = analyze(deal)
    year = min(max(1, math.ceil(perf.months_held / 12)), deal.hold_years)
    proj = analysis.years[year - 1]
    base_value = deal.after_repair_value or deal.purchase_price
    projected_value = base_value * (1 + deal.appreciation) ** (perf.months_held / 12)
    scale = 12 / perf.t12.months if perf.t12.months >= 1 else None
    t = perf.t12

    def actual(v: float) -> float | None:
        return v * scale if scale else None

    rows = [
        ("Income", proj.effective_gross_income, actual(t.income), True),
        # The engine's opex includes capex reserves, so compare against opex + capex.
        ("Opex + capex", proj.operating_expenses, actual(t.operating_expenses + t.capex), False),
        ("NOI after capex", proj.noi, actual(t.noi - t.capex), True),
        ("Debt service", proj.debt_service, actual(t.debt_service), False),
        ("Cash flow", proj.cash_flow, actual(t.cash_flow), True),
        ("Property value", projected_value, perf.value, True),
    ]
    return ProFormaComparison(
        deal_id=saved.id,
        deal_name=saved.name,
        projection_year=year,
        rows=[
            VarianceRow(
                label=label,
                projected=p,
                actual=a,
                variance=None if a is None else a - p,
                variance_pct=None if a is None or not p else (a - p) / abs(p),
                higher_is_better=better,
            )
            for label, p, a, better in rows
        ],
    )


class PortfolioMonth(BaseModel):
    month: date
    value: float
    loan_balance: float
    equity: float
    cash_flow: float
    noi: float


def combine_months(series: list[list[MonthRow]]) -> list[PortfolioMonth]:
    """Sum per-property monthly rows on a shared month-end grid.

    A property contributes value/debt only in months it was held, and its last
    (partial-month) row is attributed to that calendar month.
    """
    totals: dict[tuple[int, int], dict[str, float]] = {}
    last_date: dict[tuple[int, int], date] = {}
    for rows in series:
        for r in rows:
            key = (r.month.year, r.month.month)
            t = totals.setdefault(key, dict.fromkeys(PortfolioMonth.model_fields, 0.0))
            for f in ("value", "loan_balance", "equity", "cash_flow", "noi"):
                t[f] += getattr(r, f)
            last_date[key] = max(last_date.get(key, r.month), r.month)
    return [
        PortfolioMonth(
            month=last_date[k],
            value=t["value"],
            loan_balance=t["loan_balance"],
            equity=t["equity"],
            cash_flow=t["cash_flow"],
            noi=t["noi"],
        )
        for k, t in sorted(totals.items())
    ]


def evaluate(
    session: Session, props: list[Property], as_of: date
) -> list[tuple[Property, Holding, Performance]]:
    indexes = value_indexes(session, props)
    out = []
    for p in props:
        h = to_holding(p, indexes.get(p.market_id, []))
        out.append((p, h, performance(h, as_of)))
    return out
