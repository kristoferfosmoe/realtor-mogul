"""listing.rent_comps: RentCast rent AVM and comparables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("listing", sa.Column("rent_comps", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("listing", "rent_comps")
