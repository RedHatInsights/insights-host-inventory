"""Add covering indexes for Cyndi sync queries

Revision ID: c4e8f2a91b03
Revises: 2bd02d50876e
Create Date: 2026-04-07 18:00:00.000000
"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "c4e8f2a91b03"
down_revision = "2bd02d50876e"
branch_labels = None
depends_on = None

HOSTS_INDEX_NAME = "idx_hosts_covering_for_sync"
SPS_INDEX_NAME = "idx_sps_join_all_queries"


def upgrade():
    create_partitioned_table_index(
        table_name="hosts",
        index_name=HOSTS_INDEX_NAME,
        index_definition="(org_id, id) INCLUDE (host_type, insights_id)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )

    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name=SPS_INDEX_NAME,
        index_definition="(org_id, host_id, (operating_system->>'name'), (bootc_status->'booted'->>'image_digest'))",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name=SPS_INDEX_NAME,
        if_exists=True,
    )

    drop_partitioned_table_index(
        table_name="hosts",
        index_name=HOSTS_INDEX_NAME,
        if_exists=True,
    )
