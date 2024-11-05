"""Make hosts.groups non-nullable

Revision ID: 2e3c52165bf0
Revises: 9934227de1bb
Create Date: 2023-07-25 14:30:41.053632

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "2e3c52165bf0"
down_revision = "9934227de1bb"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("hosts", "groups", nullable=False)


def downgrade():
    op.alter_column("hosts", "groups", nullable=True)
