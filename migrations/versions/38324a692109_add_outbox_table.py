"""add outbox table

Revision ID: 38324a692109
Revises: 595dbad97e20
Create Date: 2025-08-19 12:39:56.582711

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "38324a692109"
down_revision = "595dbad97e20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("aggregatetype", sa.String(length=255), nullable=False),
        sa.Column("aggregateid", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="hbi",
    )


def downgrade():
    op.drop_table("outbox", schema="hbi")
