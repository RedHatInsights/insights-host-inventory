"""Add GIN for operating_system name

Revision ID: bb9701f29a05
Revises: cc3494db47ea
Create Date: 2023-11-10 16:53:02.882106

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "bb9701f29a05"
down_revision = "cc3494db47ea"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "idx_operating_system",
        "hosts",
        [sa.text("(system_profile_facts -> 'operating_system' ->> 'name') gin_trgm_ops")],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("idx_operating_system", table_name="hosts")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
