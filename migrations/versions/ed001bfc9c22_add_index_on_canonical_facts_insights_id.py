"""empty message

Revision ID: ed001bfc9c22
Revises: 328011606777
Create Date: 2019-04-09 16:06:14.667298

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed001bfc9c22'
down_revision = '328011606777'
branch_labels = None
depends_on = None

table_name = "hosts"
index_name = "idx_cf_insights_id"


def upgrade():
    op.create_index(index_name,
                    table_name,
                    [sa.text(("""(canonical_facts ->> 'insights_id')"""))],
                    )
                    #postgresql_using='gin')


def downgrade():
    op.drop_index(index_name, table_name)
