"""remove unique group name restriction

Revision ID: 5a430523e918
Revises: 61c1b152246a
Create Date: 2025-07-28 11:00:41.678048

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "5a430523e918"
down_revision = "61c1b152246a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_groups_org_id_name_ignorecase",
        "groups",
        [text("lower(name)"), "org_id"],
        if_not_exists=True,
        unique=False,
        schema="hbi",
        postgresql_concurrently=False,
    )
    op.drop_index(
        "idx_groups_org_id_name_nocase",
        table_name="groups",
        if_exists=True,
        schema="hbi",
        postgresql_concurrently=False,
    )


def downgrade():
    op.drop_index(
        "idx_groups_org_id_name_ignorecase",
        "groups",
        if_exists=True,
        schema="hbi",
        postgresql_concurrently=False,
    )
    op.create_index(
        "idx_groups_org_id_name_nocase",
        "groups",
        [text("lower(name)"), "org_id"],
        if_not_exists=True,
        unique=True,
        schema="hbi",
        postgresql_concurrently=False,
    )
