"""remove default value from booleans on sysytem profile static table

Revision ID: 014a85b6e197
Revises: 2e14a2172246
Create Date: 2025-10-31 09:51:53.239016

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "014a85b6e197"
down_revision = "2e14a2172246"
branch_labels = None
depends_on = None


def upgrade():
    # Drop server defaults on boolean columns in system_profiles_static
    op.alter_column(
        table_name="system_profiles_static",
        column_name="greenboot_fallback_detected",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=None,
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="is_marketplace",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=None,
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="katello_agent_running",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=None,
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="satellite_managed",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=None,
        nullable=True,
    )


def downgrade():
    # Restore server defaults to FALSE on the boolean columns
    op.alter_column(
        table_name="system_profiles_static",
        column_name="greenboot_fallback_detected",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=sa.text("FALSE"),
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="is_marketplace",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=sa.text("FALSE"),
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="katello_agent_running",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=sa.text("FALSE"),
        nullable=True,
    )
    op.alter_column(
        table_name="system_profiles_static",
        column_name="satellite_managed",
        schema=INVENTORY_SCHEMA,
        existing_type=sa.Boolean,
        server_default=sa.text("FALSE"),
        nullable=True,
    )
