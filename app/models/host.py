import uuid
from contextlib import suppress

from dateutil.parser import isoparse
from flask import current_app
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import orm
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import column_property
from sqlalchemy.orm import relationship

from app.config import ID_FACTS
from app.culling import should_host_stay_fresh_forever
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.models.constants import INVENTORY_SCHEMA
from app.models.constants import NEW_TO_OLD_REPORTER_MAP
from app.models.database import db
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile
from app.models.utils import _create_staleness_timestamps_values
from app.models.utils import _set_display_name_on_save
from app.models.utils import _time_now
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.utils import Tag

logger = get_logger(__name__)

RHSM_REPORTERS = {"rhsm-conduit", "rhsm-system-profile-bridge"}
DISPLAY_NAME_PRIORITY_REPORTERS = {"puptoo", "API"}


class LimitedHost(db.Model):
    __tablename__ = "hosts"
    __table_args__ = (
        Index("idxinsightsid", text("(canonical_facts ->> 'insights_id')")),
        Index("idxgincanonicalfacts", "canonical_facts"),
        Index("idxorgid", "org_id"),
        Index("hosts_subscription_manager_id_index", text("(canonical_facts ->> 'subscription_manager_id')")),
        Index("idxdisplay_name", "display_name"),
        Index("idxsystem_profile_facts", "system_profile_facts", postgresql_using="gin"),
        Index("idxgroups", "groups", postgresql_using="gin"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        canonical_facts=None,
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

        self.canonical_facts = canonical_facts

        if display_name:
            self.display_name = display_name
        self._update_ansible_host(ansible_host)
        self.account = account
        self.org_id = org_id
        self.facts = facts or {}
        self.tags = tags
        self.tags_alt = tags_alt
        self.system_profile_facts = system_profile_facts or {}
        self._update_normalized_system_profiles(system_profile_facts)
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

        if "operating_system" in self.system_profile_facts:
            name = self.system_profile_facts["operating_system"]["name"]
            major = self.system_profile_facts["operating_system"]["major"]
            minor = self.system_profile_facts["operating_system"]["minor"]

        return f"{name} {major:03}.{minor:03}"

    @operating_system.expression  # type: ignore [no-redef]
    def operating_system(cls):
        return case(
            (
                cls.system_profile_facts.has_key("operating_system"),
                func.concat(
                    cls.system_profile_facts["operating_system"]["name"],
                    " ",
                    func.lpad(cast(cls.system_profile_facts["operating_system"]["major"], String), 3, "0"),
                    ".",
                    func.lpad(cast(cls.system_profile_facts["operating_system"]["minor"], String), 3, "0"),
                ),
            ),
            else_=" 000.000",
        )

    def _update_normalized_system_profiles(self, input_system_profile: dict):
        """Update the normalized system profile tables."""
        from app.models.system_profile_transformer import validate_and_transform

        if not input_system_profile:
            return

        # Transform and validate the data
        static_data, dynamic_data = validate_and_transform(str(self.org_id), str(self.id), input_system_profile)

        # Update or create static system profile
        if static_data:
            if self.static_system_profile:
                # Update existing record
                for key, value in static_data.items():
                    if key not in ["org_id", "host_id"]:
                        setattr(self.static_system_profile, key, value)
            else:
                # Create new record
                self.static_system_profile = HostStaticSystemProfile(**static_data)

        # Update or create dynamic system profile
        if dynamic_data:
            if self.dynamic_system_profile:
                # Update existing record
                for key, value in dynamic_data.items():
                    if key not in ["org_id", "host_id"]:
                        setattr(self.dynamic_system_profile, key, value)
            else:
                # Create new record
                self.dynamic_system_profile = HostDynamicSystemProfile(**dynamic_data)

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
    canonical_facts = db.Column(JSONB)

    # canonical facts
    insights_id = db.Column(UUID(as_uuid=True), nullable=False, default="00000000-0000-0000-0000-000000000000")
    subscription_manager_id = db.Column(db.String(36))
    satellite_id = db.Column(db.String(255))
    fqdn = db.Column(db.String(255))
    bios_uuid = db.Column(db.String(36))
    ip_addresses = db.Column(JSONB)
    mac_addresses = db.Column(JSONB)
    provider_id = db.Column(db.String(500))
    provider_type = db.Column(db.String(50))

    system_profile_facts = db.Column(JSONB)
    groups = db.Column(MutableList.as_mutable(JSONB), default=lambda: [])
    host_type = column_property(system_profile_facts["host_type"])
    last_check_in = db.Column(db.DateTime(timezone=True))

    static_system_profile = relationship(
        "HostStaticSystemProfile", back_populates="host", cascade="all, delete-orphan", lazy="select", uselist=False
    )
    dynamic_system_profile = relationship(
        "HostDynamicSystemProfile", back_populates="host", cascade="all, delete-orphan", lazy="select", uselist=False
    )


class Host(LimitedHost):
    stale_timestamp = db.Column(db.DateTime(timezone=True))
    deletion_timestamp = db.Column(db.DateTime(timezone=True))
    stale_warning_timestamp = db.Column(db.DateTime(timezone=True))
    reporter = db.Column(db.String(255))
    per_reporter_staleness = db.Column(JSONB)
    display_name_reporter = db.Column(db.String(255))

    def __init__(
        self,
        canonical_facts,
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
        insights_id=None,
        subscription_manager_id=None,
        satellite_id=None,
        fqdn=None,
        bios_uuid=None,
        ip_addresses=None,
        mac_addresses=None,
        provider_id=None,
        provider_type=None,
    ):
        id = None
        if tags is None:
            tags = {}

        if groups is None:
            groups = []

        if not canonical_facts:
            raise ValidationException("At least one of the canonical fact fields must be present.")

        if all(id_fact not in canonical_facts for id_fact in ID_FACTS):
            raise ValidationException(f"At least one of the ID fact fields must be present: {ID_FACTS}")

        if current_app.config["USE_SUBMAN_ID"] and "subscription_manager_id" in canonical_facts:
            id = canonical_facts["subscription_manager_id"]

        if not reporter:
            raise ValidationException("The reporter field must be present.")

        if tags is None:
            raise ValidationException("The tags field cannot be null.")

        super().__init__(
            canonical_facts,
            display_name,
            ansible_host,
            account,
            org_id,
            facts,
            tags,
            tags_alt,
            system_profile_facts,
            groups,
            id,
            insights_id,
            subscription_manager_id,
            satellite_id,
            fqdn,
            bios_uuid,
            ip_addresses,
            mac_addresses,
            provider_id,
            provider_type,
        )
        self.reporter = reporter
        if display_name:
            self.display_name_reporter = reporter

        self._update_last_check_in_date()
        self._update_staleness_timestamps()

        self.per_reporter_staleness = per_reporter_staleness or {}
        if not per_reporter_staleness:
            self._update_per_reporter_staleness(reporter)

        self.update_canonical_facts(canonical_facts)
        self.update_canonical_facts_columns(canonical_facts)

    def save(self):
        self._cleanup_tags()
        db.session.add(self)

    def update(self, input_host: "Host", update_system_profile: bool = False) -> None:
        self.update_display_name(
            input_host.display_name, input_host.reporter, input_fqdn=input_host.canonical_facts.get("fqdn")
        )

        self.update_canonical_facts(input_host.canonical_facts)

        self.update_canonical_facts_columns(input_host.canonical_facts)

        self._update_ansible_host(input_host.ansible_host)

        self.update_facts(input_host.facts)

        self._update_tags(input_host.tags)

        if input_host.org_id:
            self.org_id = input_host.org_id

        self.reporter = input_host.reporter

        if update_system_profile:
            self.update_system_profile(input_host.system_profile_facts)

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
        if (
            not self.display_name
            or self.display_name == self.canonical_facts.get("fqdn")
            or self.display_name == str(self.id)
        ):
            self.display_name = input_fqdn or self.canonical_facts.get("fqdn") or self.id

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
            self.display_name = input_display_name
            self.display_name_reporter = input_reporter
        else:
            self._apply_display_name_fallback(input_fqdn)

    def update_canonical_facts(self, canonical_facts):
        logger.debug(
            "Updating host's (id=%s) canonical_facts (%s) with input canonical_facts=%s",
            self.id,
            self.canonical_facts,
            canonical_facts,
        )
        self.canonical_facts.update(canonical_facts)  # Field being removed in the future
        logger.debug("Host (id=%s) has updated canonical_facts (%s)", self.id, self.canonical_facts)
        orm.attributes.flag_modified(self, "canonical_facts")  # Field being removed in the future

    def update_canonical_facts_columns(self, canonical_facts):
        try:
            for key, value in canonical_facts.items():
                if getattr(self, key) != value:
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

    def _update_all_per_reporter_staleness(self, staleness, staleness_ts):
        for reporter in self.per_reporter_staleness:
            st = get_reporter_staleness_timestamps(self, staleness_ts, staleness, reporter)
            self.per_reporter_staleness[reporter].update(
                stale_timestamp=st["stale_timestamp"].isoformat(),
                culled_timestamp=st["culled_timestamp"].isoformat(),
                stale_warning_timestamp=st["stale_warning_timestamp"].isoformat(),
                last_check_in=self.per_reporter_staleness[reporter]["last_check_in"],
                check_in_succeeded=True,
            )
        orm.attributes.flag_modified(self, "per_reporter_staleness")

    def _update_all_per_reporter_staleness_for_rhsm_hosts(self, staleness_ts, staleness):
        st = get_staleness_timestamps(self, staleness_ts, staleness)
        for reporter in self.per_reporter_staleness:
            self.per_reporter_staleness[reporter].update(
                stale_timestamp=st["stale_timestamp"].isoformat(),
                culled_timestamp=st["culled_timestamp"].isoformat(),
                stale_warning_timestamp=st["stale_warning_timestamp"].isoformat(),
                last_check_in=self.last_check_in.isoformat(),
                check_in_succeeded=True,
            )
        orm.attributes.flag_modified(self, "per_reporter_staleness")

    def _update_per_reporter_staleness(self, reporter):
        if not self.per_reporter_staleness:
            self.per_reporter_staleness = {}

        if not self.per_reporter_staleness.get(reporter):
            self.per_reporter_staleness[reporter] = {}

        if old_reporter := NEW_TO_OLD_REPORTER_MAP.get(reporter):
            self.per_reporter_staleness.pop(old_reporter, None)

        # For hosts that should stay fresh forever, set far-future timestamps
        if should_host_stay_fresh_forever(self):
            self.per_reporter_staleness[reporter].update(
                stale_timestamp=FAR_FUTURE_STALE_TIMESTAMP.isoformat(),
                culled_timestamp=FAR_FUTURE_STALE_TIMESTAMP.isoformat(),
                stale_warning_timestamp=FAR_FUTURE_STALE_TIMESTAMP.isoformat(),
                last_check_in=self.last_check_in.isoformat(),
                check_in_succeeded=True,
            )
        else:
            st = _create_staleness_timestamps_values(self, self.org_id)

            self.per_reporter_staleness[reporter].update(
                stale_timestamp=st["stale_timestamp"].isoformat(),
                culled_timestamp=st["culled_timestamp"].isoformat(),
                stale_warning_timestamp=st["stale_warning_timestamp"].isoformat(),
                last_check_in=self.last_check_in.isoformat(),
                check_in_succeeded=True,
            )
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

        # Update the existing JSONB column (backward compatibility)
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            for key, value in input_system_profile.items():
                if key in ["rhsm", "workloads"]:
                    self.system_profile_facts[key] = {**self.system_profile_facts.get(key, {}), **value}
                else:
                    self.system_profile_facts[key] = value
        orm.attributes.flag_modified(self, "system_profile_facts")

        # Update the normalized system profile tables
        try:
            self._update_normalized_system_profiles(input_system_profile)
        except ValidationException as e:
            logger.warning("Failed to update normalized system profile tables for host %s: %s", self.id, str(e))
        except Exception as e:
            logger.warning("Failed to update normalized system profile tables for host %s: %s", self.id, str(e))

    def _update_staleness_timestamps(self):
        if should_host_stay_fresh_forever(self):
            self.stale_timestamp = FAR_FUTURE_STALE_TIMESTAMP
            self.stale_warning_timestamp = FAR_FUTURE_STALE_TIMESTAMP
            self.deletion_timestamp = FAR_FUTURE_STALE_TIMESTAMP
        else:
            staleness_timestamps = _create_staleness_timestamps_values(self, self.org_id)
            self.stale_timestamp = staleness_timestamps["stale_timestamp"]
            self.stale_warning_timestamp = staleness_timestamps["stale_warning_timestamp"]
            self.deletion_timestamp = staleness_timestamps["culled_timestamp"]

        orm.attributes.flag_modified(self, "stale_timestamp")
        orm.attributes.flag_modified(self, "stale_warning_timestamp")
        orm.attributes.flag_modified(self, "deletion_timestamp")

    def reporter_stale(self, reporter):
        # Hosts that should stay fresh forever are never stale
        if should_host_stay_fresh_forever(self):
            logger.debug("Host should stay fresh forever, reports from %s are not stale", reporter)
            return False

        prs = self.per_reporter_staleness.get(reporter, None)
        if not prs:
            logger.debug("Reports from %s are stale", reporter)
            return True

        pr_stale_timestamp = isoparse(prs["stale_timestamp"])
        logger.debug("per_reporter_staleness[%s]['stale_timestamp']: %s", reporter, pr_stale_timestamp)
        if _time_now() > pr_stale_timestamp:
            logger.debug("Reports from %s are stale", reporter)
            return True

        logger.debug("Reports from %s are not stale", reporter)
        return False

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' org_id='{self.org_id}' display_name='{self.display_name}' "
            f"canonical_facts={self.canonical_facts}>"
        )
