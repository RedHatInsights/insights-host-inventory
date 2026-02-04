from __future__ import annotations

import inspect as python_inspect
from functools import cache

from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.types import DateTime

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostAppDataMixin:
    """Base mixin for host application data models.

    Subclasses should define:
        __app_name__: str - The application name used in API responses (e.g., "advisor")

    DateTime fields are automatically converted to ISO format strings during serialization.
    """

    # Required: subclasses must define this
    __app_name__: str = ""

    # Fields from the mixin that should never be serialized
    _MIXIN_FIELDS = frozenset({"org_id", "host_id", "last_updated"})

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

    @classmethod
    @cache
    def _get_serializable_fields(cls) -> tuple[str, ...]:
        """Return tuple of field names that should be serialized in API responses."""
        mapper = inspect(cls)
        all_columns = {col.name for col in mapper.columns}
        fields = all_columns - cls._MIXIN_FIELDS
        return tuple(sorted(fields))

    @classmethod
    @cache
    def _get_datetime_fields(cls) -> frozenset[str]:
        """Return set of field names that are DateTime columns."""
        mapper = inspect(cls)
        return frozenset(col.name for col in mapper.columns if isinstance(col.type, DateTime))

    @classmethod
    @cache
    def _get_uuid_fields(cls) -> frozenset[str]:
        """Return set of field names that are UUID columns."""
        mapper = inspect(cls)
        return frozenset(col.name for col in mapper.columns if isinstance(col.type, UUID))

    def serialize(self) -> dict:
        """Serialize this instance to a dictionary for API responses."""
        datetime_fields = self._get_datetime_fields()
        uuid_fields = self._get_uuid_fields()
        result = {}

        for field in self._get_serializable_fields():
            value = getattr(self, field)

            # Convert datetime to ISO format string
            if field in datetime_fields and value is not None:
                value = value.isoformat()
            # Convert UUID to string (skip if null - OpenAPI format:uuid validation issue)
            elif field in uuid_fields:
                if value is not None:
                    result[field] = str(value)
                continue

            result[field] = value

        return result


class HostAppDataAdvisor(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_advisor"
    __app_name__ = "advisor"

    recommendations = db.Column(db.Integer, nullable=True)
    incidents = db.Column(db.Integer, nullable=True)


class HostAppDataVulnerability(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_vulnerability"
    __app_name__ = "vulnerability"

    total_cves = db.Column(db.Integer, nullable=True)
    critical_cves = db.Column(db.Integer, nullable=True)
    high_severity_cves = db.Column(db.Integer, nullable=True)
    cves_with_security_rules = db.Column(db.Integer, nullable=True)
    cves_with_known_exploits = db.Column(db.Integer, nullable=True)


class HostAppDataPatch(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_patch"
    __app_name__ = "patch"

    # Advisory counts by type (applicable)
    advisories_rhsa_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhba_applicable = db.Column(db.Integer, nullable=True)
    advisories_rhea_applicable = db.Column(db.Integer, nullable=True)
    advisories_other_applicable = db.Column(db.Integer, nullable=True)

    # Advisory counts by type (installable)
    advisories_rhsa_installable = db.Column(db.Integer, nullable=True)
    advisories_rhba_installable = db.Column(db.Integer, nullable=True)
    advisories_rhea_installable = db.Column(db.Integer, nullable=True)
    advisories_other_installable = db.Column(db.Integer, nullable=True)

    # Package counts
    packages_applicable = db.Column(db.Integer, nullable=True)
    packages_installable = db.Column(db.Integer, nullable=True)
    packages_installed = db.Column(db.Integer, nullable=True)

    # Template info
    template_name = db.Column(db.String(255), nullable=True)
    template_uuid = db.Column(UUID(as_uuid=True), nullable=True)


class HostAppDataRemediations(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_remediations"
    __app_name__ = "remediations"

    remediations_plans = db.Column(db.Integer, nullable=True)


class HostAppDataCompliance(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_compliance"
    __app_name__ = "compliance"

    policies = db.Column(JSONB, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataMalware(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_malware"
    __app_name__ = "malware"

    last_status = db.Column(db.String(50), nullable=True)
    last_matches = db.Column(db.Integer, nullable=True)
    total_matches = db.Column(db.Integer, nullable=True)
    last_scan = db.Column(db.DateTime(timezone=True), nullable=True)


class HostAppDataImageBuilder(HostAppDataMixin, db.Model):
    __tablename__ = "hosts_app_data_image_builder"
    __app_name__ = "image_builder"

    image_name = db.Column(db.String(255), nullable=True)
    image_status = db.Column(db.String(50), nullable=True)


@cache
def get_app_data_models() -> dict[str, type[HostAppDataMixin]]:
    """Return a mapping of app_name -> model class for all registered app data models."""
    from app.models import host_app_data

    models = {}
    for _name, cls in python_inspect.getmembers(host_app_data, python_inspect.isclass):
        if (
            issubclass(cls, HostAppDataMixin)
            and cls is not HostAppDataMixin
            and hasattr(cls, "__app_name__")
            and cls.__app_name__
        ):
            models[cls.__app_name__] = cls
    return models
