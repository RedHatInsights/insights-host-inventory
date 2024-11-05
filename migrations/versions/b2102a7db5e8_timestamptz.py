"""timestamptz

Revision ID: b2102a7db5e8
Revises: 76b7bc1d1d12
Create Date: 2019-10-31 09:45:20.273142

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2102a7db5e8"
down_revision = "76b7bc1d1d12"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "hosts", "created_on", type_=sa.DateTime(timezone=True), postgresql_using="created_on AT TIME ZONE 'UTC'"
    )
    op.alter_column(
        "hosts", "modified_on", type_=sa.DateTime(timezone=True), postgresql_using="modified_on AT TIME ZONE 'UTC'"
    )


def downgrade():
    op.alter_column("hosts", "created_on", type_=sa.DateTime())
    op.alter_column("hosts", "modified_on", type_=sa.DateTime())
