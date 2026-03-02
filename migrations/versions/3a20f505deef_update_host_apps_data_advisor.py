"""Add severity fields (critical, important, moderate, low) to hosts_app_data_advisor

Revision ID: 3a20f505deef
Revises: eff8fe46beae
Create Date: 2026-01-29 14:42:52.024765

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "3a20f505deef"
down_revision = "eff8fe46beae"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hosts_app_data_advisor", schema=INVENTORY_SCHEMA) as batch_op:
        batch_op.add_column(sa.Column("critical", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("important", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("moderate", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("low", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("hosts_app_data_advisor", schema=INVENTORY_SCHEMA) as batch_op:
        batch_op.drop_column("critical")
        batch_op.drop_column("important")
        batch_op.drop_column("moderate")
        batch_op.drop_column("low")
