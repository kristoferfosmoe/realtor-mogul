from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
