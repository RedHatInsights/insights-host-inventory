"""add_host_subscription_manager_id_index

Revision ID: 76b7bc1d1d12
Revises: 5dbbd56ce006
Create Date: 2019-06-24 16:41:54.754856

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "76b7bc1d1d12"
down_revision = "5dbbd56ce006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "hosts_subscription_manager_id_index", "hosts", [sa.text("(canonical_facts ->> 'subscription_manager_id')")]
    )


def downgrade():
    op.drop_index("hosts_subscription_manager_id_index", table_name="hosts")
