"""Add GIN index on system_profiles_dynamic.workloads for containment queries

Now that workload boolean filters use the @> containment operator instead of
CAST(#>> ... AS BOOLEAN), a GIN index can accelerate these queries. The GIN
index supports @>, ?, ?|, and ?& operators on JSONB columns.

This replaces the previously dropped idx_system_profiles_dynamic_workloads_gin
which was unused because the old filter used #>> (path extraction) which is not
GIN-indexable.

Revision ID: f9a0b1c2d3e4
Revises: b3e9f1a2d7c4
Create Date: 2026-06-08 17:20:00.000000

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "f9a0b1c2d3e4"
down_revision = "b3e9f1a2d7c4"
branch_labels = None
depends_on = None


def upgrade():
    """Create GIN index on system_profiles_dynamic.workloads."""

    create_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_sp_dynamic_workloads_gin",
        index_definition="USING GIN (workloads jsonb_path_ops)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop GIN index on system_profiles_dynamic.workloads."""

    drop_partitioned_table_index(
        table_name="system_profiles_dynamic",
        index_name="idx_sp_dynamic_workloads_gin",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
