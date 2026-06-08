"""Drop redundant idx_hosts_last_check_in_id index

This index on (last_check_in, id) is superseded by idx_hosts_org_id_last_check_in
which provides (org_id, last_check_in DESC). Since all queries that filter on
last_check_in also filter on org_id (tenant isolation), the composite index
with org_id as a leading column is strictly superior.

Production evidence:
  - idx_hosts_last_check_in_id: 0 index scans on primary, 0 on replica
    (7+ months of stats since idx_hosts_org_id_last_check_in was created)
  - The index adds unnecessary write amplification on every host update
    that modifies last_check_in (~800M+ writes/month across partitions)

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-08 17:10:00.000000

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    """Drop redundant idx_hosts_last_check_in_id from partitioned hosts table."""

    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_last_check_in_id",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Recreate idx_hosts_last_check_in_id on partitioned hosts table."""

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_last_check_in_id",
        index_definition="(last_check_in, id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
