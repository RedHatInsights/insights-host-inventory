"""Add per_reporter_staleness column

Revision ID: 3d06b0a8828f
Revises: 33e0aca8516f
Create Date: 2021-02-16 13:53:55.919448

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3d06b0a8828f"
down_revision = "33e0aca8516f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hosts",
        sa.Column(
            "per_reporter_staleness",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            default=dict,
            server_default="{}",
        ),
    )


def downgrade():
    op.drop_column("hosts", "per_reporter_staleness")
