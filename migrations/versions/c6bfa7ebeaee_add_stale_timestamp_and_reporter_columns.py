"""add_stale_timestamp_and_reporter_columns

Revision ID: c6bfa7ebeaee
Revises: b2102a7db5e8
Create Date: 2019-11-08 12:58:11.107559

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c6bfa7ebeaee"
down_revision = "b2102a7db5e8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("stale_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosts", sa.Column("reporter", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("hosts", "stale_timestamp")
    op.drop_column("hosts", "reporter")
