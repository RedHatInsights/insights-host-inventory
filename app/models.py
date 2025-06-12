import os
import uuid
from collections import namedtuple
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from enum import Enum
from os.path import join

from connexion.utils import coerce_type
from dateutil.parser import isoparse
from flask import current_app
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from jsonschema import RefResolver
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as jsonschema_validate
from jsonschema.validators import Draft4Validator
from marshmallow import EXCLUDE
from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields
from marshmallow import post_load
from marshmallow import pre_load
from marshmallow import validate as marshmallow_validate
from marshmallow import validates
from marshmallow import validates_schema
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import case
from sqlalchemy import cast
from sqlalchemy import func
from sqlalchemy import orm
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import column_property
from sqlalchemy.orm.base import instance_state
from sqlalchemy.orm.exc import NoResultFound
from yaml import safe_load

from app.common import inventory_config
from app.config import ID_FACTS
from app.culling import Timestamps
from app.culling import days_to_seconds
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.staleness_serialization import build_serialized_acc_staleness_obj
from app.staleness_serialization import build_staleness_sys_default
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.utils import Tag
from app.validators import check_empty_keys
from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format
from lib.feature_flags import FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)

db = SQLAlchemy()
migrate = Migrate(db)

TAG_NAMESPACE_VALIDATION = marshmallow_validate.Length(max=255)
TAG_KEY_VALIDATION = marshmallow_validate.Length(min=1, max=255)
TAG_VALUE_VALIDATION = marshmallow_validate.Length(max=255)

SPECIFICATION_DIR = "./swagger/"
SYSTEM_PROFILE_SPECIFICATION_FILE = "system_profile.spec.yaml"

# set edge host stale_timestamp way out in future to Year 2260
EDGE_HOST_STALE_TIMESTAMP = datetime(2260, 1, 1, tzinfo=timezone.utc)

# Used when updating per_reporter_staleness from old to new keys.
NEW_TO_OLD_REPORTER_MAP = {"satellite": "yupana", "discovery": "yupana"}
# Used in filtering.
OLD_TO_NEW_REPORTER_MAP = {"yupana": ("satellite", "discovery")}

MIN_CANONICAL_FACTS_VERSION = 0
MAX_CANONICAL_FACTS_VERSION = 1

ZERO_MAC_ADDRESS = "00:00:00:00:00:00"

INVENTORY_SCHEMA = os.getenv("INVENTORY_DB_SCHEMA", "hbi")


class ProviderType(str, Enum):
    ALIBABA = "alibaba"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    IBM = "ibm"


def _get_staleness_obj(org_id):
    try:
        staleness = Staleness.query.filter(Staleness.org_id == org_id).one()
        logger.info("Using custom account staleness")
        staleness = build_serialized_acc_staleness_obj(staleness)
    except NoResultFound:
        logger.debug(f"No staleness data found for org {org_id}, using system default values for model")
        staleness = build_staleness_sys_default(org_id)
        return staleness

    return staleness


def _set_display_name_on_save(context):
    """
    This method sets the display_name if it has not been set previously.
    This logic happens during the saving of the host record so that
    the id exists and can be used as the display_name if necessary.
    """
    params = context.get_current_parameters()
    if not params["display_name"] or params["display_name"] == str(params["id"]):
        return params["canonical_facts"].get("fqdn") or params["id"]


def _time_now():
    return datetime.now(timezone.utc)


def _create_staleness_timestamps_values(host, org_id):
    staleness = _get_staleness_obj(org_id)
    staleness_ts = Timestamps.from_config(inventory_config())
    return get_staleness_timestamps(host, staleness_ts, staleness)


