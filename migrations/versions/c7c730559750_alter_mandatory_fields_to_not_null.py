"""alter_mandatory_fields_to_not_null

Revision ID: c7c730559750
Revises: 33e0aca8516f
Create Date: 2020-03-26 10:59:21.151172

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "c7c730559750"
down_revision = "33e0aca8516f"
branch_labels = None
depends_on = None

COLUMNS = ("created_on", "modified_on", "account", "canonical_facts")


def upgrade():
    for column in COLUMNS:
        op.alter_column("hosts", column, nullable=False)


def downgrade():
    for column in COLUMNS:
        op.alter_column("hosts", column, nullable=True)
