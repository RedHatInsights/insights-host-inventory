"""Add host_type to hosts table

Revision ID: abc123def456
Revises: a1b2c3d4e5f6
Create Date: 2025-11-18 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "abc123def456"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    # Add host_type column
    # This column is denormalized from system_profiles_static for query performance
    # It is maintained by Python code in Host._derive_host_type()
    op.add_column("hosts", sa.Column("host_type", sa.String(50), nullable=True), schema="hbi")

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_host_type_id",
        index_definition="(host_type, id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    op.drop_column("hosts", "host_type", schema="hbi")
