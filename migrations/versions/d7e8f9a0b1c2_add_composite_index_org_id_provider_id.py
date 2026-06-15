"""Add composite index (org_id, provider_id) on hosts table

This index optimizes the MQ host deduplication query pattern:
  WHERE org_id = ? AND provider_id = ? ORDER BY modified_on DESC LIMIT 1

Without this index, PostgreSQL performs a sequential scan or bitmap
combine on the org_id partition, causing 750ms+ latencies for orgs
with many hosts sharing the same canonical facts.

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
Create Date: 2026-06-08 17:00:00.000000

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "d7e8f9a0b1c2"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    """Create index idx_hosts_org_id_provider_id on partitioned hosts table."""

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_provider_id",
        index_definition="(org_id, provider_id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop index idx_hosts_org_id_provider_id from partitioned hosts table."""

    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_provider_id",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
