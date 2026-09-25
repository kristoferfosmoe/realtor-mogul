"""Actual performance of owned properties. Pure: callers pass facts and an as-of date.

Conventions:
- Ledger amounts are signed (+ in, - out). Expenses are reported as positive numbers.
- NOI = income - operating expenses. Capex, debt service and uncategorized lines sit
  below NOI but inside cash flow. Owner transfers are ignored entirely.
- If the ledger has no mortgage payments at all but the property has a loan, scheduled
  payments are imputed (flagged), so cash flow isn't overstated before bank imports.
- Value: the latest valuation on or before a date (the purchase price is the first),
  carried forward by the market's home-value index when one is available.
- Returns to date mark the property to market: value less assumed selling costs, less
  the loan balance, as if sold on the as-of date.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel

from mogul.engine import balance_after, monthly_payment, xirr
from mogul.markets.analytics import Obs, shift_months, value_at

from .categories import Group, group_of

MIN_DAYS_FOR_IRR = 180  # annualizing a few weeks of returns produces nonsense
DEFAULT_SELLING_COSTS = 0.06


@dataclass(frozen=True)
class LoanFacts:
    amount: float
    rate: float
    years: int
    start: date

    @property
    def payment(self) -> float:
        return monthly_payment(self.amount, self.rate, self.years)

    def payments_made(self, on: date) -> int:
        """Level payments due by `on`, the first one month after the loan starts."""
        months = (on.year - self.start.year) * 12 + on.month - self.start.month
        if on.day < self.start.day and on != _month_end(on):
            months -= 1
        return max(0, min(months, self.years * 12))

    def balance(self, on: date) -> float:
        return balance_after(self.amount, self.rate, self.years, self.payments_made(on))


@dataclass(frozen=True)
class LeaseFacts:
    unit: str
    start: date
    end: date | None
    rent: float

    def active(self, on: date) -> bool:
        return self.start <= on and (self.end is None or self.end >= on)


@dataclass(frozen=True)
class Holding:
    purchase_date: date
    purchase_price: float
    closing_costs: float = 0.0
    rehab_cost: float = 0.0
    units: int = 1
    loan: LoanFacts | None = None
    sale_date: date | None = None
    sale_price: float | None = None
    selling_costs: float | None = None
    ledger: Sequence[tuple[date, str, float]] = ()  # (date, category, signed amount)
    leases: Sequence[LeaseFacts] = ()
    valuations: Sequence[tuple[date, float]] = ()
    index: Obs = field(default_factory=list)  # market home-value index


class PeriodTotals(BaseModel):
    months: float  # length of the period actually covered
    income: float
    operating_expenses: float
    noi: float
    capex: float
    debt_service: float
    uncategorized: float
    cash_flow: float


class MonthRow(BaseModel):
    month: date  # month end, or the as-of/sale date for the last month
    income: float
    operating_expenses: float
    noi: float
    capex: float
    debt_service: float
    cash_flow: float
    value: float
    loan_balance: float
    equity: float


class Performance(BaseModel):
    as_of: date
    sold: bool
    months_held: float
    cost_basis: float
    loan_amount: float
    equity_invested: float
    value: float
    value_source: str  # purchase | valuation | indexed | sale
    loan_balance: float
    equity: float
    ltv: float | None
    gain: float  # value (or net sale) minus cost basis
    gain_pct: float | None
    t12: PeriodTotals
    noi_annualized: float | None
    cash_flow_annualized: float | None
    cap_rate_on_cost: float | None
    cap_rate_on_value: float | None
    cash_on_cash: float | None
    irr: float | None
    equity_multiple: float | None
    total_return: float
    distributions: float  # sum of monthly cash flows since purchase
    units: int
    occupied_units: int
    occupancy: float | None
    scheduled_rent: float  # monthly, from active leases
    debt_service_imputed: bool
    uncategorized_count: int


def _month_end(d: date) -> date:
    return (date(d.year + d.month // 12, d.month % 12 + 1, 1)) - timedelta(days=1)


def _index_at(index: Obs, on: date) -> float | None:
    """Index level at a date. Monthly indexes are stamped at month end, so a purchase
    early in the month (or just before the series starts) uses the next print."""
    found = value_at(index, on)
    if found is None and index and (index[0][0] - on).days <= 45:
        return index[0][1]
    return found


def mark(h: Holding, on: date) -> tuple[float, str]:
    """Estimated value on a date, and where it came from."""
    anchors = [(h.purchase_date, h.purchase_price, "purchase")] + [
        (d, v, "valuation") for d, v in sorted(h.valuations)
    ]
    usable = [a for a in anchors if a[0] <= on] or anchors[:1]
    a_date, a_value, source = usable[-1]
    if h.index:
        then, now = _index_at(h.index, a_date), value_at(h.index, on)
        if then and now and on > a_date and now != then:
            return a_value * now / then, "indexed"
    return a_value, source


def _ledger_debt_exists(h: Holding) -> bool:
    return any(group_of(c) is Group.DEBT for _, c, _ in h.ledger)


def _totals(h: Holding, start: date, end: date) -> PeriodTotals:
    """Totals for ledger dates in (start, end], plus imputed debt service if needed."""
    buckets = {g: 0.0 for g in Group}
    for d, category, amount in h.ledger:
        if start < d <= end:
            buckets[group_of(category)] += amount
    # "+ 0.0" turns -0.0 into 0.0 for empty buckets.
    income = buckets[Group.INCOME] + 0.0
    opex = -buckets[Group.OPERATING] + 0.0
    capex = -buckets[Group.CAPITAL] + 0.0
    debt = -buckets[Group.DEBT] + 0.0
    if h.loan and not _ledger_debt_exists(h):
        debt = (h.loan.payments_made(end) - h.loan.payments_made(start)) * h.loan.payment
    other = buckets[Group.UNCATEGORIZED]
    return PeriodTotals(
        months=max(0.0, (end - start).days / 30.4375),
        income=income,
        operating_expenses=opex,
        noi=income - opex,
        capex=capex,
        debt_service=debt,
        uncategorized=other,
        cash_flow=income - opex - capex - debt + other,
    )


def monthly(h: Holding, as_of: date) -> list[MonthRow]:
    end = min(as_of, h.sale_date) if h.sale_date else as_of
    rows: list[MonthRow] = []
    prev = h.purchase_date - timedelta(days=1)  # purchase-day activity counts in month one
    cursor = _month_end(h.purchase_date)
    while prev < end:
        point = min(cursor, end)
        t = _totals(h, prev, point)
        value, _ = mark(h, point)
        balance = h.loan.balance(point) if h.loan else 0.0
        rows.append(
            MonthRow(
                month=point,
                income=t.income,
                operating_expenses=t.operating_expenses,
                noi=t.noi,
                capex=t.capex,
                debt_service=t.debt_service,
                cash_flow=t.cash_flow,
                value=value,
                loan_balance=balance,
                equity=value - balance,
            )
        )
        prev, cursor = point, _month_end(point + timedelta(days=1))
    return rows


def terminal_equity(h: Holding, as_of: date, selling_costs_pct: float) -> tuple[date, float]:
    """Cash to the owner on exit: the actual sale, or a mark-to-market sale on as_of."""
    if h.sale_date and h.sale_price is not None and h.sale_date <= as_of:
        payoff = h.loan.balance(h.sale_date) if h.loan else 0.0
        costs = h.selling_costs if h.selling_costs is not None else 0.0
        return h.sale_date, h.sale_price - costs - payoff
    value, _ = mark(h, as_of)
    payoff = h.loan.balance(as_of) if h.loan else 0.0
    return as_of, value * (1 - selling_costs_pct) - payoff


def cash_flows(
    h: Holding, as_of: date, selling_costs_pct: float = DEFAULT_SELLING_COSTS
) -> list[tuple[date, float]]:
    """Dated equity cash flows: -equity at purchase, monthly net cash, terminal equity."""
    flows = [(h.purchase_date, -_equity_invested(h))]
    flows += [(m.month, m.cash_flow) for m in monthly(h, as_of) if m.cash_flow]
    flows.append(terminal_equity(h, as_of, selling_costs_pct))
    return flows


def _cost_basis(h: Holding) -> float:
    return h.purchase_price + h.closing_costs + h.rehab_cost


def _equity_invested(h: Holding) -> float:
    return _cost_basis(h) - (h.loan.amount if h.loan else 0.0)


def _ratio(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b else None


def performance(
    h: Holding, as_of: date, selling_costs_pct: float = DEFAULT_SELLING_COSTS
) -> Performance:
    sold = bool(h.sale_date and h.sale_date <= as_of)
    end = h.sale_date if sold and h.sale_date else as_of
    rows = monthly(h, as_of)

    t12_start = max(shift_months(end, -12), h.purchase_date - timedelta(days=1))
    t12 = _totals(h, t12_start, end)
    annualize = 12 / t12.months if t12.months >= 1 else None

    if sold and h.sale_price is not None:
        value, source = h.sale_price, "sale"
    else:
        value, source = mark(h, end)
    balance = 0.0 if sold else (h.loan.balance(end) if h.loan else 0.0)
    cost = _cost_basis(h)
    equity_in = _equity_invested(h)
    distributions = sum(r.cash_flow for r in rows)
    _, terminal = terminal_equity(h, as_of, selling_costs_pct)
    net_sale = value - (h.selling_costs or 0.0) if sold else value
    gain = net_sale - cost
    flows = cash_flows(h, as_of, selling_costs_pct)
    held_days = (end - h.purchase_date).days
    occupied = {lease.unit for lease in h.leases if lease.active(end)} if not sold else set()
    noi_ann = t12.noi * annualize if annualize else None
    cf_ann = t12.cash_flow * annualize if annualize else None

    return Performance(
        as_of=as_of,
        sold=sold,
        months_held=held_days / 30.4375,
        cost_basis=cost,
        loan_amount=h.loan.amount if h.loan else 0.0,
        equity_invested=equity_in,
        value=value,
        value_source=source,
        loan_balance=balance,
        equity=value - balance if not sold else 0.0,
        ltv=None if sold else _ratio(balance, value),
        gain=gain,
        gain_pct=_ratio(gain, cost),
        t12=t12,
        noi_annualized=noi_ann,
        cash_flow_annualized=cf_ann,
        cap_rate_on_cost=_ratio(noi_ann, cost),
        cap_rate_on_value=None if sold else _ratio(noi_ann, value),
        cash_on_cash=_ratio(cf_ann, equity_in),
        irr=xirr(flows) if held_days >= MIN_DAYS_FOR_IRR else None,
        equity_multiple=_ratio(distributions + terminal, equity_in),
        total_return=distributions + terminal - equity_in,
        distributions=distributions,
        units=h.units,
        occupied_units=min(len(occupied), h.units),
        occupancy=None if sold else _ratio(min(len(occupied), h.units), h.units),
        scheduled_rent=0.0 if sold else sum(x.rent for x in h.leases if x.active(end)),
        debt_service_imputed=bool(h.loan) and not _ledger_debt_exists(h),
        uncategorized_count=sum(1 for _, c, _ in h.ledger if group_of(c) is Group.UNCATEGORIZED),
    )
