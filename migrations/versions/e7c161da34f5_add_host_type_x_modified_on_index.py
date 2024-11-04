"""Add host_type x modified_on index

Revision ID: e7c161da34f5
Revises: 911b5b30db35
Create Date: 2024-04-18 14:05:42.492686

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e7c161da34f5"
down_revision = "911b5b30db35"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_host_type_modified_on_org_id",
            "hosts",
            ["org_id", "modified_on", sa.text("(system_profile_facts ->> 'host_type')")],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_host_type_modified_on_org_id", table_name="hosts", postgresql_concurrently=True, if_exists=True
        )
