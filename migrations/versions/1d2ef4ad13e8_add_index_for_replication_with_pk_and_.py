"""Add index for replication with pk and insights_id

Revision ID: 1d2ef4ad13e8
Revises: 002843d515cb
Create Date: 2025-05-12 10:38:12.056799

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "1d2ef4ad13e8"
down_revision = "002843d515cb"
branch_labels = None
depends_on = None


def upgrade():
    # Add the insights_id column as UUID, non-nullable, with default
    op.add_column(
        "hosts",
        sa.Column(
            "insights_id", UUID(as_uuid=False), nullable=False, server_default="00000000-0000-0000-0000-000000000000"
        ),
        schema="hbi",
    )

    # Update insights_id for records where system_profile_facts->>'host_type' = 'edge'
    op.execute("""
        UPDATE hbi.hosts
        SET insights_id = (canonical_facts->>'insights_id')::uuid
        WHERE canonical_facts->>'insights_id' IS NOT NULL
          AND system_profile_facts->>'host_type' = 'edge'
    """)

    # Create the trigger function to sync insights_id
    op.execute("""
        CREATE OR REPLACE FUNCTION hbi.sync_insights_id()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.insights_id = COALESCE(
                (NEW.canonical_facts->>'insights_id')::uuid,
                '00000000-0000-0000-0000-000000000000'
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # Create the trigger
    op.execute("""
        CREATE TRIGGER trigger_sync_insights_id
        BEFORE INSERT OR UPDATE ON hbi.hosts
        FOR EACH ROW EXECUTE FUNCTION hbi.sync_insights_id()
    """)

    # Create a unique index on (id, insights_id, org_id)
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY idx_pk_insights_id_org_id
        ON hbi.hosts (id, insights_id, org_id)
    """)

    # Set the replica identity to the new index
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY USING INDEX idx_pk_insights_id_org_id")


def downgrade():
    # Drop the trigger
    op.execute("DROP TRIGGER IF EXISTS trigger_sync_insights_id ON hbi.hosts")

    # Drop the trigger function
    op.execute("DROP FUNCTION IF EXISTS hbi.sync_insights_id")

    # Revert the replica identity to the default
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY DEFAULT")

    # Drop the unique index
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_pk_insights_id_org_id")

    # Drop the insights_id column
    op.drop_column("hosts", "insights_id", schema="hbi")
