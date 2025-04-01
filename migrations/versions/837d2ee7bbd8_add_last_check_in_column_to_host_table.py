"""Add last_check_in column to host table

Revision ID: 837d2ee7bbd8
Revises: 6f44b7ecd7be
Create Date: 2025-03-12 11:39:53.550203

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "837d2ee7bbd8"
down_revision = "6f44b7ecd7be"
branch_labels = None
depends_on = None


def upgrade():
    # This columns is going to be nullable until data migration is performed
    # This is going to be kept up to date in the code
    op.add_column("hosts", sa.Column("last_check_in", sa.DateTime(timezone=True), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "last_check_in", schema="hbi")
