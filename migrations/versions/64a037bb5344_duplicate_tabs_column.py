"""Duplicate tabs column

Revision ID: 64a037bb5344
Revises: 286343296975
Create Date: 2025-02-12 21:19:02.465943

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "64a037bb5344"
down_revision = "286343296975"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("tags_alt", postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "tags_alt", schema="hbi")
