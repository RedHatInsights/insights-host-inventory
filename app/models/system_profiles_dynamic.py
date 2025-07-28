import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostDynamicSystemProfile(db.Model):
    """
    SQLAlchemy ORM class for the 'system_profiles_dynamic' table.

    This table stores frequently updated system profile fields to optimize write performance.
    """

    __tablename__ = "system_profiles_dynamic"
    __table_args__ = (
        sa.PrimaryKeyConstraint("org_id", "host_id"),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"], ["hbi.hosts.org_id", "hbi.hosts.id"], name="fk_system_profiles_dynamic_hosts"
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(self, org_id, host_id, **kwargs):
        if not org_id or not host_id:
            raise ValueError("org_id and host_id are required")

        self.org_id = org_id
        self.host_id = host_id

        super().__init__(**kwargs)

    org_id = sa.Column(sa.String(36), primary_key=True)
    host_id = sa.Column(postgresql.UUID(as_uuid=True), primary_key=True)
    captured_date = sa.Column(sa.DateTime(timezone=True), nullable=True)
    running_processes = sa.Column(postgresql.ARRAY(sa.String), nullable=True)
    last_boot_time = sa.Column(sa.DateTime(timezone=True), nullable=True)
    installed_packages = sa.Column(postgresql.ARRAY(sa.String), nullable=True)
    network_interfaces = sa.Column(postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    installed_products = sa.Column(postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    cpu_flags = sa.Column(postgresql.ARRAY(sa.String), nullable=True)
    insights_egg_version = sa.Column(sa.String(50), nullable=True)
    kernel_modules = sa.Column(postgresql.ARRAY(sa.String), nullable=True)
    system_memory_bytes = sa.Column(sa.BigInteger, nullable=True)
    systemd = sa.Column(postgresql.JSONB(astext_type=sa.Text()), nullable=True)
