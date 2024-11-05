"""Add indext to support workload query

Revision ID: 988065a6da42
Revises: e7c161da34f5
Create Date: 2024-04-23 16:02:07.394674

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "988065a6da42"
down_revision = "e7c161da34f5"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idxsap_system",
            "hosts",
            [sa.text("((system_profile_facts->>'sap_system')::BOOLEAN)")],
            postgresql_using="btree",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "idxansible",
            "hosts",
            [sa.text("(system_profile_facts->>'ansible')")],
            postgresql_using="btree",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "idxmssql",
            "hosts",
            [sa.text("(system_profile_facts->>'mssql')")],
            postgresql_using="btree",
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("idxsap_system", table_name="hosts", postgresql_concurrently=True, if_exists=True)
        op.drop_index("idxansible", table_name="hosts", postgresql_concurrently=True, if_exists=True)
        op.drop_index("idxmssql", table_name="hosts", postgresql_concurrently=True, if_exists=True)
