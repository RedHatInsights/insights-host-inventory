"""Remove immutable_ fileds from staleness

Revision ID: bf78431e36c3
Revises: 43a91b289b3e
Create Date: 2025-09-18 14:28:37.426553

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "bf78431e36c3"
down_revision = "43a91b289b3e"
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
