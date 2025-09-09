"""Add CASCADE to system profiles foreign keys

Revision ID: 0e3773b74542
Revises: 38324a692109
Create Date: 2025-08-07 15:32:40.665781

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0e3773b74542"
down_revision = "38324a692109"
branch_labels = None
depends_on = None


def upgrade():
    """
    Adds ondelete='CASCADE' to the foreign keys that reference the hosts table
    from the system_profiles_static and system_profiles_dynamic tables.

    This ensures that when a host is deleted, the associated system profile
    records are automatically deleted as well.
    """

    # For partitioned tables in PostgreSQL, we need to drop and recreate
    # the foreign key constraints to modify them

    # Drop existing foreign keys
    op.drop_constraint("fk_system_profiles_static_hosts", "system_profiles_static", schema="hbi")
    op.drop_constraint("fk_system_profiles_dynamic_hosts", "system_profiles_dynamic", schema="hbi")

    # Recreate foreign keys with CASCADE
    op.create_foreign_key(
        "fk_system_profiles_static_hosts",
        "system_profiles_static",
        "hosts",
        ["org_id", "host_id"],
        ["org_id", "id"],
        source_schema="hbi",
        referent_schema="hbi",
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_system_profiles_dynamic_hosts",
        "system_profiles_dynamic",
        "hosts",
        ["org_id", "host_id"],
        ["org_id", "id"],
        source_schema="hbi",
        referent_schema="hbi",
        ondelete="CASCADE",
    )


def downgrade():
    """
    We don't need to do anything here because we're not changing the foreign keys.
    """
