"""remove group name uniqunesness restriction

Revision ID: 6cba58098c84
Revises: 61c1b152246a
Create Date: 2025-08-11 16:13:34.220316

"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '6cba58098c84'
down_revision = '61c1b152246a'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(text("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_ignorecase ON hbi.groups (lower(name), org_id);"))
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_nocase;"))



def downgrade():
    with op.get_context().autocommit_block():
        op.execute(text("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_nocase ON hbi.groups (lower(name), org_id);"))
        op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_ignorecase;"))
