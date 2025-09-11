"""Add debezium signal table

Revision ID: f56c15073693
Revises: b85583af35ca
Create Date: 2025-09-11 12:01:37.297272

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f56c15073693"
down_revision = "b85583af35ca"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "debezium_signal",
        sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("data", sa.String(), nullable=True),
        schema="hbi",
    )


def downgrade():
    op.drop_table("debezium_signal", schema="hbi")
