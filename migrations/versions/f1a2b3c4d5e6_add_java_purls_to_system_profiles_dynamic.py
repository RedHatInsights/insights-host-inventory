"""Add java_purls column to system_profiles_dynamic

Adds the java_purls column (text[] / ARRAY(String)) to the partitioned
system_profiles_dynamic table. This column stores the pkg:maven package URLs
(purls) for third-party Java libraries detected on a host and is declared on
the HostDynamicSystemProfile ORM model, but no migration created it -- so it
was missing from a real database.

The column is nullable with a NULL default, so ADD COLUMN is a metadata-only
operation (no table rewrite / backfill). Because system_profiles_dynamic is a
partitioned table, adding the column to the parent automatically propagates it
to every child partition, mirroring the reporters column added to the likewise
partitioned hosts table.

Revision ID: f1a2b3c4d5e6
Revises: 4e2e1fe2f34d
Create Date: 2026-09-13 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

SP_DYNAMIC_TABLE_NAME = "system_profiles_dynamic"

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "77837836a5b3"
branch_labels = None
depends_on = None


def upgrade():
    """
    Add the nullable java_purls text[] column to system_profiles_dynamic.

    Nullable with a NULL default keeps this metadata-only (no rewrite).
    """
    op.add_column(
        SP_DYNAMIC_TABLE_NAME,
        sa.Column("java_purls", sa.ARRAY(sa.String), nullable=True),
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    """
    Drop the java_purls column from system_profiles_dynamic.
    """
    op.drop_column(SP_DYNAMIC_TABLE_NAME, "java_purls", schema=INVENTORY_SCHEMA)
