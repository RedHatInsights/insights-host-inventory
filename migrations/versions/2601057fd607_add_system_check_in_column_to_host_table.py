"""Add system_check_in column to host table

Revision ID: 2601057fd607
Revises: ecbe7e63f6d9
Create Date: 2025-02-27 15:00:36.039481

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2601057fd607"
down_revision = "ecbe7e63f6d9"
branch_labels = None
depends_on = None


def upgrade():
    # This columns is going to be nullable until data migration is performed
    # This is going to be kept up to date in the code
    op.add_column("hosts", sa.Column("last_check_in", sa.DateTime(timezone=True), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "last_check_in", schema="hbi")
