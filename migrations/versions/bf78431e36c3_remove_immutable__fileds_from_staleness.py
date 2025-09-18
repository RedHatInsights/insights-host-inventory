"""Remove immutable_ fileds from staleness

Revision ID: bf78431e36c3
Revises: 7439696a760f
Create Date: 2025-09-18 14:28:37.426553

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.models.constants import INVENTORY_SCHEMA
from app.culling import days_to_seconds

# revision identifiers, used by Alembic.
revision = 'bf78431e36c3'
down_revision = '7439696a760f'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("staleness", "immutable_time_to_stale", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_stale_warning", schema=INVENTORY_SCHEMA)
    op.drop_column("staleness", "immutable_time_to_delete", schema=INVENTORY_SCHEMA)


def downgrade():
    op.add_column("staleness", sa.Column("immutable_time_to_stale", sa.Integer(104400), nullable=False), schema="hbi")
    op.add_column("staleness", sa.Column("immutable_time_to_stale_warning", sa.Integer(days_to_seconds(7)), nullable=False), schema="hbi")
    op.add_column("staleness", sa.Column("immutable_time_to_delete", sa.Integer(days_to_seconds(14)), nullable=False), schema="hbi")