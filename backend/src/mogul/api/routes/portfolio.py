from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from mogul.db.models import (
    Geography,
    Lease,
    Loan,
    Property,
    SavedDeal,
    Transaction,
    Valuation,
)
from mogul.db.session import get_session
from mogul.engine import Deal, monthly_payment, xirr
from mogul.portfolio.categories import CATEGORIES, CategoryId, group_of
from mogul.portfolio.performance import MonthRow, Performance, cash_flows, monthly
from mogul.portfolio.service import (
    PortfolioMonth,
    ProFormaComparison,
    combine_months,
    compare_to_pro_forma,
    evaluate,
    load_properties,
)
from mogul.portfolio.statement import parse_statement

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
DbSession = Annotated[Session, Depends(get_session)]


def _cents(v: Any) -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"not an amount: {v!r}") from e


# Exact on the way in, a plain JSON number on the way out.
Money = Annotated[
    Decimal,
    BeforeValidator(_cents),
    PlainSerializer(float, return_type=float, when_used="json"),
]
PropertyType = Literal["single_family", "multi_2_4", "condo", "multifamily", "commercial", "land"]
Category = CategoryId


# ---------- schemas ----------


class LoanIn(BaseModel):
    lender: str | None = Field(None, max_length=200)
    original_amount: Money = Field(gt=0)
    interest_rate: float = Field(ge=0, le=0.5)
    amortization_years: int = Field(ge=1, le=40)
    start_date: date


class LoanOut(LoanIn):
    monthly_payment: float


class PropertyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(None, max_length=300)
    property_type: PropertyType = "single_family"
    units: int = Field(1, ge=1, le=10_000)
    market_id: int | None = None
    deal_id: int | None = None
    purchase_date: date
    purchase_price: Money = Field(gt=0)
    closing_costs: Money = Field(Decimal(0), ge=0)
    rehab_cost: Money = Field(Decimal(0), ge=0)
    sale_date: date | None = None
    sale_price: Money | None = Field(None, ge=0)
    selling_costs: Money | None = Field(None, ge=0)
    notes: str | None = None
    loan: LoanIn | None = None

    @model_validator(mode="after")
    def _sale_consistent(self) -> "PropertyIn":
        if (self.sale_date is None) != (self.sale_price is None):
            raise ValueError("sale_date and sale_price go together")
        if self.sale_date and self.sale_date < self.purchase_date:
            raise ValueError("sale_date is before purchase_date")
        return self


class PropertyOut(PropertyIn):
    id: int
    market_name: str | None
    loan: LoanOut | None = None


class LeaseIn(BaseModel):
    unit: str = Field("", max_length=50)
    tenant: str | None = Field(None, max_length=200)
    start_date: date
    end_date: date | None = None
    monthly_rent: Money = Field(ge=0)
    deposit: Money = Field(Decimal(0), ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "LeaseIn":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class LeaseOut(LeaseIn):
    id: int
    active: bool


class TransactionIn(BaseModel):
    date: date
    amount: Money = Field(description="Signed: positive money in, negative money out")
    category: Category
    description: str = Field("", max_length=500)


class TransactionPatch(BaseModel):
    category: Category | None = None
    description: str | None = Field(None, max_length=500)


class TransactionOut(TransactionIn):
    id: int
    group: str
    imported: bool


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)


class ImportOut(BaseModel):
    imported: int
    skipped_duplicates: int
    guessed: int
    uncategorized: int


class ValuationIn(BaseModel):
    date: date
    value: Money = Field(gt=0)
    note: str | None = Field(None, max_length=300)


class ValuationOut(ValuationIn):
    id: int


class CategoryOut(BaseModel):
    id: str
    label: str
    group: str


class Holding(BaseModel):
    property: PropertyOut
    performance: Performance


class PropertyDetail(Holding):
    monthly: list[MonthRow]
    leases: list[LeaseOut]
    valuations: list[ValuationOut]
    pro_forma: ProFormaComparison | None


class Totals(BaseModel):
    properties: int
    units: int
    occupied_units: int
    occupancy: float | None
    cost_basis: float
    value: float
    loan_balance: float
    equity: float
    ltv: float | None
    gain: float
    equity_invested: float
    noi_annualized: float
    cash_flow_annualized: float
    scheduled_rent: float
    cap_rate_on_value: float | None
    cash_on_cash: float | None
    irr: float | None
    total_return: float
    distributions: float