class SystemProfileNormalizer:
    class Schema(namedtuple("Schema", ("type", "properties", "items"))):
        Types = Enum("Types", ("array", "object"))

        @classmethod
        def from_dict(cls, schema, resolver):
            if "$ref" in schema:
                _, schema = resolver.resolve(schema["$ref"])

            filtered = {key: schema.get(key) for key in cls._fields}
            return cls(**filtered)

        @property
        def schema_type(self):
            return self.Types.__members__.get(self.type)

    SOME_ARBITRARY_STRING = "property"

    def __init__(self, system_profile_schema=None):
        if system_profile_schema:
            system_profile_spec = system_profile_schema
        else:
            specification = join(SPECIFICATION_DIR, SYSTEM_PROFILE_SPECIFICATION_FILE)
            with open(specification) as file:
                system_profile_spec = safe_load(file)

        self.schema = {**system_profile_spec, "$ref": "#/$defs/SystemProfile"}
        self._resolver = RefResolver.from_schema(system_profile_spec)

    def filter_keys(self, payload, schema_dict=None):
        if schema_dict is None:
            schema_dict = self._system_profile_definition()

        schema_obj = self.Schema.from_dict(schema_dict, self._resolver)
        if schema_obj.schema_type == self.Schema.Types.object:
            self._object_filter(schema_obj, payload)
        elif schema_obj.schema_type == self.Schema.Types.array:
            self._array_filter(schema_obj, payload)

    def coerce_types(self, payload, schema_dict=None):
        if schema_dict is None:
            schema_dict = self._system_profile_definition()
        coerce_type(schema_dict, payload, self.SOME_ARBITRARY_STRING)

    def _system_profile_definition(self):
        return self.schema["$defs"]["SystemProfile"]

    def _object_filter(self, schema, payload):
        if not schema.properties or type(payload) is not dict:
            return

        for key in payload.keys() - schema.properties.keys():
            del payload[key]
        for key in payload:
            self.filter_keys(payload[key], schema.properties[key])

    def _array_filter(self, schema, payload):
        if not schema.items or type(payload) is not list:
            return

        for value in payload:
            self.filter_keys(value, schema.items)


class LimitedHost(db.Model):  # type: ignore [name-defined]
    __tablename__ = "hosts"
    # These Index entries are essentially place holders so that the
    # alembic autogenerate functionality does not try to remove the indexes
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
            # Only set the display_name field if input the display_name has
            # been set...this will make it so that the "default" logic will
            # get called during the save to fill in an empty display_name
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

    def _update_ansible_host(self, ansible_host):
        if ansible_host is not None:
            # Allow a user to clear out the ansible host with an empty string
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
        # Used when accessing the instance's property
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
        # Used when querying the model
        return case(
            # If the host has system_profile_facts.operating_system,
            # generate the string value to be sorted by ("name maj.min")
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
    org_id = db.Column(db.String(36))
    display_name = db.Column(db.String(200), default=_set_display_name_on_save)
    ansible_host = db.Column(db.String(255))
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    tags_alt = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)
    system_profile_facts = db.Column(JSONB)
    groups = db.Column(JSONB)
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
        )

        self._update_last_check_in_date()
        # without reporter and stale_timestamp host payload is invalid.
        self._update_stale_timestamp(stale_timestamp, reporter)

        self._update_staleness_timestamps()

        self.per_reporter_staleness = per_reporter_staleness or {}
        if not per_reporter_staleness:
            self._update_per_reporter_staleness(reporter)

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
            # This logical branch handles the display_name fallback values.
            # If the display_name isn't set and isn't provided in the update data,
            # we need to set it to a fallback value. If the display_name is set to
            # the ID or the old FQDN, we need to re-evaluate it.
            self.display_name = input_fqdn or self.canonical_facts.get("fqdn") or self.id

    def update_canonical_facts(self, canonical_facts):
        logger.debug(
            "Updating host's (id=%s) canonical_facts (%s) with input canonical_facts=%s",
            self.id,
            self.canonical_facts,
            canonical_facts,
        )
        self.canonical_facts.update(canonical_facts)
        logger.debug("Host (id=%s) has updated canonical_facts (%s)", self.id, self.canonical_facts)
        orm.attributes.flag_modified(self, "canonical_facts")

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

    # This method is only used by update_edge_hosts_prs
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
                last_check_in=datetime.now(timezone.utc).isoformat(),
                check_in_succeeded=True,
            )
        orm.attributes.flag_modified(self, "per_reporter_staleness")

    def _update_last_check_in_date(self):
        self.last_check_in = datetime.now(timezone.utc)
        orm.attributes.flag_modified(self, "last_check_in")

    def _update_modified_date(self):
        self.modified_on = datetime.now(timezone.utc)

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

    # these duplicated methods are going to be removed in a following task
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
        # Remove namespaces that are going to be updated from the list
        if self.tags_alt:
            final_tags_alt = [t for t in self.tags_alt if t["namespace"] not in tags_dict]

        for ns, ns_items in tags_dict.items():
            for key, values in ns_items.items():
                for value in values:
                    final_tags_alt.append({"namespace": ns, "key": key, "value": value})

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
            # The value currently stored in the namespace is None so replace it
            self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

    def update_system_profile(self, input_system_profile: dict):
        logger.debug("Updating host's (id=%s) system profile", self.id)
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            # Update the fields that were passed in
            for key, value in input_system_profile.items():
                if key in ["rhsm", "workloads"]:
                    # Special case to deep merge these.
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
            # No reports from reporter, its considered stale.
            logger.debug("Reports from %s are stale", reporter)
            return True

        pr_stale_timestamp = isoparse(prs["stale_timestamp"])
        timezone = pr_stale_timestamp.tzinfo
        logger.debug("per_reporter_staleness[%s]['stale_timestamp']: %s", reporter, pr_stale_timestamp)
        if datetime.now(timezone) > pr_stale_timestamp:
            logger.debug("Reports from %s are stale", reporter)
            return True

        logger.debug("Reports from %s are not stale", reporter)
        return False

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' org_id='{self.org_id}' display_name='{self.display_name}' "
            f"canonical_facts={self.canonical_facts}>"
        )


