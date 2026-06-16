"""Add reporters text[] column and replace per_reporter_staleness GIN index

The idx_gin_per_reporter_staleness index (142GB in production) indexes the
entire JSONB including unique timestamp values, causing massive bloat and
write amplification. The only queries using it check key existence (has_key).

This migration:
1. Adds a derived reporters text[] column storing just the keys
2. Backfills it from per_reporter_staleness keys
3. Adds a GIN index on the reporters array (much smaller, ~2-3GB estimated)
4. Drops the old 142GB GIN index on per_reporter_staleness

Revision ID: a1b2c3d4e5f7
Revises: f9a0b1c2d3e4
Create Date: 2026-06-08 17:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

logger = get_logger(__name__)

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add the reporters column with a server default of empty array
    op.add_column(
        "hosts",
        sa.Column(
            "reporters",
            sa.ARRAY(sa.String(255)),
            nullable=False,
            server_default="{}",
        ),
        schema=INVENTORY_SCHEMA,
    )

    # Step 2: Backfill reporters from per_reporter_staleness keys
    logger.info("Backfilling reporters column from per_reporter_staleness keys...")
    op.execute(
        text(f"""
            UPDATE {INVENTORY_SCHEMA}.hosts
            SET reporters = (
                SELECT ARRAY_AGG(t.key ORDER BY t.key)
                FROM jsonb_object_keys(per_reporter_staleness) AS t(key)
            )
            WHERE per_reporter_staleness IS NOT NULL
              AND per_reporter_staleness != '{{}}'::jsonb
        """)
    )
    logger.info("Backfill complete.")

    # Step 3: Add GIN index on reporters array
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_reporters_gin",
        index_definition="USING GIN (reporters)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )

    # Step 4: Drop the old bloated GIN index on per_reporter_staleness
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_gin_per_reporter_staleness",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    # Recreate the old GIN index on per_reporter_staleness
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_gin_per_reporter_staleness",
        index_definition="USING GIN (per_reporter_staleness)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )

    # Drop the new GIN index on reporters
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_hosts_reporters_gin",
        num_partitions=TABLE_NUM_PARTITIONS,
    )

    # Drop the reporters column
    op.drop_column("hosts", "reporters", schema=INVENTORY_SCHEMA)
