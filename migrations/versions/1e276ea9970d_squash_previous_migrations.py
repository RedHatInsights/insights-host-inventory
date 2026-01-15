"""Squash previous migrations

Revision ID: 1e276ea9970d
Revises:
Create Date: 2024-11-26 11:20:10.948151

"""

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "1e276ea9970d"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Get the path to the schema file relative to this migration script
    migration_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_file_path = os.path.join(migration_dir, "hbi_schema_2024-12-03.sql")

    with open(schema_file_path) as f:
        # Don't execute the last item, as it's just an empty comment
        # (i.e. "PostgreSQL database dump complete")
        for stmt in f.read().split(";\n")[:-1]:
            if not stmt or stmt.startswith("--"):
                continue
            op.execute(stmt)

    op.execute("COMMIT")


def downgrade():
    pass
