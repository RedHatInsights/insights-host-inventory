"""Add operating_system multicolumn index

Revision ID: ea9d9c5cb4e4
Revises: 3d4efbc9da4f
Create Date: 2024-05-21 08:57:57.247696

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ea9d9c5cb4e4"
down_revision = "3d4efbc9da4f"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_operating_system_multi",
            "hosts",
            [
                sa.text("(system_profile_facts -> 'operating_system' ->> 'name')"),
                sa.text("(((system_profile_facts -> 'operating_system' ->> 'major')::int))"),
                sa.text("(((system_profile_facts -> 'operating_system' ->> 'minor')::int))"),
                sa.text("(system_profile_facts ->> 'host_type')"),
                "modified_on",
                "org_id",
            ],
            postgresql_concurrently=True,
            if_not_exists=True,
            postgresql_where=(sa.text("(system_profile_facts -> 'operating_system') IS NOT NULL")),
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("idx_operating_system_multi", table_name="hosts", postgresql_concurrently=True, if_exists=True)
