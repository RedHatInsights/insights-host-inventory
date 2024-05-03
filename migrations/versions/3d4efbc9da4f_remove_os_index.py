"""Remove OS index, set replica identity for tables

Revision ID: 3d4efbc9da4f
Revises: 90879eb18c66
Create Date: 2024-05-03 09:01:46.316467

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3d4efbc9da4f"
down_revision = "90879eb18c66"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.drop_index("idx_operating_system", table_name="hosts", postgresql_concurrently=True, if_exists=True)
        op.execute('ALTER TABLE "groups" REPLICA IDENTITY FULL')
        op.execute('ALTER TABLE "hosts_groups" REPLICA IDENTITY FULL')
        op.execute('ALTER TABLE "staleness" REPLICA IDENTITY FULL')


def downgrade():
    with op.get_context().autocommit_block():
        op.execute('ALTER TABLE "groups" REPLICA IDENTITY DEFAULT')
        op.execute('ALTER TABLE "hosts_groups" REPLICA IDENTITY DEFAULT')
        op.execute('ALTER TABLE "staleness" REPLICA IDENTITY DEFAULT')
        op.create_index(
            "idx_operating_system",
            "hosts",
            [sa.text("(COALESCE(system_profile_facts -> 'operating_system' ->> 'name', '')) gin_trgm_ops")],
            postgresql_using="gin",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
