"""Create metadata table to store host-stale notification successful runs

Revision ID: 4f0b36e6cf28
Revises: 1e276ea9970d
Create Date: 2025-01-24 15:30:37.555780

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4f0b36e6cf28"
down_revision = "1e276ea9970d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hbi_metadata",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("last_succeeded", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", "type"),
        schema="hbi",
    )


def downgrade():
    op.drop_table("hbi_metadata", schema="hbi")
