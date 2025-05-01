"""Add stale_warning_timestamp and deletion_timestamp columns to host table

Revision ID: bfc9f9c35c66
Revises: 84ef628a2a99
Create Date: 2025-04-22 09:30:33.876262

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "bfc9f9c35c66"
down_revision = "84ef628a2a99"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hosts", sa.Column("stale_warning_timestamp", sa.DateTime(timezone=True), nullable=True), schema="hbi"
    )
    op.add_column("hosts", sa.Column("deletion_timestamp", sa.DateTime(timezone=True), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "stale_warning_timestamp", schema="hbi")
    op.drop_column("hosts", "deletion_timestamp", schema="hbi")
