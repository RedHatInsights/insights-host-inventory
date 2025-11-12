from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostAppDataAdvisor(db.Model):
    __tablename__ = "hosts_app_data_advisor"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_advisor_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    recommendations = db.Column(db.Integer, nullable=True)
    incidents = db.Column(db.Integer, nullable=True)


class HostAppDataVulnerability(db.Model):
    __tablename__ = "hosts_app_data_vulnerability"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_vulnerability_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    total_cves = db.Column(db.Integer, nullable=True)
    critical_cves = db.Column(db.Integer, nullable=True)
    high_severity_cves = db.Column(db.Integer, nullable=True)
    cves_with_security_rules = db.Column(db.Integer, nullable=True)
    cves_with_known_exploits = db.Column(db.Integer, nullable=True)


class HostAppDataPatch(db.Model):
    __tablename__ = "hosts_app_data_patch"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_patch_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    installable_advisories = db.Column(db.Integer, nullable=True)
    template = db.Column(db.String(255), nullable=True)
    rhsm_locked_version = db.Column(db.String(50), nullable=True)


class HostAppDataRemediations(db.Model):
    __tablename__ = "hosts_app_data_remediations"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_remediations_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    remediations_plans = db.Column(db.Integer, nullable=True)


class HostAppDataCompliance(db.Model):
    __tablename__ = "hosts_app_data_compliance"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_compliance_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    policies = db.Column(db.Integer, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataMalware(db.Model):
    __tablename__ = "hosts_app_data_malware"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_malware_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    last_status = db.Column(db.String(50), nullable=True)
    last_matches = db.Column(db.Integer, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataImageBuilder(db.Model):
    __tablename__ = "hosts_app_data_image_builder"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_hosts_app_data_image_builder_hosts",
            ondelete="CASCADE",
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)
    image_name = db.Column(db.String(255), nullable=True)
    image_status = db.Column(db.String(50), nullable=True)
