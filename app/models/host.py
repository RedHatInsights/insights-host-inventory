import uuid
from contextlib import suppress
from datetime import datetime

from dateutil.parser import isoparse
from flask import current_app
from sqlalchemy import String
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import relationship
from sqlalchemy.orm import validates

from app.common import inventory_config
from app.config import CANONICAL_FACTS_FIELDS
from app.config import DEFAULT_INSIGHTS_ID
from app.config import ID_FACTS
from app.culling import Timestamps
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from app.models.constants import NEW_TO_OLD_REPORTER_MAP
from app.models.database import db
from app.models.mixins import HostTypeDeriver
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile
from app.models.utils import _create_staleness_timestamps_values
from app.models.utils import _set_display_name_on_save
from app.models.utils import _time_now
from app.models.utils import get_staleness_obj
from app.utils import Tag

logger = get_logger(__name__)


RHSM_REPORTERS = {"rhsm-conduit", "rhsm-system-profile-bridge"}
DISPLAY_NAME_PRIORITY_REPORTERS = {"puptoo", "API"}

# Fields that should be merged (shallow) instead of replaced when updating system profiles.
SYSTEM_PROFILE_MERGE_FIELDS = {"rhsm", "workloads"}


class LimitedHost(db.Model, HostTypeDeriver):
    __tablename__ = "hosts"
    __table_args__ = ({"schema": INVENTORY_SCHEMA},)

    def __init__(
        self,
        *,
        display_name=None,
        ansible_host=None,
        account=None,
        org_id=None,
        facts=None,
        tags=None,
        tags_alt=None,
        system_profile_facts=None,
        groups=None,
        id=None,
        insights_id=None,
        subscription_manager_id=None,
        satellite_id=None,
        fqdn=None,
        bios_uuid=None,
        ip_addresses=None,
        mac_addresses=None,
        provider_id=None,
        provider_type=None,
        openshift_cluster_id=None,
    ):
        if id:
            self.id = id
        if tags is None:
            tags = {}
            tags_alt = []
        else:
            tags_alt = self._populate_tags_alt_from_tags(tags)
        if groups is None:
            groups = []

        if display_name:
            self.display_name = display_name
        self._update_ansible_host(ansible_host)
        self.account = account
        self.org_id = org_id
        self.facts = facts or {}
        self.tags = tags
        self.tags_alt = tags_alt
        self._add_or_update_normalized_system_profiles(system_profile_facts)
        self.groups = groups or []

        self.last_check_in = _time_now()
        # canonical facts
        self.insights_id = insights_id
        self.subscription_manager_id = subscription_manager_id
        self.satellite_id = satellite_id
        self.fqdn = fqdn
        self.bios_uuid = bios_uuid
        self.ip_addresses = ip_addresses
        self.mac_addresses = mac_addresses
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.openshift_cluster_id = openshift_cluster_id

    def _update_ansible_host(self, ansible_host):
        if ansible_host is not None:
            self.ansible_host = ansible_host

    def _populate_tags_alt_from_tags(self, tags):
        if isinstance(tags, dict):
            transformed_tags_obj = Tag.create_tags_from_nested(tags)
            transformed_tags = [tag.data() for tag in transformed_tags_obj]
        elif isinstance(tags, list):
            transformed_tags = tags
        else:
            raise TypeError("Tags must be dict or list")

        return transformed_tags

    @hybrid_property
    def operating_system(self):
        name = ""
        major = 0
        minor = 0

        if self.static_system_profile and (os := self.static_system_profile.operating_system):
            name = os.get("name", "")
            major = os.get("major", 0)
            minor = os.get("minor", 0)

        return f"{name} {major:03}.{minor:03}"

    @operating_system.expression  # type: ignore [no-redef]
    def operating_system(cls):
        # Note: This assumes HostStaticSystemProfile is joined in the query
        return case(
            (
                HostStaticSystemProfile.operating_system.isnot(None),
                func.concat(
                    HostStaticSystemProfile.operating_system["name"].astext,
                    " ",
                    func.lpad(cast(HostStaticSystemProfile.operating_system["major"].astext, String), 3, "0"),
                    ".",
                    func.lpad(cast(HostStaticSystemProfile.operating_system["minor"].astext, String), 3, "0"),
                ),
            ),
            else_=" 000.000",
        )

    def _update_derived_host_type(self):
        """
        Update the denormalized host_type column from system profile.

        This method should be called whenever the system profile is updated
        to keep the host_type column in sync with the source data.
        """
        derived = self.derive_host_type()
        if derived != self.host_type:
            self.host_type = derived
            orm.attributes.flag_modified(self, "host_type")

    @staticmethod
    def _update_profile_attributes(profile, data: dict, skip_keys: set | None = None):
        """
        Update a system profile object's attributes from a dictionary.

        For fields in SYSTEM_PROFILE_MERGE_FIELDS, performs a shallow merge with existing data.
        For all other fields, replaces the value entirely.
        Skips writes when the new value matches the current value.
        """
        skip_keys = skip_keys or set()

        for key, value in data.items():
            if key in skip_keys:
                continue

            if key in SYSTEM_PROFILE_MERGE_FIELDS and value:
                existing = getattr(profile, key, None) or {}
                merged = {**existing, **value}
                if merged != existing:
                    setattr(profile, key, merged)
            else:
                if getattr(profile, key, None) != value:
                    setattr(profile, key, value)

    def _add_or_update_normalized_system_profiles(self, input_system_profile: dict):
        """Update the normalized system profile tables."""
        from copy import deepcopy

        from app.models.schemas import LimitedHostSchema
        from app.models.system_profile_transformer import validate_and_transform

        if not input_system_profile:
            self._update_derived_host_type()
            return

        # Make a copy and migrate legacy workload fields to workloads.* for the normalized tables
        # This ensures backward compatibility: legacy fields in input are converted to workloads.*
        # before being written to the new system_profiles_dynamic.workloads column
        system_profile_copy = deepcopy(input_system_profile)
        data_wrapper = {"system_profile": system_profile_copy}
        LimitedHostSchema._migrate_and_remove_legacy_workloads_fields(data_wrapper)
        migrated_profile = data_wrapper["system_profile"]

        # Transform and validate the data
        static_data, dynamic_data = validate_and_transform(str(self.org_id), str(self.id), migrated_profile)

        # Keys that are managed automatically and should not be updated from input
        skip_keys = {"org_id", "host_id"}

        # Update or create static system profile
        if static_data:
            if self.static_system_profile:
                self._update_profile_attributes(self.static_system_profile, static_data, skip_keys)
            else:
                self.static_system_profile = HostStaticSystemProfile(**static_data)

        # Update or create dynamic system profile
        if dynamic_data:
            if self.dynamic_system_profile:
                self._update_profile_attributes(self.dynamic_system_profile, dynamic_data, skip_keys)
            else:
                self.dynamic_system_profile = HostDynamicSystemProfile(**dynamic_data)

        self._update_derived_host_type()

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    org_id = db.Column(db.String(36), primary_key=True)
    display_name = db.Column(db.String(200), default=_set_display_name_on_save)
    ansible_host = db.Column(db.String(255))
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    tags_alt = db.Column(JSONB)

    # canonical facts
    insights_id = db.Column(UUID(as_uuid=True), nullable=False, default=DEFAULT_INSIGHTS_ID)
    subscription_manager_id = db.Column(db.String(36), nullable=True)
    satellite_id = db.Column(db.String(255), nullable=True)
    fqdn = db.Column(db.String(255), nullable=True)
    bios_uuid = db.Column(db.String(36), nullable=True)
    ip_addresses = db.Column(JSONB, nullable=True)
    mac_addresses = db.Column(JSONB, nullable=True)
    provider_id = db.Column(db.String(500), nullable=True)
    provider_type = db.Column(db.String(50), nullable=True)

    openshift_cluster_id = db.Column(UUID(as_uuid=True))
    host_type = db.Column(db.String(12))  # Denormalized from system_profiles_static for performance
    groups = db.Column(MutableList.as_mutable(JSONB), default=lambda: [], nullable=False)
    last_check_in = db.Column(db.DateTime(timezone=True))

    static_system_profile = relationship(
        "HostStaticSystemProfile", back_populates="host", cascade="all, delete-orphan", lazy="select", uselist=False
    )
    dynamic_system_profile = relationship(
        "HostDynamicSystemProfile", back_populates="host", cascade="all, delete-orphan", lazy="select", uselist=False
    )
    host_group_assocs = relationship("HostGroupAssoc", viewonly=True, lazy="noload")


