"""alter org_id and account

Revision ID: 69c96c8b47e0
Revises: 268debe6db17
Create Date: 2022-07-05 13:23:52.361283

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "69c96c8b47e0"
down_revision = "268debe6db17"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("hosts", "account", nullable=True)
    op.alter_column("hosts", "org_id", nullable=False)


def downgrade():
    op.alter_column("hosts", "account", nullable=False)
    op.alter_column("hosts", "org_id", nullable=True)
