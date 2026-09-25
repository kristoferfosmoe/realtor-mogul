"""market data: geography, series, observations, ingestion runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "geography",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("size_rank", sa.Integer(), nullable=True),
        sa.Column("external_ids", sa.JSON(), nullable=False),
        sa.UniqueConstraint("kind", "name"),
    )
    op.create_table(
        "market_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "geography_id",
            sa.Integer(),
            sa.ForeignKey("geography.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("segment", sa.String(length=40), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source", "source_key"),
    )
    op.create_index("ix_market_series_geo_metric", "market_series", ["geography_id", "metric"])
    op.create_table(
        "market_observation",
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("market_series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("value", sa.Float(), nullable=False),
    )
    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("series_count", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("raw_path", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_run")
    op.drop_table("market_observation")
    op.drop_index("ix_market_series_geo_metric", table_name="market_series")
    op.drop_table("market_series")
    op.drop_table("geography")
