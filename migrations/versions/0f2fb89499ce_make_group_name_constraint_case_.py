"""Make Group name constraint case-insensitive

Revision ID: 0f2fb89499ce
Revises: ada40da60e4e
Create Date: 2023-03-21 10:53:36.544420

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0f2fb89499ce"
down_revision = "ada40da60e4e"
branch_labels = None
depends_on = None


def upgrade():
    # Replace the old Unique Constraint with a case-insensitive functional index
    op.drop_constraint("groups_org_id_name_key", "groups")
    op.create_index(
        index_name="idx_groups_org_id_name_nocase",
        table_name="groups",
        columns=["org_id", text("lower(name)")],
        unique=True,
    )

    # For now, each host can only be associated with one group at a time
    op.create_unique_constraint(
        constraint_name="hosts_groups_unique_host_id", table_name="hosts_groups", columns=["host_id"]
    )
    pass


def downgrade():
    op.drop_constraint("hosts_groups_unique_host_id", "hosts_groups")

    op.drop_index("idx_groups_org_id_name_nocase", "groups")
    op.create_unique_constraint(
        constraint_name="groups_org_id_name_key", table_name="groups", columns=["org_id", "name"]
    )
    pass