class Slice(BaseModel):
    label: str
    value: float
    share: float


class PortfolioOut(BaseModel):
    as_of: date
    totals: Totals
    holdings: list[Holding]
    months: list[PortfolioMonth]
    by_market: list[Slice]
    by_type: list[Slice]


# ---------- helpers ----------


def _property_out(p: Property) -> PropertyOut:
    loan = None
    if p.loan:
        loan = LoanOut(
            lender=p.loan.lender,
            original_amount=p.loan.original_amount,
            interest_rate=p.loan.interest_rate,
            amortization_years=p.loan.amortization_years,
            start_date=p.loan.start_date,
            monthly_payment=monthly_payment(
                float(p.loan.original_amount), p.loan.interest_rate, p.loan.amortization_years
            ),
        )
    return PropertyOut(
        id=p.id,
        name=p.name,
        address=p.address,
        property_type=p.property_type,
        units=p.units,
        market_id=p.market_id,
        market_name=p.market.name if p.market else None,
        deal_id=p.deal_id,
        purchase_date=p.purchase_date,
        purchase_price=p.purchase_price,
        closing_costs=p.closing_costs,
        rehab_cost=p.rehab_cost,
        sale_date=p.sale_date,
        sale_price=p.sale_price,
        selling_costs=p.selling_costs,
        notes=p.notes,
        loan=loan,
    )


def _get_property(db: Session, property_id: int) -> Property:
    found = load_properties(db, [property_id])
    if not found:
        raise HTTPException(404, detail="property not found")
    return found[0]


def _check_refs(db: Session, body: PropertyIn) -> None:
    if body.market_id is not None and db.get(Geography, body.market_id) is None:
        raise HTTPException(422, detail="market_id does not exist")
    if body.deal_id is not None and db.get(SavedDeal, body.deal_id) is None:
        raise HTTPException(422, detail="deal_id does not exist")


def _apply(prop: Property, body: PropertyIn) -> None:
    for field in (
        "name", "address", "property_type", "units", "market_id", "deal_id", "purchase_date",
        "purchase_price", "closing_costs", "rehab_cost", "sale_date", "sale_price",
        "selling_costs", "notes",
    ):  # fmt: skip
        setattr(prop, field, getattr(body, field))
    if body.loan is None:
        prop.loan = None
    else:
        if prop.loan is None:
            prop.loan = Loan()
        for field in ("lender", "original_amount", "interest_rate", "amortization_years",
                      "start_date"):  # fmt: skip
            setattr(prop.loan, field, getattr(body.loan, field))


def _lease_out(x: Lease, today: date) -> LeaseOut:
    return LeaseOut(
        id=x.id,
        unit=x.unit,
        tenant=x.tenant,
        start_date=x.start_date,
        end_date=x.end_date,
        monthly_rent=x.monthly_rent,
        deposit=x.deposit,
        active=x.start_date <= today and (x.end_date is None or x.end_date >= today),
    )


def _tx_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        date=t.date,
        amount=t.amount,
        category=t.category,
        description=t.description,
        group=group_of(t.category).value,
        imported=t.import_hash is not None,
    )


def _slices(pairs: list[tuple[str, float]]) -> list[Slice]:
    agg: dict[str, float] = {}
    for label, v in pairs:
        agg[label] = agg.get(label, 0.0) + v
    total = sum(agg.values()) or 1.0
    return [
        Slice(label=k, value=v, share=v / total)
        for k, v in sorted(agg.items(), key=lambda kv: -kv[1])
    ]


# ---------- portfolio ----------


