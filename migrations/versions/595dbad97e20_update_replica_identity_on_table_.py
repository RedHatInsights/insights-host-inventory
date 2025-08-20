"""Update replica identity on table partitions

Revision ID: 595dbad97e20
Revises: 6714f3063d90
Create Date: 2025-08-14 15:41:29.851439
"""

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import MIGRATION_MODE
from migrations.helpers import TABLE_NUM_PARTITIONS
from migrations.helpers import validate_num_partitions

# revision identifiers, used by Alembic.
revision = "595dbad97e20"
down_revision = "6714f3063d90"
branch_labels = None
depends_on = None

"""
This migration updates the replica identity on table partitions
to use the composite unique index (org_id, id/host_id, insights_id),
which is required for logical replication.

Previous migrations updated the replica identity on the parent tables,
but we later discovered that these changes do not automatically
cascade to child partitions, so each partition must be updated individually.
"""


def upgrade():
    validate_num_partitions(TABLE_NUM_PARTITIONS)

    def set_replica_identity_if_index_exists(schema: str, table: str, index: str):
        result = (
            op.get_bind()
            .execute(
                text("""
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = :schema
                  AND tablename = :table
                  AND indexname = :index
            """),
                {"schema": schema, "table": table, "index": index},
            )
            .fetchone()
        )

        if result:
            op.execute(text(f"ALTER TABLE {schema}.{table} REPLICA IDENTITY USING INDEX {index};"))
        else:
            print(f"Index '{index}' does not exist on table '{schema}.{table}'. Skipping replica identity update.")

    for i in range(TABLE_NUM_PARTITIONS):
        # In managed environments, this index was created concurrently on the hosts table partitions,
        # unlike automated environments, where index creation cascades automatically from the parent table.
        # This is why the partition indexes for the hosts table ended up having two different naming schemes.
        hosts_index_name = (
            f"hosts_p{i}_replica_identity_idx"
            if MIGRATION_MODE == "managed"
            else f"hosts_p{i}_org_id_id_insights_id_idx"
        )
        hosts_table = f"hosts_p{i}"
        set_replica_identity_if_index_exists(INVENTORY_SCHEMA, hosts_table, hosts_index_name)

        sp_static_table = f"system_profiles_static_p{i}"
        sp_static_index = f"{sp_static_table}_org_id_host_id_insights_id_idx"
        set_replica_identity_if_index_exists(INVENTORY_SCHEMA, sp_static_table, sp_static_index)

        sp_dynamic_table = f"system_profiles_dynamic_p{i}"
        sp_dynamic_index = f"{sp_dynamic_table}_org_id_host_id_insights_id_idx"
        set_replica_identity_if_index_exists(INVENTORY_SCHEMA, sp_dynamic_table, sp_dynamic_index)


def downgrade():
    validate_num_partitions(TABLE_NUM_PARTITIONS)

    for i in range(TABLE_NUM_PARTITIONS):
        hosts_partition_name = f"{INVENTORY_SCHEMA}.hosts_p{i}"
        op.execute(text(f"ALTER TABLE {hosts_partition_name} REPLICA IDENTITY DEFAULT;"))

        sp_static_partition_name = f"{INVENTORY_SCHEMA}.system_profiles_static_p{i}"
        op.execute(text(f"ALTER TABLE {sp_static_partition_name} REPLICA IDENTITY DEFAULT;"))

        sp_dynamic_partition_name = f"{INVENTORY_SCHEMA}.system_profiles_dynamic_p{i}"
        op.execute(text(f"ALTER TABLE {sp_dynamic_partition_name} REPLICA IDENTITY DEFAULT;"))
