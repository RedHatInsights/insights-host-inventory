"""Make hosts.stale_timestamp nullable

Revision ID: 41e07d4c1092
Revises: c4e8f2a91b03
Create Date: 2026-04-28

Reversibility: ``downgrade()`` re-applies ``NOT NULL`` and will fail if any row has
``stale_timestamp IS NULL``. After the application begins omitting or clearing this
column, those NULLs are expected, so the migration is not reliably reversible in
production without backfilling NULLs to concrete timestamps first.

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "41e07d4c1092"
down_revision = "c4e8f2a91b03"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "hosts",
        "stale_timestamp",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    # Fails if any host has NULL stale_timestamp; see module docstring.
    op.alter_column(
        "hosts",
        "stale_timestamp",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        schema=INVENTORY_SCHEMA,
    )
