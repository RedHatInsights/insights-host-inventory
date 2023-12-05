"""Rename staleness attribute

Revision ID: 22367a1b23e9
Revises: cc3494db47ea
Create Date: 2023-12-05 10:29:10.185627

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "22367a1b23e9"
down_revision = "cc3494db47ea"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("staleness", "conventional_staleness_delta", new_column_name="conventional_time_to_stale")
    op.alter_column(
        "staleness", "conventional_stale_warning_delta", new_column_name="conventional_time_to_stale_warning"
    )
    op.alter_column("staleness", "conventional_culling_delta", new_column_name="conventional_time_to_delete")
    op.alter_column("staleness", "immutable_staleness_delta", new_column_name="immutable_time_to_stale")
    op.alter_column("staleness", "immutable_stale_warning_delta", new_column_name="immutable_time_to_stale_warning")
    op.alter_column("staleness", "immutable_culling_delta", new_column_name="immutable_time_to_delete")


def downgrade():
    op.alter_column("staleness", "conventional_time_to_stale", new_column_name="conventional_staleness_delta")
    op.alter_column(
        "staleness", "conventional_time_to_stale_warning", new_column_name="conventional_stale_warning_delta"
    )
    op.alter_column("staleness", "conventional_time_to_delete", new_column_name="conventional_culling_delta")
    op.alter_column("staleness", "immutable_time_to_stale", new_column_name="immutable_staleness_delta")
    op.alter_column("staleness", "immutable_time_to_stale_warning", new_column_name="immutable_stale_warning_delta")
    op.alter_column("staleness", "immutable_time_to_delete", new_column_name="immutable_culling_delta")
