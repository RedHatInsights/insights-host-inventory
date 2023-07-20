"""Make group_id unique in assignment_rules table

Revision ID: 9934227de1bb
Revises: 1689cda89252
Create Date: 2023-07-13 15:44:31.118406

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "9934227de1bb"
down_revision = "1689cda89252"
branch_labels = None
depends_on = None


def upgrade():
    # For now, group_id column is unique in assignment_rules table
    op.create_unique_constraint(
        constraint_name="assignment_rules_unique_group_id", table_name="assignment_rules", columns=["group_id"]
    )


def downgrade():
    op.drop_constraint("assignment_rules_unique_group_id", "assignment_rules")
