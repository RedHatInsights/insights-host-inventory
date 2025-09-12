"""Add index on last_check_in and id columns for hosts table

Revision ID: 7439696a760f
Revises: f56c15073693
Create Date: 2025-09-11 12:06:02.487394

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "7439696a760f"
down_revision = "f56c15073693"
branch_labels = None
depends_on = None


def upgrade():
    """Create index idx_hosts_last_check_in_id on partitioned hosts table."""

    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_last_check_in_id",
        index_definition="(last_check_in, id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop index idx_hosts_last_check_in_id from partitioned hosts table."""

    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_last_check_in_id",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
