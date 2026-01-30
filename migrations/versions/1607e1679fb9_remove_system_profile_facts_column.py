"""remove system_profile_facts column

Revision ID: 1607e1679fb9
Revises: eff8fe46beae
Create Date: 2026-01-28 09:31:04.988769

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "1607e1679fb9"
down_revision = "eff8fe46beae"
branch_labels = None
depends_on = None


def upgrade():
    # Drop the column from partitioned hosts table
    # This automatically drops the GIN index and propagates to all partitions
    op.drop_column("hosts", "system_profile_facts", schema="hbi")


def downgrade():
    # Restore the column
    op.add_column(
        "hosts",
        sa.Column(
            "system_profile_facts",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
            default=dict,
        ),
        schema="hbi",
    )

    # Restore the GIN index
    create_partitioned_table_index(
        table_name="hosts",
        index_name="idxsystem_profile_facts",
        index_definition="USING GIN (system_profile_facts)",
        num_partitions=TABLE_NUM_PARTITIONS,
    )
