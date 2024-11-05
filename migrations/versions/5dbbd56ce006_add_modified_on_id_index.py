"""add_modified_on_id_index

Revision ID: 5dbbd56ce006
Revises: a9f0e674cf52
Create Date: 2019-05-24 20:53:01.426278

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5dbbd56ce006"
down_revision = "a9f0e674cf52"
branch_labels = None
depends_on = None


def upgrade():
    columns = (sa.desc("modified_on"), sa.desc("id"))
    expressions = [sa.text(str(column)) for column in columns]
    op.create_index("hosts_modified_on_id", "hosts", expressions)


def downgrade():
    op.drop_index("hosts_modified_on_id")
