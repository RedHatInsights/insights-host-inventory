from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostAppDataMixin:
    """Base mixin for host application data models."""

    @declared_attr
    def __table_args__(cls):
        """Generate table args with PK, FK, and schema configuration."""
        table_name = cls.__tablename__
        fk_name = f"fk_{table_name}_hosts"

        return (
            PrimaryKeyConstraint("org_id", "host_id"),
            ForeignKeyConstraint(
                ["org_id", "host_id"],
                [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
                name=fk_name,
                ondelete="CASCADE",
            ),
            {"schema": INVENTORY_SCHEMA},
        )

    org_id = db.Column(db.String(36), primary_key=True, nullable=False)
    host_id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), nullable=False)


class HostAppDataAdvisor(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_advisor"

    recommendations = db.Column(db.Integer, nullable=True)
    incidents = db.Column(db.Integer, nullable=True)


class HostAppDataVulnerability(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_vulnerability"

    total_cves = db.Column(db.Integer, nullable=True)
    critical_cves = db.Column(db.Integer, nullable=True)
    high_severity_cves = db.Column(db.Integer, nullable=True)
    cves_with_security_rules = db.Column(db.Integer, nullable=True)
    cves_with_known_exploits = db.Column(db.Integer, nullable=True)


class HostAppDataPatch(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_patch"

    advisories_rhsa_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhba_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhea_applicable = db.Column(db.Integer, nullable=True)
    advisories_other_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhsa_installable = db.Column(db.Integer, nullable=True)
    advisories_rhba_installable = db.Column(db.Integer, nullable=True)
    advisories_rhea_installable = db.Column(db.Integer, nullable=True)
    advisories_other_installable = db.Column(db.Integer, nullable=True)
    packages_applicable = db.Column(db.Integer, nullable=True)
    packages_installable = db.Column(db.Integer, nullable=True)
    packages_installed = db.Column(db.Integer, nullable=True)
    template_name = db.Column(db.String(255), nullable=True)
    template_uuid = db.Column(UUID(as_uuid=True), nullable=True)


class HostAppDataRemediations(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_remediations"

    remediations_plans = db.Column(db.Integer, nullable=True)


class HostAppDataCompliance(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_compliance"

    policies = db.Column(db.Integer, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataMalware(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_malware"

    last_status = db.Column(db.String(50), nullable=True)
    last_matches = db.Column(db.Integer, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataImageBuilder(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_image_builder"

    image_name = db.Column(db.String(255), nullable=True)
    image_status = db.Column(db.String(50), nullable=True)
