"""Add covering index for group host count query

Revision ID: a7b8c9d0e1f2
Revises: 173077b5db8c
Create Date: 2026-03-24 12:00:00.000000
"""

from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "173077b5db8c"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_hosts_org_id_deletion_ts"


def upgrade():
    create_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        index_definition="(org_id, id, deletion_timestamp)",
    )


def downgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        if_exists=True,
    )
