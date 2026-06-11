"""Add composite index (org_id, modified_on DESC) on hosts table

This index optimizes the common host list query pattern:
  WHERE org_id = ? ORDER BY modified_on DESC LIMIT ? OFFSET ?

Revision ID: c5d6e7f8a9b0
Revises: b3e9f1a2d7c4
Create Date: 2026-06-08 16:00:00.000000

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "c5d6e7f8a9b0"
down_revision = "b3e9f1a2d7c4"
branch_labels = None
depends_on = None


def upgrade():
    """Create index idx_hosts_org_id_modified_on on partitioned hosts table."""

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_modified_on",
        index_definition="(org_id, modified_on DESC)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop index idx_hosts_org_id_modified_on from partitioned hosts table."""

    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_modified_on",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
