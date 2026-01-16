"""Update hosts_app_data_patch columns

Revision ID: b2c3d4e5f6a7
Revises: abc123def456
Create Date: 2026-01-16 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "abc123def456"
branch_labels = None
depends_on = None

TABLE_NAME = "hosts_app_data_patch"


def upgrade():
    # Drop old columns
    op.drop_column(TABLE_NAME, "installable_advisories", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "template", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "rhsm_locked_version", schema=INVENTORY_SCHEMA)

    # Add new columns for advisory counts (applicable and installable by type)
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhsa_applicable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhba_applicable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhea_applicable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_other_applicable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhsa_installable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhba_installable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_rhea_installable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("advisories_other_installable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )

    # Add new columns for package counts
    op.add_column(
        TABLE_NAME,
        sa.Column("packages_applicable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("packages_installable", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("packages_installed", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )

    # Add new columns for template info
    op.add_column(
        TABLE_NAME,
        sa.Column("template_name", sa.String(255), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("template_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    # Drop new columns
    op.drop_column(TABLE_NAME, "advisories_rhsa_applicable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_rhba_applicable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_rhea_applicable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_other_applicable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_rhsa_installable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_rhba_installable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_rhea_installable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "advisories_other_installable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "packages_applicable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "packages_installable", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "packages_installed", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "template_name", schema=INVENTORY_SCHEMA)
    op.drop_column(TABLE_NAME, "template_uuid", schema=INVENTORY_SCHEMA)

    # Restore old columns
    op.add_column(
        TABLE_NAME,
        sa.Column("installable_advisories", sa.Integer(), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("template", sa.String(255), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("rhsm_locked_version", sa.String(50), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
