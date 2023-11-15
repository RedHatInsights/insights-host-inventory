"""Add COALESCE to operating_system GIN

Revision ID: 3ecc428e69cb
Revises: bb9701f29a05
Create Date: 2023-11-15 09:01:49.968782

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "3ecc428e69cb"
down_revision = "bb9701f29a05"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("idx_operating_system", table_name="hosts")
    op.create_index(
        "idx_operating_system",
        "hosts",
        [sa.text("(COALESCE(system_profile_facts -> 'operating_system' ->> 'name')) gin_trgm_ops")],
        postgresql_using="gin",
    )


def downgrade():
    # No point downgrading to an incorrect index.
    # Downgrading one migration further will remove the index as intended.
    pass