class Group(db.Model):  # type: ignore [name-defined]
    __tablename__ = "groups"
    __table_args__ = (
        Index("idxgrouporgid", "org_id"),
        Index("idx_groups_org_id_name_nocase", "org_id", text("lower(name)"), unique=True),
        Index("idxorgidungrouped", "org_id", "ungrouped"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        org_id,
        name,
        account=None,
        id=None,
        ungrouped=False,
    ):
        if not org_id:
            raise ValidationException("Group org_id cannot be null.")
        if not name:
            raise ValidationException("Group name cannot be null.")
        if id is not None:
            self.id = id

        self.org_id = org_id
        self.account = account
        self.name = name
        self.ungrouped = ungrouped

    def update_modified_on(self):
        self.modified_on = _time_now()

    def update(self, input_group):
        if input_group.name is not None:
            self.name = input_group.name
        if input_group.account is not None:
            self.account = input_group.account

    def patch(self, patch_data):
        logger.debug("patching group (id=%s) with data: %s", self.id, patch_data)
        if self.ungrouped is True:
            raise InventoryException(title="Bad Request", detail="The 'ungrouped' group can not be modified.")
        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        if "name" in patch_data:
            self.name = patch_data["name"]
            return True

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    org_id = db.Column(db.String(36), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    ungrouped = db.Column(db.Boolean, default=False, nullable=False)
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)
    hosts = orm.relationship("Host", secondary=f"{INVENTORY_SCHEMA}.hosts_groups")


class HostGroupAssoc(db.Model):  # type: ignore [name-defined]
    __tablename__ = "hosts_groups"
    __table_args__ = (
        Index("idxhostsgroups", "host_id", "group_id"),
        Index("idxgroups_hosts", "group_id", "host_id"),
        UniqueConstraint("host_id", name="hosts_groups_unique_host_id"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        host_id,
        group_id,
    ):
        self.host_id = host_id
        self.group_id = group_id

    host_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.hosts.id"), primary_key=True)
    group_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.groups.id"), primary_key=True)


class Staleness(db.Model):  # type: ignore [name-defined]
    __tablename__ = "staleness"
    __table_args__ = (
        Index("idxaccstaleorgid", "org_id"),
        UniqueConstraint("org_id", name="staleness_unique_org_id"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        org_id,
        conventional_time_to_stale=None,
        conventional_time_to_stale_warning=None,
        conventional_time_to_delete=None,
        immutable_time_to_stale=None,
        immutable_time_to_stale_warning=None,
        immutable_time_to_delete=None,
    ):
        if not org_id:
            raise ValidationException("Staleness org_id cannot be null.")

        self.org_id = org_id
        self.conventional_time_to_stale = conventional_time_to_stale
        self.conventional_time_to_stale_warning = conventional_time_to_stale_warning
        self.conventional_time_to_delete = conventional_time_to_delete
        self.immutable_time_to_stale = immutable_time_to_stale
        self.immutable_time_to_stale_warning = immutable_time_to_stale_warning
        self.immutable_time_to_delete = immutable_time_to_delete

    def update(self, input_acc):
        if input_acc.conventional_time_to_stale:
            self.conventional_time_to_stale = input_acc.conventional_time_to_stale
        if input_acc.conventional_time_to_stale_warning:
            self.conventional_time_to_stale_warning = input_acc.conventional_time_to_stale_warning
        if input_acc.conventional_time_to_delete:
            self.conventional_time_to_delete = input_acc.conventional_time_to_delete
        if input_acc.immutable_time_to_stale:
            self.immutable_time_to_stale = input_acc.immutable_time_to_stale
        if input_acc.immutable_time_to_stale_warning:
            self.immutable_time_to_stale_warning = input_acc.immutable_time_to_stale_warning
        if input_acc.immutable_time_to_delete:
            self.immutable_time_to_delete = input_acc.immutable_time_to_delete

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = db.Column(db.String(36), nullable=False)
    conventional_time_to_stale = db.Column(db.Integer, default=104400, nullable=False)
    conventional_time_to_stale_warning = db.Column(db.Integer, default=days_to_seconds(7), nullable=False)
    conventional_time_to_delete = db.Column(db.Integer, default=days_to_seconds(14), nullable=False)
    immutable_time_to_stale = db.Column(db.Integer, default=days_to_seconds(2), nullable=False)
    immutable_time_to_stale_warning = db.Column(db.Integer, default=days_to_seconds(180), nullable=False)
    immutable_time_to_delete = db.Column(db.Integer, default=days_to_seconds(730), nullable=False)
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)


class HostInventoryMetadata(db.Model):  # type: ignore [name-defined]
    __tablename__ = "hbi_metadata"
    __table_args__ = ({"schema": INVENTORY_SCHEMA},)

    def __init__(self, name, type):
        self.name = name
        self.type = type

    def _update_last_succeeded(self, last_succeed_run_datetime):
        self.last_succeeded = last_succeed_run_datetime

    name = db.Column(db.String(32), primary_key=True)
    type = db.Column(db.String(32), primary_key=True)
    last_succeeded = db.Column(
        db.DateTime(timezone=True), default=_time_now() - timedelta(hours=1), onupdate=_time_now
    )


class DiskDeviceSchema(MarshmallowSchema):
    device = fields.Str(validate=marshmallow_validate.Length(max=2048))
    label = fields.Str(validate=marshmallow_validate.Length(max=1024))
    options = fields.Dict(validate=check_empty_keys)
    mount_point = fields.Str(validate=marshmallow_validate.Length(max=2048))
    type = fields.Str(validate=marshmallow_validate.Length(max=256))


class RhsmSchema(MarshmallowSchema):
    version = fields.Str(validate=marshmallow_validate.Length(max=255))


class OperatingSystemSchema(MarshmallowSchema):
    major = fields.Int()
    minor = fields.Int()
    name = fields.Str(validate=marshmallow_validate.Length(max=4))


class YumRepoSchema(MarshmallowSchema):
    id = fields.Str(validate=marshmallow_validate.Length(max=256))
    name = fields.Str(validate=marshmallow_validate.Length(max=1024))
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Str(validate=marshmallow_validate.Length(max=2048))


class DnfModuleSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(max=128))
    stream = fields.Str(validate=marshmallow_validate.Length(max=128))


class InstalledProductSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(max=512))
    id = fields.Str(validate=marshmallow_validate.Length(max=64))
    status = fields.Str(validate=marshmallow_validate.Length(max=256))


