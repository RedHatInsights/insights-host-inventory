"""Elongate host_type to 7 characters

Revision ID: 2e14a2172246
Revises: ad19e988bec3
Create Date: 2025-09-23 10:40:57.887088

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2e14a2172246"
down_revision = "ad19e988bec3"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        table_name="system_profiles_static",
        column_name="host_type",
        schema="hbi",
        existing_type=sa.String(length=4),
        type_=sa.String(length=12),
    )


def downgrade():
    op.alter_column(
        table_name="system_profiles_static",
        column_name="host_type",
        schema="hbi",
        existing_type=sa.String(length=12),
        type_=sa.String(length=4),
    )
