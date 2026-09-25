from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SavedDeal(Base):
    """A property on the watchlist. `inputs` is a serialized engine.Deal.

    Inputs are stored as a document rather than columns so the underwriting model
    can grow without a migration per assumption; metrics are always recomputed.
    """

    __tablename__ = "saved_deal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="watching")
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Geography(Base):
    """A place market data describes: the country, a metro (MSA), and later ZIPs etc.

    `name` follows Zillow's style ("Austin, TX"). Matching the same metro across
    sources (Zillow ids, CBSA codes) goes through `external_ids`.
    """

    __tablename__ = "geography"
    __table_args__ = (UniqueConstraint("kind", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # country | msa
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(2))
    size_rank: Mapped[int | None] = mapped_column(Integer)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    series: Mapped[list[MarketSeries]] = relationship(back_populates="geography")


class MarketSeries(Base):
    """One time series from one source, e.g. Zillow's rent index for Austin."""

    __tablename__ = "market_series"
    __table_args__ = (
        UniqueConstraint("source", "source_key"),
        Index("ix_market_series_geo_metric", "geography_id", "metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geography_id: Mapped[int] = mapped_column(ForeignKey("geography.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(40))
    source_key: Mapped[str] = mapped_column(String(200))
    metric: Mapped[str] = mapped_column(String(40))  # see mogul.ingest.base.METRICS
    segment: Mapped[str] = mapped_column(String(40), default="all")
    unit: Mapped[str] = mapped_column(String(20))  # usd | rate | index
    frequency: Mapped[str] = mapped_column(String(20))  # weekly | monthly | quarterly
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    geography: Mapped[Geography] = relationship(back_populates="series")


class MarketObservation(Base):
    __tablename__ = "market_observation"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("market_series.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)


class IngestionRun(Base):
    """Audit log of every ingestion attempt, successful or not."""

    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | error
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    series_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Portfolio: what is actually owned. Money here is exact (NUMERIC), unlike the
# engine's projections, because it records real transactions.
# ---------------------------------------------------------------------------

Money = Numeric(14, 2)


class Property(Base):
    __tablename__ = "property"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    property_type: Mapped[str] = mapped_column(String(30), default="single_family")
    units: Mapped[int] = mapped_column(Integer, default=1)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("geography.id", ondelete="SET NULL"))
    # The underwriting this purchase was based on, for actual-vs-projected.
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("saved_deal.id", ondelete="SET NULL"))
    purchase_date: Mapped[date] = mapped_column(Date)
    purchase_price: Mapped[Decimal] = mapped_column(Money)
    closing_costs: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    rehab_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    sale_date: Mapped[date | None] = mapped_column(Date)
    sale_price: Mapped[Decimal | None] = mapped_column(Money)
    selling_costs: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    loan: Mapped[Loan | None] = relationship(
        back_populates="property", cascade="all, delete-orphan", uselist=False
    )
    leases: Mapped[list[Lease]] = relationship(
        back_populates="property", cascade="all, delete-orphan", order_by="Lease.start_date"
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="property", cascade="all, delete-orphan", order_by="Transaction.date"
    )
    valuations: Mapped[list[Valuation]] = relationship(
        back_populates="property", cascade="all, delete-orphan", order_by="Valuation.date"
    )
    market: Mapped[Geography | None] = relationship()


class Loan(Base):
    """The acquisition mortgage: fixed rate, fully amortizing, one per property for now."""

    __tablename__ = "loan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("property.id", ondelete="CASCADE"), unique=True
    )
    lender: Mapped[str | None] = mapped_column(String(200))
    original_amount: Mapped[Decimal] = mapped_column(Money)
    interest_rate: Mapped[float] = mapped_column(Float)
    amortization_years: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)

    property: Mapped[Property] = relationship(back_populates="loan")


class Lease(Base):
    __tablename__ = "lease"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("property.id", ondelete="CASCADE"))
    unit: Mapped[str] = mapped_column(String(50), default="")
    tenant: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # None = month-to-month / open
    monthly_rent: Mapped[Decimal] = mapped_column(Money)
    deposit: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))

    property: Mapped[Property] = relationship(back_populates="leases")


class Transaction(Base):
    """One ledger line. Amounts are signed like a bank statement: + in, - out."""

    __tablename__ = "ledger_transaction"
    __table_args__ = (
        UniqueConstraint("property_id", "import_hash"),
        Index("ix_ledger_property_date", "property_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("property.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    category: Mapped[str] = mapped_column(String(40))  # see mogul.portfolio.categories
    description: Mapped[str] = mapped_column(String(500), default="")
    # Set for CSV imports so re-importing the same statement skips known lines.
    import_hash: Mapped[str | None] = mapped_column(String(64))

    property: Mapped[Property] = relationship(back_populates="transactions")


class Valuation(Base):
    """A point-in-time value (appraisal, broker opinion, own estimate).

    Between valuations, value is carried forward with the market's home-value index.
    """

    __tablename__ = "valuation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("property.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Money)
    note: Mapped[str | None] = mapped_column(String(300))

    property: Mapped[Property] = relationship(back_populates="valuations")
