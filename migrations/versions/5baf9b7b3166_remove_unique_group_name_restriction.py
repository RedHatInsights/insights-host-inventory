"""remove unique group name restriction

Revision ID: 5baf9b7b3166
Revises: 28280de3f1ce
Create Date: 2025-07-07 17:18:02.286001

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "5baf9b7b3166"
down_revision = "28280de3f1ce"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_groups_org_id_name_ignorecase",
            "groups",
            [text("lower(name)"), "org_id"],
            if_not_exists=True,
            unique=False,
            schema="hbi",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "idx_groups_org_id_name_nocase",
            table_name="groups",
            if_exists=True,
            schema="hbi",
            postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_groups_org_id_name_ignorecase",
            "groups",
            if_exists=True,
            schema="hbi",
            postgresql_concurrently=True,
        )
        op.create_index(
            "idx_groups_org_id_name_nocase",
            "groups",
            [text("lower(name)"), "org_id"],
            if_not_exists=True,
            unique=True,
            schema="hbi",
            postgresql_concurrently=True,
        )
