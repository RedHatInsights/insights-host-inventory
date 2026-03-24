"""Drop low-usage indexes on system_profiles_static, system_profiles_dynamic, and groups

Revision ID: 173077b5db8c
Revises: 585cecb6e372
Create Date: 2026-03-23 12:00:00.000000

Production evidence (7-11 months of stats from both primary and replica):
  - 6 indexes on system_profiles_static: 0 scans on primary, 0-2791 on replica
  - 1 GIN index on system_profiles_dynamic: 0 scans on primary, 2 per partition on replica
  - 1 index on groups: 0 scans everywhere (316K row table, planner prefers seq scan + filter)
  - 2 replica identity indexes on SP static/dynamic: 0 scans, no longer used for
    logical replication (reset to DEFAULT in migration e54048e82617), redundant
    with the (org_id, host_id) primary key

system_profiles_static receives ~800M-1B write operations across all partitions.
Dropping 8 of ~10 indexes eliminates ~80% of index maintenance overhead per write.
"""

from alembic import op

from app.models.constants import INVENTORY_SCHEMA
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "173077b5db8c"
down_revision = "585cecb6e372"
branch_labels = None
depends_on = None


def upgrade():
    # --- system_profiles_static (partitioned x32) ---
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_status",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_operating_system_multi",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_system_update_method",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_rhc_client_id",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_image_digest",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_host_type",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_replica_identity",
    )

    # --- system_profiles_dynamic (partitioned x32) ---
    drop_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_system_profiles_dynamic_workloads_gin",
    )
    drop_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_system_profiles_dynamic_replica_identity",
    )

    # --- groups (non-partitioned) ---
    op.drop_index("idxorgidungrouped", table_name="groups", schema=INVENTORY_SCHEMA)


def downgrade():
    # --- system_profiles_static ---
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_status",
        index_definition="(bootc_status)",
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_operating_system_multi",
        index_definition=(
            "((operating_system ->> 'name'), "
            "((operating_system ->> 'major')::integer), "
            "((operating_system ->> 'minor')::integer), "
            "org_id) WHERE operating_system IS NOT NULL"
        ),
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_system_update_method",
        index_definition="(system_update_method)",
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_rhc_client_id",
        index_definition="(rhc_client_id)",
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_image_digest",
        index_definition="((bootc_status -> 'booted' ->> 'image_digest'))",
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_host_type",
        index_definition="(host_type)",
    )
    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_replica_identity",
        index_definition="(org_id, host_id, insights_id)",
        unique=True,
    )

    # --- system_profiles_dynamic ---
    create_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_system_profiles_dynamic_workloads_gin",
        index_definition="USING GIN (workloads)",
    )
    create_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_system_profiles_dynamic_replica_identity",
        index_definition="(org_id, host_id, insights_id)",
        unique=True,
    )

    # --- groups ---
    op.create_index(
        "idxorgidungrouped",
        "groups",
        ["org_id", "ungrouped"],
        schema=INVENTORY_SCHEMA,
    )
