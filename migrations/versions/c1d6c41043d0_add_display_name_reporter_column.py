"""Add display_name_reporter column

Revision ID: c1d6c41043d0
Revises: 0e3773b74542
Create Date: 2025-08-27 11:15:25.799091

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d6c41043d0"
down_revision = "0e3773b74542"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("display_name_reporter", sa.String(length=255), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "display_name_reporter", schema="hbi")
