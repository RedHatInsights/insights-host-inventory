"""alter_stale_timestamp_and_reporter_to_not_null

Revision ID: f48f739902ed
Revises: ff39a83abac3
Create Date: 2020-02-20 15:37:06.363012

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f48f739902ed"
down_revision = "ff39a83abac3"
branch_labels = None
depends_on = None


COLUMNS = ("stale_timestamp", "reporter")


def upgrade():
    for column in COLUMNS:
        op.alter_column("hosts", column, nullable=False)


def downgrade():
    for column in COLUMNS:
        op.alter_column("hosts", column, nullable=True)
