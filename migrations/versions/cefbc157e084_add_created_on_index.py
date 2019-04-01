"""empty message

Revision ID: cefbc157e084
Revises: 2d1cdfe3208d
Create Date: 2019-04-01 16:25:05.494229

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cefbc157e084'
down_revision = '2d1cdfe3208d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("hosts_created_on", "hosts", ("created_on",))


def downgrade():
    op.drop_index("hosts_created_on")
