"""Add indexes for display_name, system_profile, and group_name. Remove account index.

Revision ID: 7c97d8464b6b
Revises: 727301ac6483
Create Date: 2024-03-07 11:46:14.512390

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "7c97d8464b6b"
down_revision = "727301ac6483"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idxdisplay_name", "hosts", ["display_name"], unique=False)
    op.execute("CREATE INDEX idxsystem_profile_facts ON hosts USING GIN (system_profile_facts jsonb_ops);")
    op.execute("CREATE INDEX idxgroups ON hosts USING GIN (groups jsonb_ops);")
    op.drop_index("idxaccount", table_name="hosts")


def downgrade():
    op.drop_index("idxdisplay_name", table_name="hosts")
    op.drop_index("idxsystem_profile_facts", table_name="hosts")
    op.drop_index("idxgroups", table_name="hosts")
    op.create_index("idxaccount", "hosts", ["account"], unique=False)
