"""Add index for replication with pk and insights_id

Revision ID: 1d2ef4ad13e8
Revises: 002843d515cb
Create Date: 2025-05-12 10:38:12.056799

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1d2ef4ad13e8"
down_revision = "002843d515cb"
branch_labels = None
depends_on = None


def upgrade():
    # Create replication identity index concurrently
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY idx_pk_insights_id
        ON hbi.hosts (id, (canonical_facts->>'insights_id'))
        WHERE (canonical_facts->>'insights_id' IS NOT NULL)
    """)

    # Set the replica identity to the new index
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY USING INDEX idx_pk_insights_id")


def downgrade():
    # Revert the replica identity to the default (primary key)
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY DEFAULT")

    # Drop the hosts_insights_id_idx index concurrently
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_pk_insights_id")
