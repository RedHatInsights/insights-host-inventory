"""Add composite index on org_id and last_check_in for hosts table

This index optimizes queries that filter by org_id and last_check_in,
including:
- last_check_in_start/last_check_in_end API parameters
- ORDER BY last_check_in sorting
- registered_with per-reporter staleness filter
- Host reaper job (find_stale_host_in_window)

Without this index, PostgreSQL bitmap-combines the org_id lookup with
idx_hosts_last_check_in_id. The composite index enables a single index
range scan (~2-4x faster for medium-to-large orgs).

Revision ID: ea70fa9e4753
Revises: 1607e1679fb9
Create Date: 2026-02-13 15:00:00.000000

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "ea70fa9e4753"
down_revision = "1607e1679fb9"
branch_labels = None
depends_on = None


def upgrade():
    """Create index idx_hosts_org_id_last_check_in on partitioned hosts table."""

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_last_check_in",
        index_definition="(org_id, last_check_in DESC)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop index idx_hosts_org_id_last_check_in from partitioned hosts table."""

    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_org_id_last_check_in",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
