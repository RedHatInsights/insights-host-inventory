"""create hbi schema and move tables

Revision ID: 1e276ea9970d
Revises: dbbecd6bf7d1
Create Date: 2024-10-18 14:59:16.167777

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1e276ea9970d"
down_revision = "dbbecd6bf7d1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS hbi")
    op.execute("ALTER TABLE IF EXISTS public.assignment_rules SET SCHEMA hbi")
    op.execute("ALTER TABLE IF EXISTS public.groups SET SCHEMA hbi")
    op.execute("ALTER TABLE IF EXISTS public.hosts SET SCHEMA hbi")
    op.execute("ALTER TABLE IF EXISTS public.hosts_groups SET SCHEMA hbi")
    op.execute("ALTER TABLE IF EXISTS public.staleness SET SCHEMA hbi")


def downgrade():
    op.execute("ALTER TABLE IF EXISTS hbi.assignment_rules SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS hbi.groups SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS hbi.hosts SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS hbi.hosts_groups SET SCHEMA public")
    op.execute("ALTER TABLE IF EXISTS hbi.staleness SET SCHEMA public")
    op.execute("DROP SCHEMA IF EXISTS hbi")
