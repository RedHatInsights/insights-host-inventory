"""Add openshift_cluster_id to hosts table

Revision ID: 619de6666f1b
Revises: 014a85b6e197
Create Date: 2025-11-07 10:27:02.164791

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "619de6666f1b"
down_revision = "014a85b6e197"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("openshift_cluster_id", sa.UUID(as_uuid=True), nullable=True), schema="hbi")


def downgrade():
    op.drop_column("hosts", "openshift_cluster_id", schema="hbi")
