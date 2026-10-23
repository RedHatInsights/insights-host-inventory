"""Add python_purls column to system_profiles_dynamic

Mirror of the java_purls migration for third-party Python packages. Adds the
python_purls column (text[] / ARRAY(String)) to the partitioned
system_profiles_dynamic table. It stores the pkg:pypi package URLs (purls) for
Python packages detected on a host and is declared on the
HostDynamicSystemProfile ORM model; without this migration the column is missing
from a real database and host ingestion fails with
"'python_purls' is an invalid keyword argument for HostDynamicSystemProfile".

Nullable with a NULL default -> metadata-only ADD COLUMN (no table rewrite);
adding it to the partitioned parent propagates to every child partition.

Revision ID: 5160d6a8448a
Revises: a879660ecf36
Create Date: 2026-10-07 23:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

SP_DYNAMIC_TABLE_NAME = "system_profiles_dynamic"

# revision identifiers, used by Alembic.
revision = "5160d6a8448a"
down_revision = "a879660ecf36"
branch_labels = None
depends_on = None


def upgrade():
    """Add the nullable python_purls text[] column to system_profiles_dynamic."""
    op.add_column(
        SP_DYNAMIC_TABLE_NAME,
        sa.Column("python_purls", sa.ARRAY(sa.String), nullable=True),
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    """Drop the python_purls column from system_profiles_dynamic."""
    op.drop_column(SP_DYNAMIC_TABLE_NAME, "python_purls", schema=INVENTORY_SCHEMA)
