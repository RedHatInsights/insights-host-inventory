"""Add indexes for display_name, system_profile, and group_name. Remove account index.

Revision ID: 7c97d8464b6b
Revises: 727301ac6483
Create Date: 2024-03-07 11:46:14.512390

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7c97d8464b6b"
down_revision = "727301ac6483"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index("idxdisplay_name", "hosts", ["display_name"], unique=False, if_not_exists=True)
        op.drop_index("idxaccount", table_name="hosts", if_exists=True)
        op.create_index(
            "idxsystem_profile_facts",
            "hosts",
            [sa.text("system_profile_facts jsonb_ops")],
            postgresql_using="gin",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "idxgroups",
            "hosts",
            [sa.text("groups jsonb_ops")],
            postgresql_using="gin",
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    op.drop_index("idxdisplay_name", table_name="hosts", if_exists=True)
    op.drop_index("idxsystem_profile_facts", table_name="hosts", if_exists=True)
    op.drop_index("idxgroups", table_name="hosts", if_exists=True)
    op.create_index("idxaccount", "hosts", ["account"], unique=False)
