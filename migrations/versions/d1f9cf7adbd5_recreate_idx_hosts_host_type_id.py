"""Recreate idx_hosts_host_type_id index

This migration recreates the idx_hosts_host_type_id index that failed to create
in production during migration abc123def456. We drop any existing indexes first
(valid or invalid) and then recreate them.

Revision ID: d1f9cf7adbd5
Revises: 3245d92a8f31
Create Date: 2026-01-22 14:00:00.000000
"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "d1f9cf7adbd5"
down_revision = "3245d92a8f31"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_hosts_host_type_id"


def upgrade():
    # Drop any existing indexes (valid or invalid) from the failed migration abc123def456.
    drop_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        num_partitions=TABLE_NUM_PARTITIONS,
        if_exists=True,
    )

    # Recreate the index on all partitions and the parent table.
    create_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        index_definition="(host_type, id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        num_partitions=TABLE_NUM_PARTITIONS,
        if_exists=True,
    )
