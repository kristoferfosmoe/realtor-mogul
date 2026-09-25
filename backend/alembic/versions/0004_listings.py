"""listings, listing events, buy boxes

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("zip", sa.String(length=10), nullable=True),
        sa.Column("address_key", sa.String(length=300), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "market_id",
            sa.Integer(),
            sa.ForeignKey("geography.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("property_type", sa.String(length=30), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("units_inferred", sa.Boolean(), nullable=False),
        sa.Column("beds", sa.Float(), nullable=True),
        sa.Column("baths", sa.Float(), nullable=True),
        sa.Column("sqft", sa.Integer(), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("hoa_monthly", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("listed_date", sa.Date(), nullable=True),
        sa.Column("days_on_market", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("stated_rent", sa.Float(), nullable=True),
        sa.Column("rent_override", sa.Float(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_id"),
    )
    op.create_index("ix_listing_address_key", "listing", ["address_key"])
    op.create_index("ix_listing_status", "listing", ["status"])
    op.create_table(
        "listing_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("listing.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("event", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
    )
    op.create_table(
        "buy_box",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("buy_box")
    op.drop_table("listing_event")
    op.drop_index("ix_listing_status", table_name="listing")
    op.drop_index("ix_listing_address_key", table_name="listing")
    op.drop_table("listing")
