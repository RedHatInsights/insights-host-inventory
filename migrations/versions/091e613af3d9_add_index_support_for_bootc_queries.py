"""Add index support for bootc queries

Revision ID: 091e613af3d9
Revises: 988065a6da42
Create Date: 2024-04-29 08:30:01.883057

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "091e613af3d9"
down_revision = "988065a6da42"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idxbootc_status",
            "hosts",
            ["org_id"],
            postgresql_using="btree",
            postgresql_concurrently=True,
            if_not_exists=True,
            postgresql_where=(
                sa.text("(system_profile_facts->'bootc_status'->'booted'->>'image_digest') IS NOT NULL")
            ),
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("idxbootc_status", table_name="hosts", postgresql_concurrently=True, if_exists=True)
