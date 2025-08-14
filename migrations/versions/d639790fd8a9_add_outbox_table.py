"""add outbox table

Revision ID: d639790fd8a9
Revises: 6714f3063d90
Create Date: 2025-08-13 18:09:42.252661

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd639790fd8a9'
down_revision = '6714f3063d90'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'outbox',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('aggregatetype', sa.String(length=255), nullable=False),
        sa.Column('aggregateid', sa.UUID(), nullable=False),
        sa.Column('operation', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='hbi'
    )


def downgrade():
    op.drop_table('outbox', schema='hbi')
