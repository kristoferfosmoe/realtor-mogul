"""portfolio: properties, loans, leases, ledger, valuations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(14, 2)


def _property_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "property_id",
        sa.Integer(),
        sa.ForeignKey("property.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "property",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("property_type", sa.String(length=30), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column(
            "market_id",
            sa.Integer(),
            sa.ForeignKey("geography.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "deal_id",
            sa.Integer(),
            sa.ForeignKey("saved_deal.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("purchase_price", MONEY, nullable=False),
        sa.Column("closing_costs", MONEY, nullable=False),
        sa.Column("rehab_cost", MONEY, nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=True),
        sa.Column("sale_price", MONEY, nullable=True),
        sa.Column("selling_costs", MONEY, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "loan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "property_id",
            sa.Integer(),
            sa.ForeignKey("property.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("lender", sa.String(length=200), nullable=True),
        sa.Column("original_amount", MONEY, nullable=False),
        sa.Column("interest_rate", sa.Float(), nullable=False),
        sa.Column("amortization_years", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
    )
    op.create_table(
        "lease",
        sa.Column("id", sa.Integer(), primary_key=True),
        _property_fk(),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("tenant", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("monthly_rent", MONEY, nullable=False),
        sa.Column("deposit", MONEY, nullable=False),
    )
    op.create_table(
        "ledger_transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        _property_fk(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("import_hash", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("property_id", "import_hash"),
    )
    op.create_index("ix_ledger_property_date", "ledger_transaction", ["property_id", "date"])
    op.create_table(
        "valuation",
        sa.Column("id", sa.Integer(), primary_key=True),
        _property_fk(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", MONEY, nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("valuation")
    op.drop_index("ix_ledger_property_date", table_name="ledger_transaction")
    op.drop_table("ledger_transaction")
    op.drop_table("lease")
    op.drop_table("loan")
    op.drop_table("property")
