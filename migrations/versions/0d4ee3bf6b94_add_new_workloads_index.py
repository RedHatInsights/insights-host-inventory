"""add new workloads index

Revision ID: 0d4ee3bf6b94
Revises: 43a91b289b3e
Create Date: 2025-09-17 16:34:30.337947

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "0d4ee3bf6b94"
down_revision = "43a91b289b3e"
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
