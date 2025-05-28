"""remove unique group name restriction

Revision ID: a359eca4a491
Revises: 002843d515cb
Create Date: 2025-05-28 16:45:43.718142

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "a359eca4a491"
down_revision = "002843d515cb"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "idx_groups_org_id_name_nocase",
        table_name="groups",
        postgresql_concurrently=True,
        if_exists=True,
        schema="hbi",
    )


def downgrade():
    op.create_index(
        "idx_groups_org_id_name_nocase",
        "groups",
        [text("lower(name)"), "org_id"],
        postgresql_concurrently=True,
        if_not_exists=True,
        schema="hbi",
    )
