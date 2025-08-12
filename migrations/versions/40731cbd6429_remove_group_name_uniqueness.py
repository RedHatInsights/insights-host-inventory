"""remove group name uniqueness

Revision ID: 40731cbd6429
Revises: 6714f3063d90
Create Date: 2025-08-12 14:59:36.772127

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "40731cbd6429"
down_revision = "6714f3063d90"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            text("""
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_ignorecase
            ON hbi.groups (lower(name), org_id);
        """)
        )
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_nocase;"))


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            text("""
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_nocase
            ON hbi.groups (lower(name), org_id);
        """)
        )
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_ignorecase;"))
