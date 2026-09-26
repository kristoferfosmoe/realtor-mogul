"""remove synthetic demo data

The app no longer ships demo data. This deletes any that an earlier version loaded,
so everything left on screen came from a real source or from the user.

Geographies stay: they are just place names, real sources reuse them by name, and
properties and buy boxes may point at them.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Explicit child deletes: SQLite does not enforce ON DELETE CASCADE by default.
    op.execute(
        "DELETE FROM market_observation WHERE series_id IN "
        "(SELECT id FROM market_series WHERE source = 'demo')"
    )
    op.execute("DELETE FROM market_series WHERE source = 'demo'")
    op.execute(
        "DELETE FROM listing_event WHERE listing_id IN "
        "(SELECT id FROM listing WHERE source = 'demo')"
    )
    op.execute("DELETE FROM listing WHERE source = 'demo'")
    op.execute("DELETE FROM ingestion_run WHERE source IN ('demo', 'demo-listings')")
    # Size ranks on places left without data came from the demo set.
    op.execute(
        "UPDATE geography SET size_rank = NULL "
        "WHERE id NOT IN (SELECT geography_id FROM market_series)"
    )


def downgrade() -> None:
    pass  # deleted demo data is not restored
