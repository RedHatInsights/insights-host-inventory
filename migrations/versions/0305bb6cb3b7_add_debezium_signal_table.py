"""Add debezium signal table

Revision ID: 0305bb6cb3b7
Revises: 91110801bc8e
Create Date: 2025-09-03 15:56:31.038074

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0305bb6cb3b7"
down_revision = "91110801bc8e"
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
