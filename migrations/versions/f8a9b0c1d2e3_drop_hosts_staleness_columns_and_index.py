"""Drop hosts staleness columns and covering index

Revision ID: f8a9b0c1d2e3
Revises: b3e9f1a2d7c4
Create Date: 2026-05-25 12:00:00.000000

Phase 3 of compute-on-read: remove persisted staleness columns and the covering
index used for group host-count queries (now derived from last_check_in).

Space reclamation: DROP COLUMN removes catalog metadata immediately but does not
reclaim disk from existing heap tuples until VACUUM FULL or pg_repack on the
partitioned hosts table (and its partitions). Plan optional post-deploy maintenance
with DBAs; do not run VACUUM FULL inside this migration.

Downgrade: dev/ephemeral only. Restored columns are nullable and will be NULL until
backfilled; the app no longer writes these fields in production.

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "f8a9b0c1d2e3"
down_revision = "b3e9f1a2d7c4"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_hosts_org_id_deletion_ts"
STALENESS_COLUMNS = ("stale_timestamp", "stale_warning_timestamp", "deletion_timestamp")


def upgrade():
    drop_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        if_exists=True,
    )
    for column_name in STALENESS_COLUMNS:
        op.drop_column("hosts", column_name, schema=INVENTORY_SCHEMA)


def downgrade():
    op.add_column(
        "hosts",
        sa.Column("stale_timestamp", sa.DateTime(timezone=True), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        "hosts",
        sa.Column("stale_warning_timestamp", sa.DateTime(timezone=True), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    op.add_column(
        "hosts",
        sa.Column("deletion_timestamp", sa.DateTime(timezone=True), nullable=True),
        schema=INVENTORY_SCHEMA,
    )
    create_partitioned_table_index(
        table_name="hosts",
        index_name=INDEX_NAME,
        index_definition="(org_id, id, deletion_timestamp)",
    )