class NetworkInterfaceSchema(MarshmallowSchema):
    ipv4_addresses = fields.List(fields.Str())
    ipv6_addresses = fields.List(fields.Str())
    state = fields.Str(validate=marshmallow_validate.Length(max=25))
    mtu = fields.Int()
    mac_address = fields.Str(validate=marshmallow_validate.Length(max=59))
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=50))
    type = fields.Str(validate=marshmallow_validate.Length(max=18))


class FactsSchema(MarshmallowSchema):
    namespace = fields.Str()
    facts = fields.Dict(validate=check_empty_keys)


class TagsSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    namespace = fields.Str(required=False, allow_none=True, validate=TAG_NAMESPACE_VALIDATION)
    key = fields.Str(required=True, allow_none=False, validate=TAG_KEY_VALIDATION)
    value = fields.Str(required=False, allow_none=True, validate=TAG_VALUE_VALIDATION)


class CanonicalFactsSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    canonical_facts_version = fields.Integer(
        required=False,
        load_default=MIN_CANONICAL_FACTS_VERSION,
        validate=marshmallow_validate.Range(min=MIN_CANONICAL_FACTS_VERSION, max=MAX_CANONICAL_FACTS_VERSION),
    )
    is_virtual = fields.Boolean(required=False)

    insights_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_satellite_id)
    fqdn = fields.Str(validate=marshmallow_validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=verify_ip_address_format))
    mac_addresses = fields.List(
        fields.Str(validate=verify_mac_address_format), validate=marshmallow_validate.Length(min=1)
    )
    provider_id = fields.Str(validate=marshmallow_validate.Length(min=1, max=500))
    provider_type = fields.Str(validate=marshmallow_validate.Length(min=1, max=50))

    @validates_schema
    def validate_schema(self, data, **kwargs):
        schema_version = data.get("canonical_facts_version")

        if "mac_addresses" in data:
            #
            # Remove all zero mac addresses from the list.
            #
            mac_addresses = data["mac_addresses"]
            while ZERO_MAC_ADDRESS in mac_addresses:
                logger.warning(f"Zero MAC address reported by: {data.get('reporter', 'Not Available')}")
                mac_addresses.remove(ZERO_MAC_ADDRESS)
            if not mac_addresses:
                #
                # If mac_addresses is now empty, we remove the mac_addresses key.
                # This is so we don't introduce a new failure case for varsion 0, and will
                # only fail for version 1.
                #
                del data["mac_addresses"]

        if schema_version > MIN_CANONICAL_FACTS_VERSION:
            if "is_virtual" not in data:
                raise MarshmallowValidationError(
                    f"is_virtual is required for canonical_facts_version > {MIN_CANONICAL_FACTS_VERSION}."
                )
            if "mac_addresses" not in data:
                raise MarshmallowValidationError(
                    f"mac_addresses is required for canonical_facts_version > {MIN_CANONICAL_FACTS_VERSION}."
                )
            if data["is_virtual"]:
                if "provider_id" not in data:
                    raise MarshmallowValidationError(
                        "provider_id and provider_type are required when is_virtual = True."
                    )
            else:
                if "provider_id" in data:
                    raise MarshmallowValidationError("provider_id is not allowed when is_virtual = False.")

        provider_type = data.get("provider_type")
        provider_id = data.get("provider_id")

        if (provider_type and not provider_id) or (provider_id and not provider_type):
            raise MarshmallowValidationError("provider_type and provider_id are both required.")

        if provider_type and provider_type.lower() not in ProviderType.__members__.values():
            raise MarshmallowValidationError(
                f'Unknown Provider Type: "{provider_type}".  '
                f"Valid provider types are: {', '.join([p.value for p in ProviderType])}."
            )

        # check for white spaces, tabs, and newline characters only
        if provider_id and provider_id.isspace():
            raise MarshmallowValidationError("Provider id can not be just blank, whitespaces or tabs")


