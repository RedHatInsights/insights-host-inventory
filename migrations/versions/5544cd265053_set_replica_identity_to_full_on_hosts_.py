"""Set REPLICA_IDENTITY to FULL on hosts table

Revision ID: 5544cd265053
Revises: f48f739902ed
Create Date: 2020-03-02 09:21:32.938401

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "5544cd265053"
down_revision = "f48f739902ed"
branch_labels = None
depends_on = None


# Can be verified by:
#
#   SELECT "relreplident" FROM "pg_class" WHERE "oid" = 'hosts'::regclass;
#
# 'd' means DEFAULT, 'f' means FULL.


def upgrade():
    op.execute('ALTER TABLE "hosts" REPLICA IDENTITY FULL')


def downgrade():
    op.execute('ALTER TABLE "hosts" REPLICA IDENTITY DEFAULT')
