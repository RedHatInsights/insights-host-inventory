"""Remove unused indexes

Revision ID: 90879eb18c66
Revises: 091e613af3d9
Create Date: 2024-05-01 11:18:49.909380

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "90879eb18c66"
down_revision = "091e613af3d9"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "hosts_subscription_manager_id_index", table_name="hosts", postgresql_concurrently=True, if_exists=True
        )
        op.drop_index("idx_reporter", table_name="hosts", postgresql_concurrently=True, if_exists=True)
        op.drop_index("idxdisplay_name", table_name="hosts", postgresql_concurrently=True, if_exists=True)
        op.drop_index("idxsap_sids", table_name="hosts", postgresql_concurrently=True, if_exists=True)


def downgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "hosts_subscription_manager_id_index",
            "hosts",
            [sa.text("(canonical_facts ->> 'subscription_manager_id')")],
        )
        op.create_index("idx_reporter", "hosts", ["reporter"])
        op.create_index(
            "idxdisplay_name",
            "hosts",
            ["display_name"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "idxsap_sids",
            "hosts",
            [sa.text("(system_profile_facts->'sap_sids') jsonb_path_ops")],
            postgresql_using="gin",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
