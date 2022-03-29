"""Add org_id column and index

Revision ID: 268debe6db17
Revises: 3d06b0a8828f
Create Date: 2022-03-28 13:46:34.982026

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '268debe6db17'
down_revision = '3d06b0a8828f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("org_id", sa.String(length=255), nullable=True))
    op.create_index("idxorgid", "hosts", ["org_id"])


def downgrade():
    op.drop_index("idxorgid", table_name="hosts")
    op.drop_column("hosts", "org_id")
