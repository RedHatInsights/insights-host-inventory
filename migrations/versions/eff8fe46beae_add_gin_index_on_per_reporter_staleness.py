"""add gin index on per_reporter_staleness

Revision ID: eff8fe46beae
Revises: 5d158622cabd
Create Date: 2026-02-17 19:46:12.416706

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "eff8fe46beae"
down_revision = "5d158622cabd"
branch_labels = None
depends_on = None


def upgrade():
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idx_gin_per_reporter_staleness",
        index_definition="USING GIN (per_reporter_staleness)",
        num_partitions=TABLE_NUM_PARTITIONS,
        unique=False,
    )


def downgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name="idx_gin_per_reporter_staleness",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
