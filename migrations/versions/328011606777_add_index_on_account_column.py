"""empty message

Revision ID: 328011606777
Revises: 2d1cdfe3208d
Create Date: 2019-04-09 15:54:19.095222

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '328011606777'
down_revision = '2d1cdfe3208d'
branch_labels = None
depends_on = None

table_name = "hosts"
index_name = "idx_account"


def upgrade():
    op.create_index(index_name, table_name, ["account"])


def downgrade():
    op.drop_index(index_name, table_name)