@router.get("")
def portfolio(db: DbSession) -> PortfolioOut:
    today = date.today()
    evaluated = evaluate(db, load_properties(db), today)
    held = [(p, perf) for p, _, perf in evaluated if not perf.sold]
    flows = [f for _, h, _ in evaluated for f in cash_flows(h, today)]
    first = min((p.purchase_date for p, _, _ in evaluated), default=today)

    def total(attr: str, rows: list[tuple[Property, Performance]] = held) -> float:
        return sum(getattr(perf, attr) or 0.0 for _, perf in rows)

    everything = [(p, perf) for p, _, perf in evaluated]
    value, debt = total("value"), total("loan_balance")
    units, occupied = total("units"), total("occupied_units")
    noi, cf = total("noi_annualized"), total("cash_flow_annualized")
    totals = Totals(
        properties=len(held),
        units=int(units),
        occupied_units=int(occupied),
        occupancy=occupied / units if units else None,
        cost_basis=total("cost_basis"),
        value=value,
        loan_balance=debt,
        equity=value - debt,
        ltv=debt / value if value else None,
        gain=total("gain"),
        equity_invested=total("equity_invested"),
        noi_annualized=noi,
        cash_flow_annualized=cf,
        scheduled_rent=total("scheduled_rent"),
        cap_rate_on_value=noi / value if value else None,
        cash_on_cash=cf / total("equity_invested") if total("equity_invested") else None,
        irr=xirr(flows) if flows and (today - first).days >= 180 else None,
        total_return=total("total_return", everything),
        distributions=total("distributions", everything),
    )
    return PortfolioOut(
        as_of=today,
        totals=totals,
        holdings=[Holding(property=_property_out(p), performance=perf) for p, _, perf in evaluated],
        months=combine_months([monthly(h, today) for _, h, _ in evaluated]),
        by_market=_slices(
            [(p.market.name if p.market else "Unassigned", perf.value) for p, perf in held]
        ),  # fmt: skip
        by_type=_slices([(p.property_type, perf.value) for p, perf in held]),
    )


@router.get("/categories")
def categories() -> list[CategoryOut]:
    return [CategoryOut(id=k, label=label, group=g.value) for k, (label, g) in CATEGORIES.items()]


# ---------- properties ----------


@router.post("/properties", status_code=201)
def create_property(body: PropertyIn, db: DbSession) -> PropertyDetail:
    _check_refs(db, body)
    prop = Property()
    _apply(prop, body)
    db.add(prop)
    db.commit()
    return get_property(prop.id, db)


@router.post("/properties/from-deal/{deal_id}", status_code=201)
def create_from_deal(deal_id: int, purchase_date: date, db: DbSession) -> PropertyDetail:
    """Turn a watchlist deal into an owned property, keeping it linked for comparisons."""
    saved = db.get(SavedDeal, deal_id)
    if saved is None:
        raise HTTPException(404, detail="deal not found")
    deal = Deal.model_validate(saved.inputs)
    fin = deal.financing
    body = PropertyIn(
        name=saved.name,
        address=saved.address,
        deal_id=saved.id,
        purchase_date=purchase_date,
        purchase_price=Decimal(str(deal.purchase_price)),
        closing_costs=Decimal(str(deal.purchase_price * deal.closing_costs_pct)),
        rehab_cost=Decimal(str(deal.rehab_cost)),
        loan=LoanIn(
            original_amount=Decimal(str(deal.purchase_price * (1 - fin.down_payment_pct))),
            interest_rate=fin.interest_rate,
            amortization_years=fin.amortization_years,
            start_date=purchase_date,
        )
        if fin and fin.down_payment_pct < 1
        else None,
    )
    saved.status = "owned"
    return create_property(body, db)


@router.get("/properties/{property_id}")
def get_property(property_id: int, db: DbSession) -> PropertyDetail:
    today = date.today()
    prop = _get_property(db, property_id)
    [(_, holding, perf)] = evaluate(db, [prop], today)
    return PropertyDetail(
        property=_property_out(prop),
        performance=perf,
        monthly=monthly(holding, today),
        leases=[_lease_out(x, today) for x in prop.leases],
        valuations=[
            ValuationOut(id=v.id, date=v.date, value=v.value, note=v.note) for v in prop.valuations
        ],
        pro_forma=compare_to_pro_forma(db, prop, perf),
    )


@router.put("/properties/{property_id}")
def update_property(property_id: int, body: PropertyIn, db: DbSession) -> PropertyDetail:
    _check_refs(db, body)
    prop = _get_property(db, property_id)
    _apply(prop, body)
    db.commit()
    db.expire_all()
    return get_property(property_id, db)


