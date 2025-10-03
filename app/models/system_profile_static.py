from sqlalchemy import CheckConstraint
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db

logger = get_logger(__name__)


class HostStaticSystemProfile(db.Model):
    __tablename__ = "system_profiles_static"
    __table_args__ = (
        Index("idx_system_profiles_static_org_id", "org_id"),
        Index("idx_system_profiles_static_host_id", "host_id"),
        CheckConstraint(
            "cores_per_socket >= 0 AND cores_per_socket <= 2147483647", name="cores_per_socket_range_check"
        ),
        CheckConstraint("number_of_cpus >= 0 AND number_of_cpus <= 2147483647", name="number_of_cpus_range_check"),
        CheckConstraint(
            "number_of_sockets >= 0 AND number_of_sockets <= 2147483647", name="number_of_sockets_range_check"
        ),
        CheckConstraint(
            "threads_per_core >= 0 AND threads_per_core <= 2147483647", name="threads_per_core_range_check"
        ),
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_system_profiles_static_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), nullable=False, primary_key=True)
    host_id = db.Column(db.UUID(as_uuid=True), nullable=False, primary_key=True)
    arch = db.Column(db.String(50), nullable=True)
    basearch = db.Column(db.String(50), nullable=True)
    bios_release_date = db.Column(db.String(50), nullable=True)
    bios_vendor = db.Column(db.String(100), nullable=True)
    bios_version = db.Column(db.String(100), nullable=True)
    bootc_status = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    cloud_provider = db.Column(db.String(100), nullable=True)
    conversions = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    cores_per_socket = db.Column(db.Integer, nullable=True)
    cpu_model = db.Column(db.String(100), nullable=True)
    disk_devices = db.Column(ARRAY(JSONB(astext_type=db.Text())), nullable=True)
    dnf_modules = db.Column(ARRAY(JSONB(astext_type=db.Text())), nullable=True)
    enabled_services = db.Column(ARRAY(String(512)), nullable=True)
    gpg_pubkeys = db.Column(ARRAY(String(512)), nullable=True)
    greenboot_fallback_detected = db.Column(db.Boolean, default=False, nullable=True)
    greenboot_status = db.Column(db.String(5), nullable=True)
    host_type = db.Column(db.String(12), nullable=True)
    image_builder = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    infrastructure_type = db.Column(db.String(100), nullable=True)
    infrastructure_vendor = db.Column(db.String(100), nullable=True)
    insights_client_version = db.Column(db.String(50), nullable=True)
    installed_packages_delta = db.Column(ARRAY(String(512)), nullable=True)
    installed_services = db.Column(ARRAY(String(512)), nullable=True)
    is_marketplace = db.Column(db.Boolean, default=False, nullable=True)
    katello_agent_running = db.Column(db.Boolean, default=False, nullable=True)
    number_of_cpus = db.Column(db.Integer, nullable=True)
    number_of_sockets = db.Column(db.Integer, nullable=True)
    operating_system = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    os_kernel_version = db.Column(db.String(20), nullable=True)
    os_release = db.Column(db.String(100), nullable=True)
    owner_id = db.Column(UUID(as_uuid=True), nullable=True)
    public_dns = db.Column(ARRAY(String(100)), nullable=True)
    public_ipv4_addresses = db.Column(ARRAY(String(15)), nullable=True)
    releasever = db.Column(db.String(100), nullable=True)
    rhc_client_id = db.Column(UUID(as_uuid=True), nullable=True)
    rhc_config_state = db.Column(UUID(as_uuid=True), nullable=True)
    rhsm = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    rpm_ostree_deployments = db.Column(ARRAY(JSONB(astext_type=db.Text())), nullable=True)
    satellite_managed = db.Column(db.Boolean, default=False, nullable=True)
    selinux_config_file = db.Column(db.String(128), nullable=True)
    selinux_current_mode = db.Column(db.String(10), nullable=True)
    subscription_auto_attach = db.Column(db.String(100), nullable=True)
    subscription_status = db.Column(db.String(100), nullable=True)
    system_purpose = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    system_update_method = db.Column(db.String(10), nullable=True)
    third_party_services = db.Column(JSONB(astext_type=db.Text()), nullable=True)
    threads_per_core = db.Column(db.Integer, nullable=True)
    tuned_profile = db.Column(db.String(256), nullable=True)
    virtual_host_uuid = db.Column(db.UUID(as_uuid=True), nullable=True)
    yum_repos = db.Column(ARRAY(JSONB(astext_type=db.Text())), nullable=True)

    host = relationship("Host", back_populates="static_system_profile")
