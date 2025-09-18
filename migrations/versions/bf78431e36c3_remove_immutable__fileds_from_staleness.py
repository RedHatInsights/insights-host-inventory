"""Remove immutable_ fileds from staleness

Revision ID: bf78431e36c3
Revises: 7439696a760f
Create Date: 2025-09-18 14:28:37.426553

"""

import sqlalchemy as sa
from alembic import op

from app.culling import days_to_seconds
from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "bf78431e36c3"
down_revision = "7439696a760f"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("staleness", "immutable_time_to_stale", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_stale_warning", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_delete", schema=INVENTORY_SCHEMA)


def downgrade():
    op.add_column(
        "staleness", sa.Column("immutable_time_to_stale", sa.Integer(104400), nullable=False), schema=INVENTORY_SCHEMA
    )
    op.add_column(
        "staleness",
        sa.Column("immutable_time_to_stale_warning", sa.Integer(days_to_seconds(7)), nullable=False),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        "staleness",
        sa.Column("immutable_time_to_delete", sa.Integer(days_to_seconds(14)), nullable=False),
        schema=INVENTORY_SCHEMA,
    )
