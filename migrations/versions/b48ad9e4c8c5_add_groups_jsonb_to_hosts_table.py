"""Add groups JSONB to hosts table

Revision ID: b48ad9e4c8c5
Revises: 0f2fb89499ce
Create Date: 2023-04-06 09:42:51.222003

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b48ad9e4c8c5"
down_revision = "0f2fb89499ce"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column("hosts", "groups")
