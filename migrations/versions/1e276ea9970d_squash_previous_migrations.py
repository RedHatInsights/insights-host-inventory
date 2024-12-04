"""Squash previous migrations

Revision ID: 1e276ea9970d
Revises:
Create Date: 2024-11-26 11:20:10.948151

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1e276ea9970d"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with open("app_migrations/hbi_schema_2024-12-03.sql") as f:
        # Don't execute the last item, as it's just an empty comment
        # (i.e. "PostgreSQL database dump complete")
        for stmt in f.read().split(";\n")[:-1]:
            if not stmt or stmt.startswith("--"):
                continue
            op.execute(stmt)

    op.execute("COMMIT")


def downgrade():
    pass
