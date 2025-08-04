import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

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
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_system_profiles_dynamic_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = sa.Column(sa.String(36), primary_key=True)
    host_id = sa.Column(UUID(as_uuid=True), primary_key=True)
    captured_date = sa.Column(sa.DateTime(timezone=True), nullable=True)
    running_processes = sa.Column(ARRAY(sa.String), nullable=True)
    last_boot_time = sa.Column(sa.DateTime(timezone=True), nullable=True)
    installed_packages = sa.Column(ARRAY(sa.String), nullable=True)
    network_interfaces = sa.Column(JSONB(astext_type=sa.Text()), nullable=True)
    installed_products = sa.Column(JSONB(astext_type=sa.Text()), nullable=True)
    cpu_flags = sa.Column(ARRAY(sa.String), nullable=True)
    insights_egg_version = sa.Column(sa.String(50), nullable=True)
    kernel_modules = sa.Column(ARRAY(sa.String), nullable=True)
    system_memory_bytes = sa.Column(sa.BigInteger, nullable=True)
    systemd = sa.Column(JSONB(astext_type=sa.Text()), nullable=True)
    workloads = db.Column(JSONB(astext_type=db.Text()), nullable=True)

    host = relationship("Host", back_populates="dynamic_system_profile")
