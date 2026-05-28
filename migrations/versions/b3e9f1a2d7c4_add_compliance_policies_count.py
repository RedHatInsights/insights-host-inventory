"""add compliance policies_count generated column

Revision ID: b3e9f1a2d7c4
Revises: d4f7a2b8c1e3
Create Date: 2026-05-28 15:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "b3e9f1a2d7c4"
down_revision = "d4f7a2b8c1e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hosts_app_data_compliance",
        sa.Column(
            "policies_count",
            sa.Integer(),
            sa.Computed("jsonb_array_length(COALESCE(policies, '[]'::jsonb))"),
            nullable=False,
        ),
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    op.drop_column("hosts_app_data_compliance", "policies_count", schema=INVENTORY_SCHEMA)
