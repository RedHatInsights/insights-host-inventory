"""remove canonical facts

Revision ID: 3245d92a8f31
Revises: abc123def456
Create Date: 2026-01-19 11:49:58.438639

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "3245d92a8f31"
down_revision = "abc123def456"
branch_labels = None
depends_on = None


def upgrade():
    # Dropping the column automatically drops the indexes
    op.drop_column("hosts", "canonical_facts", schema="hbi")


def downgrade():
    # First restore the canonical_facts column
    op.add_column(
        "hosts",
        sa.Column(
            "canonical_facts",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
            default=dict,
        ),
        schema="hbi",
    )

    # Then restore the original indexes, matching the pre-migration schema
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idxgincanonicalfacts",
        index_definition="USING GIN (canonical_facts)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idxinsightsid",
        index_definition="((canonical_facts ->> 'insights_id'))",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
    create_partitioned_table_index(
        table_name="hosts",
        index_name="hosts_subscription_manager_id_index",
        index_definition="((canonical_facts ->> 'subscription_manager_id'))",
        num_partitions=TABLE_NUM_PARTITIONS,
        unique=False,
    )
