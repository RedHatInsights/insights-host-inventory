"""fix groups ungrouped column default

Revision ID: 84ef628a2a99
Revises: f94ada908824
Create Date: 2025-04-17 13:20:24.685754

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "84ef628a2a99"
down_revision = "f94ada908824"
branch_labels = None
depends_on = None


def upgrade():
    # Update existing NULL values to False
    op.execute("UPDATE hbi.groups SET ungrouped = FALSE WHERE ungrouped IS NULL")

    # Alter column to set default and make non-nullable
    op.alter_column(
        table_name="groups",
        column_name="ungrouped",
        schema="hbi",
        existing_type=sa.Boolean,
        nullable=False,
        server_default=sa.text("FALSE"),
    )


def downgrade():
    op.alter_column(
        table_name="groups",
        column_name="ungrouped",
        schema="hbi",
        existing_type=sa.Boolean,
        nullable=True,
        server_default=None,
    )