class LimitedHostSchema(CanonicalFactsSchema):
    class Meta:
        unknown = EXCLUDE

    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    account = fields.Str(validate=marshmallow_validate.Length(min=0, max=10))
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=36))
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Dict()
    tags = fields.Raw()
    tags_alt = fields.Raw()
    groups = fields.List(fields.Dict())

    def __init__(self, system_profile_schema=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = type(self)
        if not hasattr(cls, "system_profile_normalizer"):
            cls.system_profile_normalizer = SystemProfileNormalizer()
        if system_profile_schema:
            self.system_profile_normalizer = SystemProfileNormalizer(system_profile_schema=system_profile_schema)

    @validates("tags")
    def validate_tags(self, tags, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if isinstance(tags, list):
            return self._validate_tags_list(tags)
        elif isinstance(tags, dict):
            return self._validate_tags_dict(tags)
        else:
            raise MarshmallowValidationError("Tags must be either an object or an array, and cannot be null.")

    @staticmethod
    def _validate_tags_list(tags):
        TagsSchema(many=True).load(tags)
        return True

    @staticmethod
    def _validate_tags_dict(tags):
        for namespace, ns_tags in tags.items():
            TAG_NAMESPACE_VALIDATION(namespace)
            if ns_tags is None:
                continue
            if not isinstance(ns_tags, dict):
                raise MarshmallowValidationError("Tags in a namespace must be an object or null.")

            for key, values in ns_tags.items():
                TAG_KEY_VALIDATION(key)
                if values is None:
                    continue
                if not isinstance(values, list):
                    raise MarshmallowValidationError("Tag values must be an array or null.")

                for value in values:
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise MarshmallowValidationError("Tag value must be a string or null.")
                    TAG_VALUE_VALIDATION(value)

        return True

    @staticmethod
    def _normalize_system_profile(normalize, data):
        if "system_profile" not in data:
            return data

        system_profile = deepcopy(data["system_profile"])
        normalize(system_profile)
        return {**data, "system_profile": system_profile}

    @staticmethod
    def build_model(data, canonical_facts, facts, tags, tags_alt=None):
        return LimitedHost(
            canonical_facts=canonical_facts,
            display_name=data.get("display_name"),
            ansible_host=data.get("ansible_host"),
            account=data.get("account"),
            org_id=data.get("org_id"),
            facts=facts,
            tags=tags,
            tags_alt=tags_alt if tags_alt else [],
            system_profile_facts=data.get("system_profile", {}),
            groups=data.get("groups", []),
        )

    @pre_load
    def coerce_system_profile_types(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.coerce_types, data)

    @post_load
    def filter_system_profile_keys(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.filter_keys, data)

    @validates("system_profile")
    def system_profile_is_valid(self, system_profile, data_key):  # noqa: ARG002, required for marshmallow validator functions
        try:
            jsonschema_validate(
                system_profile, self.system_profile_normalizer.schema, format_checker=Draft4Validator.FORMAT_CHECKER
            )
        except JsonSchemaValidationError as error:
            raise MarshmallowValidationError(f"System profile does not conform to schema.\n{error}") from error

        for dd_i, disk_device in enumerate(system_profile.get("disk_devices", [])):
            if not check_empty_keys(disk_device.get("options")):
                raise MarshmallowValidationError(f"Empty key in /system_profile/disk_devices/{dd_i}/options.")


class HostSchema(LimitedHostSchema):
    class Meta:
        unknown = EXCLUDE

    stale_timestamp = fields.AwareDateTime(required=True)
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))

    @staticmethod
    def build_model(data, canonical_facts, facts, tags, tags_alt=None):
        if tags_alt is None:
            tags_alt = []
        return Host(
            canonical_facts,
            data.get("display_name"),
            data.get("ansible_host"),
            data.get("account"),
            data.get("org_id"),
            facts,
            tags,
            tags_alt,
            data.get("system_profile", {}),
            data["stale_timestamp"],
            data["reporter"],
            data.get("groups", []),
        )


