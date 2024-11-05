"""Create account_staleness_culling table

Revision ID: fc4921790a66
Revises: 2e3c52165bf0
Create Date: 2023-07-20 15:34:34.073988

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.culling import days_to_seconds

# revision identifiers, used by Alembic.
revision = "fc4921790a66"
down_revision = "2e3c52165bf0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_staleness_culling",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("account", sa.String(length=10), nullable=True),
        # This value is in seconds (28 hrs)
        sa.Column(
            "conventional_staleness_delta", sa.String(length=36), default=f"{days_to_seconds(1)}", nullable=False
        ),
        # This value is in seconds (7 days)
        sa.Column(
            "conventional_stale_warning_delta", sa.String(length=36), default=f"{days_to_seconds(7)}", nullable=False
        ),
        # This value is in seconds (14 days)
        sa.Column(
            "conventional_culling_delta", sa.String(length=36), default=f"{days_to_seconds(14)}", nullable=False
        ),
        # This value is in seconds (2 days)
        sa.Column("immutable_staleness_delta", sa.String(length=36), default=f"{days_to_seconds(2)}", nullable=False),
        # This value is in seconds (120 days)
        sa.Column(
            "immutable_stale_warning_delta", sa.String(length=36), default=f"{days_to_seconds(120)}", nullable=False
        ),
        # This value is in seconds (180 days)
        sa.Column("immutable_culling_delta", sa.String(length=36), default=f"{days_to_seconds(180)}", nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_on", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("idxaccstaleorgid", "account_staleness_culling", ["org_id"])


def downgrade():
    op.drop_index("idxaccstaleorgid")
    op.drop_table("account_staleness_culling")
