"""remove group name uniqueness

Revision ID: 91110801bc8e
Revises: c1d6c41043d0
Create Date: 2025-09-02 11:46:53.861264

"""

import os

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "91110801bc8e"
down_revision = "c1d6c41043d0"
branch_labels = None
depends_on = None

MIGRATION_MODE = os.environ.get("MIGRATION_MODE", "automated").lower()


def upgrade():
    if MIGRATION_MODE == "managed":
        with op.get_context().autocommit_block():
            op.execute(
                text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_ignorecase
                ON hbi.groups (lower(name), org_id);
            """)
            )
            op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_nocase;"))

    else:
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
    if MIGRATION_MODE == "managed":
        with op.get_context().autocommit_block():
            op.execute(
                text("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_groups_org_id_name_nocase
                ON hbi.groups (lower(name), org_id);
            """)
            )
            op.execute(text("DROP INDEX CONCURRENTLY IF EXISTS hbi.idx_groups_org_id_name_ignorecase;"))
    else:
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
