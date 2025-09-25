"""Drop immutable fields from staleness

Revision ID: ad19e988bec3
Revises: 94a16dd3106c
Create Date: 2025-09-23 15:05:34.314328

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "ad19e988bec3"
down_revision = "94a16dd3106c"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("staleness", "immutable_time_to_stale", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_stale_warning", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_delete", schema=INVENTORY_SCHEMA)


def downgrade():
    op.add_column(
        "staleness",
        sa.Column("immutable_time_to_stale", sa.Integer(), nullable=False, server_default="104400"),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        "staleness",
        sa.Column("immutable_time_to_stale_warning", sa.Integer(), nullable=False, server_default="604800"),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        "staleness",
        sa.Column("immutable_time_to_delete", sa.Integer(), nullable=False, server_default="1209600"),
        schema=INVENTORY_SCHEMA,
    )