class Host(LimitedHost):
    stale_timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    deletion_timestamp = db.Column(db.DateTime(timezone=True))
    stale_warning_timestamp = db.Column(db.DateTime(timezone=True))
    reporter = db.Column(db.String(255), nullable=False)
    per_reporter_staleness = db.Column(JSONB, nullable=False)
    display_name_reporter = db.Column(db.String(255))

    def __init__(
        self,
        *,
        display_name=None,
        ansible_host=None,
        account=None,
        org_id=None,
        facts=None,
        tags=None,
        tags_alt=None,
        system_profile_facts=None,
        stale_timestamp=None,  # noqa: ARG002 - to be removed
        reporter=None,
        per_reporter_staleness=None,
        groups=None,
        id=None,
        insights_id=None,
        subscription_manager_id=None,
        satellite_id=None,
        fqdn=None,
        bios_uuid=None,
        ip_addresses=None,
        mac_addresses=None,
        provider_id=None,
        provider_type=None,
        openshift_cluster_id=None,
    ):
        if tags is None:
            tags = {}

        if groups is None:
            groups = []

        local_vars = locals()
        fact_fields = tuple(local_vars[field] for field in CANONICAL_FACTS_FIELDS)
        if all(field is None for field in fact_fields):
            raise ValidationException("At least one of the canonical fact fields must be present.")

        id_fact_fields = tuple(local_vars[field] for field in ID_FACTS)
        if all(field is None for field in id_fact_fields):
            raise ValidationException(f"At least one of the ID fact fields must be present: {ID_FACTS}")

        if current_app.config["USE_SUBMAN_ID"] and subscription_manager_id is not None:
            id = subscription_manager_id

        if not reporter:
            raise ValidationException("The reporter field must be present.")

        if tags is None:
            raise ValidationException("The tags field cannot be null.")

        super().__init__(
            display_name=display_name,
            ansible_host=ansible_host,
            account=account,
            org_id=org_id,
            facts=facts,
            tags=tags,
            tags_alt=tags_alt,
            system_profile_facts=system_profile_facts,
            groups=groups,
            id=id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            satellite_id=satellite_id,
            fqdn=fqdn,
            bios_uuid=bios_uuid,
            ip_addresses=ip_addresses,
            mac_addresses=mac_addresses,
            provider_id=provider_id,
            provider_type=provider_type,
            openshift_cluster_id=openshift_cluster_id,
        )
        self.reporter = reporter
        if display_name:
            self.display_name_reporter = reporter

        self._update_last_check_in_date()
        self._update_staleness_timestamps()

        self.per_reporter_staleness = per_reporter_staleness or {}
        if not per_reporter_staleness:
            self._update_per_reporter_staleness(reporter)

        self._update_derived_host_type()

    def save(self):
        self._cleanup_tags()
        db.session.add(self)

    def update(self, input_host: "Host", update_system_profile: bool = False) -> None:
        self.update_display_name(input_host.display_name, input_host.reporter, input_fqdn=input_host.fqdn)

        canonical_facts_to_update = {}
        for field in CANONICAL_FACTS_FIELDS:
            value = getattr(input_host, field, None)
            if value is not None:
                canonical_facts_to_update[field] = value

        if canonical_facts_to_update:
            self.update_canonical_facts_columns(canonical_facts_to_update)

        self._update_ansible_host(input_host.ansible_host)

        self.update_facts(input_host.facts)

        self._update_tags(input_host.tags)

        if input_host.org_id:
            self.org_id = input_host.org_id

        self.reporter = input_host.reporter

        if update_system_profile:
            # Get system profile data from the serialized representation
            from app.serialization import build_system_profile_from_normalized

            system_profile = build_system_profile_from_normalized(input_host)
            if system_profile:
                self.update_system_profile(system_profile)

        self._update_last_check_in_date()
        self._update_per_reporter_staleness(input_host.reporter)
        self._update_staleness_timestamps()

    def patch(self, patch_data):
        logger.debug("patching host (id=%s) with data: %s", self.id, patch_data)

        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        self.update_display_name(patch_data.get("display_name"), "API")
        self._update_ansible_host(patch_data.get("ansible_host"))

    def _should_ignore_display_name_update(self, input_reporter: str) -> bool:
        # Ignore display_name updates from RHSM, if it has already been updated by API or insights-client
        # https://issues.redhat.com/browse/RHINENG-19514
        return input_reporter in RHSM_REPORTERS and self.display_name_reporter in DISPLAY_NAME_PRIORITY_REPORTERS

    def _apply_display_name_fallback(self, input_fqdn: str | None) -> None:
        if not self.display_name or self.display_name == self.fqdn or self.display_name == str(self.id):
            self.display_name = input_fqdn or self.fqdn or self.id

    def update_display_name(
        self, input_display_name: str | None, input_reporter: str, *, input_fqdn: str | None = None
    ) -> None:
        if input_display_name:
            if self._should_ignore_display_name_update(input_reporter):
                logger.debug(
                    f"Ignoring display_name update from {input_reporter}, "
                    f"current display_name_reporter: {self.display_name_reporter}"
                )
                return
            if self.display_name == input_display_name and self.display_name_reporter == input_reporter:
                return
            self.display_name = input_display_name
            self.display_name_reporter = input_reporter
        else:
            self._apply_display_name_fallback(input_fqdn)

    def update_canonical_facts_columns(self, canonical_facts):
        try:
            for key, value in canonical_facts.items():
                current_value = getattr(self, key)
                # Handle type conversion for comparison (e.g., UUID vs string)
                # Convert both to strings for comparison to avoid false positives
                current_value_str = str(current_value) if current_value is not None else None
                value_str = str(value) if value is not None else None

                if current_value_str != value_str:
                    setattr(self, key, value)
                    orm.attributes.flag_modified(self, key)
        except AttributeError as e:
            logger.warning("Error updating canonical facts column %s: %s", key, str(e))
            raise e

    def update_facts(self, facts_dict):
        if facts_dict:
            if not self.facts:
                self.facts = facts_dict
                return

            for input_namespace, input_facts in facts_dict.items():
                self.replace_facts_in_namespace(input_namespace, input_facts)

    def _update_per_reporter_staleness(self, reporter):
        if not self.per_reporter_staleness:
            self.per_reporter_staleness = {}

        if old_reporter := NEW_TO_OLD_REPORTER_MAP.get(reporter):
            self.per_reporter_staleness.pop(old_reporter, None)

        self.per_reporter_staleness[reporter] = self.last_check_in.isoformat()
        orm.attributes.flag_modified(self, "per_reporter_staleness")

    def _update_last_check_in_date(self):
        self.last_check_in = _time_now()
        orm.attributes.flag_modified(self, "last_check_in")

    def _update_modified_date(self):
        self.modified_on = _time_now()

    def replace_facts_in_namespace(self, namespace, facts_dict):
        self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

    def _update_tags(self, tags_dict):
        if self.tags is None:
            raise InventoryException(
                title="Invalid request", detail="Tags must be either an object or an array, and cannot be null."
            )

        for namespace, ns_tags in tags_dict.items():
            if ns_tags:
                self._replace_tags_in_namespace(namespace, ns_tags)
            else:
                self._delete_tags_namespace(namespace)

        self._update_tags_alt(tags_dict)

    def _update_tags_alt(self, tags_dict):
        for namespace, ns_tags in tags_dict.items():
            if ns_tags:
                self._replace_tags_alt_in_namespace(tags_dict)
            else:
                self._delete_tags_alt_namespace(namespace)

    def _replace_tags_in_namespace(self, namespace, tags):
        self.tags[namespace] = tags
        orm.attributes.flag_modified(self, "tags")

    def _replace_tags_alt_in_namespace(self, tags_dict):
        final_tags_alt = []
        if self.tags_alt:
            final_tags_alt = [t for t in self.tags_alt if t["namespace"] not in tags_dict]

        for ns, ns_items in tags_dict.items():
            for key, values in ns_items.items():
                final_tags_alt.extend({"namespace": ns, "key": key, "value": value} for value in values)

        self.tags_alt = final_tags_alt

        orm.attributes.flag_modified(self, "tags_alt")

    def _delete_tags_namespace(self, namespace):
        with suppress(KeyError):
            del self.tags[namespace]

        orm.attributes.flag_modified(self, "tags")

    def _delete_tags_alt_namespace(self, namespace):
        if self.tags_alt:
            for i, tag in enumerate(self.tags_alt):
                if tag.get("namespace") == namespace:
                    with suppress(KeyError):
                        del self.tags_alt[i]

                orm.attributes.flag_modified(self, "tags_alt")

    def _cleanup_tags(self):
        namespaces_to_delete = tuple(namespace for namespace, items in self.tags.items() if not items)
        for namespace in namespaces_to_delete:
            self._delete_tags_namespace(namespace)

    def merge_facts_in_namespace(self, namespace, facts_dict):
        if not facts_dict:
            return

        if self.facts[namespace]:
            self.facts[namespace] = {**self.facts[namespace], **facts_dict}
        else:
            self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

    def update_system_profile(self, input_system_profile: dict):
        logger.debug("Updating host's (id=%s) system profile", self.id)

        try:
            self._add_or_update_normalized_system_profiles(input_system_profile)
        except Exception as e:
            logger.warning("Failed to update normalized system profile tables for host %s: %s", self.id, str(e))

    def _update_staleness_timestamps(self):
        staleness_timestamps = _create_staleness_timestamps_values(self, self.org_id)
        self.stale_timestamp = staleness_timestamps["stale_timestamp"]
        self.stale_warning_timestamp = staleness_timestamps["stale_warning_timestamp"]
        self.deletion_timestamp = staleness_timestamps["culled_timestamp"]

        orm.attributes.flag_modified(self, "stale_timestamp")
        orm.attributes.flag_modified(self, "stale_warning_timestamp")
        orm.attributes.flag_modified(self, "deletion_timestamp")

    def reporter_stale(self, reporter):
        reporter_data = self.per_reporter_staleness.get(reporter, None)
        if not reporter_data:
            logger.debug("Reports from %s are stale (no check-in recorded)", reporter)
            return True

        if not isinstance(reporter_data, str):
            raise ValidationException(
                f"Invalid per_reporter_staleness for reporter {reporter!r}: "
                f"expected ISO-8601 string, got {type(reporter_data).__name__}."
            )
        try:
            last_check_in = isoparse(reporter_data)
        except ValueError as e:
            raise ValidationException(str(e)) from e

        staleness_ts = Timestamps.from_config(inventory_config())
        staleness = get_staleness_obj(self.org_id)
        pr_stale_timestamp = staleness_ts.stale_timestamp(last_check_in, staleness["conventional_time_to_stale"])

        logger.debug("per_reporter_staleness[%s] stale_timestamp: %s", reporter, pr_stale_timestamp)
        if _time_now() > pr_stale_timestamp:
            logger.debug("Reports from %s are stale", reporter)
            return True

        logger.debug("Reports from %s are not stale", reporter)
        return False

    @validates("per_reporter_staleness")
    def _validate_per_reporter_staleness(self, _key, value):
        out: dict[str, str] = {}
        if not value:
            return out
        for reporter, raw in dict(value).items():
            if isinstance(raw, dict):
                raise ValidationException(
                    f"Invalid per_reporter_staleness: reporter {reporter!r} has nested value; "
                    "ISO-8601 string required."
                )
            if isinstance(raw, datetime):
                out[reporter] = raw.isoformat()
            elif isinstance(raw, str):
                out[reporter] = raw
            else:
                raise ValidationException(
                    f"Invalid per_reporter_staleness: reporter {reporter!r} value must be str or datetime, "
                    f"not {type(raw).__name__}."
                )
        return out

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' org_id='{self.org_id}' display_name='{self.display_name}' "
            f"insights_id='{self.insights_id}'>"
        )
