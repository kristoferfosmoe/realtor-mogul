from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