@router.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: int, db: DbSession) -> Response:
    db.delete(_get_property(db, property_id))
    db.commit()
    return Response(status_code=204)


# ---------- leases ----------


@router.post("/properties/{property_id}/leases", status_code=201)
def add_lease(property_id: int, body: LeaseIn, db: DbSession) -> LeaseOut:
    _get_property(db, property_id)
    lease = Lease(property_id=property_id, **body.model_dump())
    db.add(lease)
    db.commit()
    return _lease_out(lease, date.today())


@router.put("/leases/{lease_id}")
def update_lease(lease_id: int, body: LeaseIn, db: DbSession) -> LeaseOut:
    lease = db.get(Lease, lease_id)
    if lease is None:
        raise HTTPException(404, detail="lease not found")
    for k, v in body.model_dump().items():
        setattr(lease, k, v)
    db.commit()
    return _lease_out(lease, date.today())


@router.delete("/leases/{lease_id}", status_code=204)
def delete_lease(lease_id: int, db: DbSession) -> Response:
    lease = db.get(Lease, lease_id)
    if lease is None:
        raise HTTPException(404, detail="lease not found")
    db.delete(lease)
    db.commit()
    return Response(status_code=204)


# ---------- ledger ----------


@router.get("/properties/{property_id}/transactions")
def list_transactions(property_id: int, db: DbSession) -> list[TransactionOut]:
    _get_property(db, property_id)
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.property_id == property_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    return [_tx_out(t) for t in rows]


@router.post("/properties/{property_id}/transactions", status_code=201)
def add_transaction(property_id: int, body: TransactionIn, db: DbSession) -> TransactionOut:
    _get_property(db, property_id)
    t = Transaction(property_id=property_id, **body.model_dump())
    db.add(t)
    db.commit()
    return _tx_out(t)


@router.post("/properties/{property_id}/transactions/import")
def import_transactions(property_id: int, body: ImportIn, db: DbSession) -> ImportOut:
    """Import a bank/property-manager CSV. Lines seen in earlier imports are skipped."""
    _get_property(db, property_id)
    try:
        rows = parse_statement(body.csv)
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from e
    known = set(
        db.scalars(
            select(Transaction.import_hash).where(
                Transaction.property_id == property_id, Transaction.import_hash.is_not(None)
            )
        )
    )
    new = [r for r in rows if r.import_hash not in known]
    db.add_all(
        Transaction(
            property_id=property_id,
            date=r.date,
            amount=r.amount,
            category=r.category,
            description=r.description[:500],
            import_hash=r.import_hash,
        )
        for r in new
    )
    db.commit()
    return ImportOut(
        imported=len(new),
        skipped_duplicates=len(rows) - len(new),
        guessed=sum(r.category_guessed and r.category != "uncategorized" for r in new),
        uncategorized=sum(r.category == "uncategorized" for r in new),
    )


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int, body: TransactionPatch, db: DbSession
) -> TransactionOut:
    t = db.get(Transaction, transaction_id)
    if t is None:
        raise HTTPException(404, detail="transaction not found")
    if body.category is not None:
        t.category = body.category
    if body.description is not None:
        t.description = body.description
    db.commit()
    return _tx_out(t)


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: DbSession) -> Response:
    t = db.get(Transaction, transaction_id)
    if t is None:
        raise HTTPException(404, detail="transaction not found")
    db.delete(t)
    db.commit()
    return Response(status_code=204)


# ---------- valuations ----------


@router.post("/properties/{property_id}/valuations", status_code=201)
def add_valuation(property_id: int, body: ValuationIn, db: DbSession) -> ValuationOut:
    _get_property(db, property_id)
    v = Valuation(property_id=property_id, **body.model_dump())
    db.add(v)
    db.commit()
    return ValuationOut(id=v.id, date=v.date, value=v.value, note=v.note)


@router.delete("/valuations/{valuation_id}", status_code=204)
def delete_valuation(valuation_id: int, db: DbSession) -> Response:
    v = db.get(Valuation, valuation_id)
    if v is None:
        raise HTTPException(404, detail="valuation not found")
    db.delete(v)
    db.commit()
    return Response(status_code=204)
