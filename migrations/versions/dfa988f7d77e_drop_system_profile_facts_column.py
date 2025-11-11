"""Drop system_profile_facts column from hosts table

Revision ID: dfa988f7d77e
Revises: 014a85b6e197
Create Date: 2025-11-11 12:25:17.124935

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "dfa988f7d77e"
down_revision = "014a85b6e197"
branch_labels = None
depends_on = None


def upgrade():
    # Drop the system_profile_facts column from hosts table
    # Note: PostgreSQL automatically drops dependent indexes:
    # - idx_hosts_ansible
    # - idx_hosts_bootc_status
    # - idx_hosts_host_type
    # - idx_hosts_host_type_modified_on_org_id
    # - idx_hosts_mssql
    # - idx_hosts_operating_system_multi
    # - idx_hosts_sap_system
    # - idx_hosts_system_profiles_workloads_gin
    op.drop_column("hosts", "system_profile_facts", schema="hbi")


def downgrade():
    # Restore the system_profile_facts column to hosts table
    op.add_column(
        "hosts",
        sa.Column("system_profile_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="hbi",
    )
