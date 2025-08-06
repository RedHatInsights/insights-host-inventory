"""add outbox table

Revision ID: b4b598dd1fb8
Revises: 3b60b7daf0f2
Create Date: 2025-08-06 08:33:36.026872

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b4b598dd1fb8'
down_revision = '3b60b7daf0f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('outbox',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('aggregate_type', sa.String(length=255), nullable=False),
    sa.Column('aggregate_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=255), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='hbi'
    )


def downgrade():
    op.drop_table('outbox', schema='hbi')
