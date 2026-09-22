"""Add severity fields (moderate_cves, low_cves) to hosts_app_data_vulnerability

Revision ID: 77837836a5b3
Revises: 4e2e1fe2f34d
Create Date: 2026-09-18 11:11:56.615803

"""

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "77837836a5b3"
down_revision = "4e2e1fe2f34d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hosts_app_data_vulnerability", schema=INVENTORY_SCHEMA) as batch_op:
        batch_op.add_column(sa.Column("moderate_cves", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("low_cves", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("hosts_app_data_vulnerability", schema=INVENTORY_SCHEMA) as batch_op:
        batch_op.drop_column("moderate_cves")
        batch_op.drop_column("low_cves")