class PatchHostSchema(MarshmallowSchema):
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class InputGroupSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=255))
    host_ids = fields.List(fields.Str(validate=verify_uuid_format))

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data:
            in_data["name"] = in_data["name"].strip()

        return in_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class StalenessSchema(MarshmallowSchema):
    conventional_time_to_stale = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=604800)
    )  # Max of 7 days
    conventional_time_to_stale_warning = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=15552000)
    )  # Max of 180 days
    conventional_time_to_delete = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=63072000)
    )  # Max of 2 years
    immutable_time_to_stale = fields.Integer(validate=marshmallow_validate.Range(min=1, max=604800))  # Max of 7 days
    immutable_time_to_stale_warning = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=15552000)
    )  # Max of 180 days
    immutable_time_to_delete = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=63072000)
    )  # Max of 2 years

    @validates_schema
    def validate_staleness(self, data, **kwargs):
        staleness_fields = ["time_to_stale", "time_to_stale_warning", "time_to_delete"]
        for host_type in (
            "conventional",
            "immutable",
        ):
            for i in range(len(staleness_fields) - 1):  # For all but the last field
                for j in range(i + 1, len(staleness_fields)):  # For all fields after that field
                    if (
                        data[(field_1 := f"{host_type}_{staleness_fields[i]}")]
                        >= data[(field_2 := f"{host_type}_{staleness_fields[j]}")]
                    ):
                        raise MarshmallowValidationError(f"{field_1} must be lower than {field_2}")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def deleted_by_this_query(model):
    # This process of checking for an already-deleted object relies
    # on checking the session after it has been updated by the commit()
    # function and marked the deleted objects as expired. It is after this
    # change that the host is called by a new query and, if deleted by a
    # different process, triggers the ObjectDeletedError and is not emitted.
    return not instance_state(model).expired
