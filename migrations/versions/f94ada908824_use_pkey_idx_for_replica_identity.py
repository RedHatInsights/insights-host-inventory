"""Use pkey for replica identity.

Revision ID: f94ada908824
Revises: 837d2ee7bbd8
Create Date: 2025-03-27 09:30:38.364871

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f94ada908824"
down_revision = "837d2ee7bbd8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY USING INDEX hosts_pkey")


def downgrade():
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY FULL")
