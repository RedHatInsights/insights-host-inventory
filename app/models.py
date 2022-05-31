import uuid
from collections import namedtuple
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from enum import Enum
from os.path import join

from connexion.decorators.validation import coerce_type
from flask_sqlalchemy import SQLAlchemy
from jsonschema import draft4_format_checker
from jsonschema import RefResolver
from jsonschema import validate as jsonschema_validate
from jsonschema import ValidationError as JsonSchemaValidationError
from marshmallow import EXCLUDE
from marshmallow import fields
from marshmallow import post_load
from marshmallow import pre_load
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate
from marshmallow import validates
from marshmallow import validates_schema
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy import Index
from sqlalchemy import orm
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from yaml import safe_load

from app.exceptions import InventoryException
from app.logging import get_logger
from app.validators import check_empty_keys
from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format


logger = get_logger(__name__)

db = SQLAlchemy()

TAG_NAMESPACE_VALIDATION = marshmallow_validate.Length(max=255)
TAG_KEY_VALIDATION = marshmallow_validate.Length(min=1, max=255)
TAG_VALUE_VALIDATION = marshmallow_validate.Length(max=255)

SPECIFICATION_DIR = "./swagger/"
SYSTEM_PROFILE_SPECIFICATION_FILE = "system_profile.spec.yaml"

# set edge host stale_timestamp way out in future to Year 2260
EDGE_HOST_STALE_TIMESTAMP = datetime(2260, 1, 1, tzinfo=timezone.utc)


class ProviderType(str, Enum):
    ALIBABA = "alibaba"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    IBM = "ibm"


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


class SystemProfileNormalizer:
    class Schema(namedtuple("Schema", ("type", "properties", "items"))):
        Types = Enum("SchemaTypes", ("array", "object"))

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


class LimitedHost(db.Model):
    __tablename__ = "hosts"
    # These Index entries are essentially place holders so that the
    # alembic autogenerate functionality does not try to remove the indexes
    __table_args__ = (
        Index("idxinsightsid", text("(canonical_facts ->> 'insights_id')")),
        Index("idxgincanonicalfacts", "canonical_facts"),
        Index("idxaccount", "account"),
        Index("idxorgid", "org_id"),
        Index("hosts_subscription_manager_id_index", text("(canonical_facts ->> 'subscription_manager_id')")),
    )

    def __init__(
        self,
        canonical_facts=None,
        display_name=None,
        ansible_host=None,
        account=None,
        org_id=None,
        facts=None,
        tags={},
        system_profile_facts=None,
    ):

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
        self.system_profile_facts = system_profile_facts or {}

    def _update_ansible_host(self, ansible_host):
        if ansible_host is not None:
            # Allow a user to clear out the ansible host with an empty string
            self.ansible_host = ansible_host

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    org_id = db.Column(db.String(36))
    display_name = db.Column(db.String(200), default=_set_display_name_on_save)
    ansible_host = db.Column(db.String(255))
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)
    system_profile_facts = db.Column(JSONB)


