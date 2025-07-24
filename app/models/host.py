import os
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

from app.common import inventory_config
from app.config import ID_FACTS
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models.constants import EDGE_HOST_STALE_TIMESTAMP
from app.models.constants import INVENTORY_SCHEMA
from app.models.constants import NEW_TO_OLD_REPORTER_MAP
from app.models.database import db
from app.models.utils import _create_staleness_timestamps_values
from app.models.utils import _set_display_name_on_save
from app.models.utils import _time_now
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.utils import Tag
from lib.feature_flags import FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)


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
        self.groups = groups or []
        self.last_check_in = _time_now()

        if not inventory_config().hbi_db_refactoring_use_old_table:
            # New code: assign canonical facts to individual columns
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

    if os.environ.get("HBI_DB_REFACTORING_USE_OLD_TABLE", "false").lower() != "true":
        insights_id = db.Column(UUID(as_uuid=True), default="00000000-0000-0000-0000-000000000000")
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


class Host(LimitedHost):
    stale_timestamp = db.Column(db.DateTime(timezone=True))
    deletion_timestamp = db.Column(db.DateTime(timezone=True))
    stale_warning_timestamp = db.Column(db.DateTime(timezone=True))
    reporter = db.Column(db.String(255))
    per_reporter_staleness = db.Column(JSONB)

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
        stale_timestamp=None,
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

        if not stale_timestamp or not reporter:
            raise ValidationException("Both stale_timestamp and reporter fields must be present.")

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

        self._update_last_check_in_date()
        self._update_stale_timestamp(stale_timestamp, reporter)

        self._update_staleness_timestamps()

        self.per_reporter_staleness = per_reporter_staleness or {}
        if not per_reporter_staleness:
            self._update_per_reporter_staleness(reporter)

        if not inventory_config().hbi_db_refactoring_use_old_table:
            # New code: update canonical facts to individual columns
            self.update_canonical_facts(canonical_facts)

    def save(self):
        self._cleanup_tags()
        db.session.add(self)

    def update(self, input_host, update_system_profile=False):
        self.update_display_name(input_host.display_name, input_host.canonical_facts.get("fqdn"))

        self.update_canonical_facts(input_host.canonical_facts)

        self._update_ansible_host(input_host.ansible_host)

        self.update_facts(input_host.facts)

        self._update_tags(input_host.tags)

        if input_host.org_id:
            self.org_id = input_host.org_id

        if update_system_profile:
            self.update_system_profile(input_host.system_profile_facts)

        self._update_stale_timestamp(input_host.stale_timestamp, input_host.reporter)
        self._update_last_check_in_date()
        self._update_per_reporter_staleness(input_host.reporter)
        self._update_staleness_timestamps()

    def patch(self, patch_data):
        logger.debug("patching host (id=%s) with data: %s", self.id, patch_data)

        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        self.update_display_name(patch_data.get("display_name"))
        self._update_ansible_host(patch_data.get("ansible_host"))

    def update_display_name(self, input_display_name, input_fqdn=None):
        if input_display_name:
            self.display_name = input_display_name
        elif (
            not self.display_name
            or self.display_name == self.canonical_facts.get("fqdn")
            or self.display_name == str(self.id)
        ):
            self.display_name = input_fqdn or self.canonical_facts.get("fqdn") or self.id

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

    def update_facts(self, facts_dict):
        if facts_dict:
            if not self.facts:
                self.facts = facts_dict
                return

            for input_namespace, input_facts in facts_dict.items():
                self.replace_facts_in_namespace(input_namespace, input_facts)

    def _update_stale_timestamp(self, stale_timestamp, reporter):
        if self.system_profile_facts and self.system_profile_facts.get("host_type") == "edge":
            self.stale_timestamp = EDGE_HOST_STALE_TIMESTAMP
        else:
            self.stale_timestamp = stale_timestamp
        self.reporter = reporter

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

        if get_flag_value(FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS):
            st = _create_staleness_timestamps_values(self, self.org_id)

            self.per_reporter_staleness[reporter].update(
                stale_timestamp=st["stale_timestamp"].isoformat(),
                culled_timestamp=st["culled_timestamp"].isoformat(),
                stale_warning_timestamp=st["stale_warning_timestamp"].isoformat(),
                last_check_in=self.last_check_in.isoformat(),
                check_in_succeeded=True,
            )
        else:
            self.per_reporter_staleness[reporter].update(
                stale_timestamp=self.stale_timestamp.isoformat(),
                last_check_in=_time_now().isoformat(),
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
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            for key, value in input_system_profile.items():
                if key in ["rhsm", "workloads"]:
                    self.system_profile_facts[key] = {**self.system_profile_facts.get(key, {}), **value}
                else:
                    self.system_profile_facts[key] = value
        orm.attributes.flag_modified(self, "system_profile_facts")

    def _update_staleness_timestamps(self):
        if get_flag_value(FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS):
            staleness_timestamps = _create_staleness_timestamps_values(self, self.org_id)
            self.stale_timestamp = staleness_timestamps["stale_timestamp"]
            self.stale_warning_timestamp = staleness_timestamps["stale_warning_timestamp"]
            self.deletion_timestamp = staleness_timestamps["culled_timestamp"]

            orm.attributes.flag_modified(self, "stale_timestamp")
            orm.attributes.flag_modified(self, "stale_warning_timestamp")
            orm.attributes.flag_modified(self, "deletion_timestamp")

    def _update_staleness_timestamps_in_reaper(self, staleness_ts, staleness):
        if get_flag_value(FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS):
            staleness_timestamps = get_staleness_timestamps(self, staleness_ts, staleness)
            self.stale_timestamp = staleness_timestamps["stale_timestamp"]
            self.stale_warning_timestamp = staleness_timestamps["stale_warning_timestamp"]
            self.deletion_timestamp = staleness_timestamps["culled_timestamp"]

            orm.attributes.flag_modified(self, "stale_timestamp")
            orm.attributes.flag_modified(self, "stale_warning_timestamp")
            orm.attributes.flag_modified(self, "deletion_timestamp")

    def reporter_stale(self, reporter):
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
