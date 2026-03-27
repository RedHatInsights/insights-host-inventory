"""Drop hosts_old and hosts_groups_old tables

Revision ID: 2bd02d50876e
Revises: a7b8c9d0e1f2
Create Date: 2026-03-26 09:57:31.644715

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "2bd02d50876e"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    # Drop old unused tables
    op.drop_table("hosts_groups_old", schema="hbi", if_exists=True)
    op.drop_table("hosts_old", schema="hbi", if_exists=True)


def downgrade():
    # These tables are no longer needed, so we can just drop them
    pass
