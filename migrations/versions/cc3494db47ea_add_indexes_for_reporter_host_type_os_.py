"""Add indexes for reporter, host_type, OS name

Revision ID: cc3494db47ea
Revises: f8c3af70df12
Create Date: 2023-11-08 09:38:18.821767

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "cc3494db47ea"
down_revision = "f8c3af70df12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_reporter", "hosts", ["reporter"])
    op.create_index("idx_host_type", "hosts", [sa.text("(system_profile_facts ->> 'host_type')")])


def downgrade():
    op.drop_index("idx_host_type", table_name="hosts")
    op.drop_index("idx_reporter", table_name="hosts")
