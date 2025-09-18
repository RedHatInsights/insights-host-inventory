"""signal_table_columns_update

Revision ID: 94a16dd3106c
Revises: 0d4ee3bf6b94
Create Date: 2025-09-18 15:16:34.854784

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '94a16dd3106c'
down_revision = '0d4ee3bf6b94'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "debezium_signal", "id",
        existing_type=sa.String(36),
        type_=sa.String(50),
        existing_nullable=False, # Adjust based on your column's nullability
        primary_key=True,
        schema="hbi",
    )

    op.alter_column(
        "debezium_signal", "type",
        existing_type=sa.String(50),
        type_=sa.String(32),
        existing_nullable=False, # Adjust based on your column's nullability
        schema="hbi",
    )

    op.alter_column(
        "debezium_signal", "data",
        existing_type=sa.String(),
        type_=sa.String(2048),
        existing_nullable=True, # Adjust based on your column's nullability
        schema="hbi",
    )


def downgrade():
    op.alter_column(
        "debezium_signal", "id",
        existing_type=sa.String(50),
        type_=sa.String(36),
        existing_nullable=False, # Adjust based on your column's nullability
        primary_key=True,
        schema="hbi",
    )

    op.alter_column(
        "debezium_signal", "type",
        existing_type=sa.String(32),
        type_=sa.String(50),
        existing_nullable=False, # Adjust based on your column's nullability
        schema="hbi",
    )

    op.alter_column(
        "debezium_signal", "data",
        existing_type=sa.String(2048),
        type_=sa.String(),
        existing_nullable=True, # Adjust based on your column's nullability
        schema="hbi",
    )