class Host(LimitedHost):
    stale_timestamp = db.Column(db.DateTime(timezone=True))
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
        tags={},
        system_profile_facts=None,
        stale_timestamp=None,
        reporter=None,
        per_reporter_staleness=None,
    ):
        if not canonical_facts:
            raise InventoryException(
                title="Invalid request", detail="At least one of the canonical fact fields must be present."
            )

        if not stale_timestamp or not reporter:
            raise InventoryException(
                title="Invalid request", detail="Both stale_timestamp and reporter fields must be present."
            )

        if tags is None:
            raise InventoryException(title="Invalid request", detail="The tags field cannot be null.")

        super().__init__(
            canonical_facts, display_name, ansible_host, account, org_id, facts, tags, system_profile_facts
        )

        # without reporter and stale_timestamp host payload is invalid.
        self._update_stale_timestamp(stale_timestamp, reporter)

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
        self._update_per_reporter_staleness(input_host.reporter)

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

    def _update_per_reporter_staleness(self, reporter):
        if not self.per_reporter_staleness:
            self.per_reporter_staleness = {}

        if not self.per_reporter_staleness.get(reporter):
            self.per_reporter_staleness[reporter] = {}

        self.per_reporter_staleness[reporter].update(
            stale_timestamp=self.stale_timestamp.isoformat(),
            last_check_in=datetime.now(timezone.utc).isoformat(),
            check_in_succeeded=True,
        )
        orm.attributes.flag_modified(self, "per_reporter_staleness")

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

    def _replace_tags_in_namespace(self, namespace, tags):
        self.tags[namespace] = tags
        orm.attributes.flag_modified(self, "tags")

    def _delete_tags_namespace(self, namespace):
        try:
            del self.tags[namespace]
        except KeyError:
            pass

        orm.attributes.flag_modified(self, "tags")

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

    def update_system_profile(self, input_system_profile):
        logger.debug("Updating host's (id=%s) system profile", self.id)
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            # Update the fields that were passed in
            self.system_profile_facts = {**self.system_profile_facts, **input_system_profile}
        orm.attributes.flag_modified(self, "system_profile_facts")

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' org_id='{self.org_id}' display_name='{self.display_name}' "
            f"canonical_facts={self.canonical_facts}>"
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
    def validate_provider(self, data, **kwargs):
        provider_type = data.get("provider_type")
        provider_id = data.get("provider_id")

        if (provider_type and not provider_id) or (provider_id and not provider_type):
            raise MarshmallowValidationError("provider_type and provider_id are both required.")

        if provider_type and provider_type.lower() not in ProviderType.__members__.values():
            raise MarshmallowValidationError(
                f'Unknown Provider Type: "{provider_type}".  '
                f'Valid provider types are: {", ".join([p.value for p in ProviderType])}.'
            )

        # check for white spaces, tabs, and newline characters only
        if provider_id and provider_id.isspace():
            raise MarshmallowValidationError("Provider id can not be just blank, whitespaces or tabs")


class LimitedHostSchema(CanonicalFactsSchema):
    class Meta:
        unknown = EXCLUDE

    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    account = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=10))
    org_id = fields.Str(validate=marshmallow_validate.Length(min=0, max=36))
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Dict()
    tags = fields.Raw()

    def __init__(self, system_profile_schema=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = type(self)
        if not hasattr(cls, "system_profile_normalizer"):
            cls.system_profile_normalizer = SystemProfileNormalizer()
        if system_profile_schema:
            self.system_profile_normalizer = SystemProfileNormalizer(system_profile_schema=system_profile_schema)

    @validates("tags")
    def validate_tags(self, tags):
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
    def build_model(data, canonical_facts, facts, tags):
        return LimitedHost(
            canonical_facts=canonical_facts,
            display_name=data.get("display_name"),
            ansible_host=data.get("ansible_host"),
            account=data.get("account"),
            org_id=data.get("org_id"),
            facts=facts,
            tags=tags,
            system_profile_facts=data.get("system_profile", {}),
        )

    @pre_load
    def coerce_system_profile_types(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.coerce_types, data)

    @post_load
    def filter_system_profile_keys(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.filter_keys, data)

    @validates("system_profile")
    def system_profile_is_valid(self, system_profile):
        try:
            jsonschema_validate(
                system_profile, self.system_profile_normalizer.schema, format_checker=draft4_format_checker
            )
        except JsonSchemaValidationError as error:
            raise MarshmallowValidationError(f"System profile does not conform to schema.\n{error}") from error

        for dd_i, disk_device in enumerate(system_profile.get("disk_devices", [])):
            if not check_empty_keys(disk_device.get("options")):
                raise MarshmallowValidationError(f"Empty key in /system_profile/disk_devices/{dd_i}/options.")


class HostSchema(LimitedHostSchema):
    class Meta:
        unknown = EXCLUDE

    stale_timestamp = fields.DateTime(required=True, timezone=True)
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))

    @staticmethod
    def build_model(data, canonical_facts, facts, tags):
        return Host(
            canonical_facts,
            data.get("display_name"),
            data.get("ansible_host"),
            data.get("account"),
            data.get("org_id"),
            facts,
            tags,
            data.get("system_profile", {}),
            data["stale_timestamp"],
            data["reporter"],
        )

    @validates("stale_timestamp")
    def has_timezone_info(self, timestamp):
        if timestamp.tzinfo is None:
            raise MarshmallowValidationError("Timestamp must contain timezone info")


class PatchHostSchema(MarshmallowSchema):
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
