"""Add extensions; add GIN for operating_system

Revision ID: 727301ac6483
Revises: 22367a1b23e9
Create Date: 2024-02-08 11:23:45.975838

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "727301ac6483"
down_revision = "22367a1b23e9"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        # Adds pg_trgm extension (https://www.postgresql.org/docs/current/pgtrgm.html#PGTRGM)
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("COMMIT")
        op.create_index(
            "idx_operating_system",
            "hosts",
            [sa.text("(COALESCE(system_profile_facts -> 'operating_system' ->> 'name', '')) gin_trgm_ops")],
            postgresql_using="gin",
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    op.drop_index("idx_operating_system", table_name="hosts", if_exists=True)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
