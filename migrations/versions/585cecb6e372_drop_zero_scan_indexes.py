"""Drop zero-scan indexes

Revision ID: 585cecb6e372
Revises: ea70fa9e4753
Create Date: 2026-03-09 10:11:30.140225

"""

from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "585cecb6e372"
down_revision = "ea70fa9e4753"
branch_labels = None
depends_on = None


def upgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_groups_gin",
    )
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_system_profiles_workloads_gin",
    )
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="org_id_idx",
    )


def downgrade():
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_groups_gin",
        index_definition="USING GIN((groups))",
    )
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_system_profiles_workloads_gin",
        index_definition="USING GIN ((system_profile_facts -> 'workloads'))",
    )
    create_partitioned_table_index(
        table_name="hosts",
        index_name="org_id_idx",
        index_definition="(org_id)",
    )
