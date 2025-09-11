"""add new workloads index

Revision ID: ad2d8b8922b9
Revises: 7439696a760f
Create Date: 2025-09-17 11:31:02.434428

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "ad2d8b8922b9"
down_revision = "7439696a760f"
branch_labels = None
depends_on = None


def upgrade():
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_system_profiles_workloads_gin",
        index_definition="USING GIN ((system_profile_facts -> 'workloads'))",
        num_partitions=TABLE_NUM_PARTITIONS,
        unique=False,
    )


def downgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_system_profiles_workloads_gin",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
