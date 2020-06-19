import uuid
from datetime import datetime
from datetime import timezone

from flask_sqlalchemy import SQLAlchemy
from marshmallow import fields
from marshmallow import Schema
from marshmallow import validate
from marshmallow import validates
from marshmallow import ValidationError
from sqlalchemy import Index
from sqlalchemy import orm
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

from app.exceptions import InventoryException
from app.logging import get_logger
from app.validators import check_empty_keys
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format


logger = get_logger(__name__)

db = SQLAlchemy()

TAG_NAMESPACE_VALIDATION = validate.Length(max=255)
TAG_KEY_VALIDATION = validate.Length(min=1, max=255)
TAG_VALUE_VALIDATION = validate.Length(max=255)


def _set_display_name_on_save(context):
    """
    This method sets the display_name if it has not been set previously.
    This logic happens during the saving of the host record so that
    the id exists and can be used as the display_name if necessary.
    """
    params = context.get_current_parameters()
    if not params["display_name"]:
        return params["canonical_facts"].get("fqdn") or params["id"]


def _time_now():
    return datetime.now(timezone.utc)


class Host(db.Model):
    __tablename__ = "hosts"
    # These Index entries are essentially place holders so that the
    # alembic autogenerate functionality does not try to remove the indexes
    __table_args__ = (
        Index("idxinsightsid", text("(canonical_facts ->> 'insights_id')")),
        Index("idxgincanonicalfacts", "canonical_facts"),
        Index("idxaccount", "account"),
        Index("hosts_subscription_manager_id_index", text("(canonical_facts ->> 'subscription_manager_id')")),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    display_name = db.Column(db.String(200), default=_set_display_name_on_save)
    ansible_host = db.Column(db.String(255))
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)
    system_profile_facts = db.Column(JSONB)
    stale_timestamp = db.Column(db.DateTime(timezone=True))
    reporter = db.Column(db.String(255))

    def __init__(
        self,
        canonical_facts,
        display_name=None,
        ansible_host=None,
        account=None,
        facts=None,
        tags=None,
        system_profile_facts=None,
        stale_timestamp=None,
        reporter=None,
    ):

        if not canonical_facts:
            raise InventoryException(
                title="Invalid request", detail="At least one of the canonical fact fields must be present."
            )

        if (not stale_timestamp and reporter) or (stale_timestamp and not reporter):
            raise InventoryException(
                title="Invalid request", detail="Both stale_timestamp and reporter fields must be present."
            )

        self.canonical_facts = canonical_facts

        if display_name:
            # Only set the display_name field if input the display_name has
            # been set...this will make it so that the "default" logic will
            # get called during the save to fill in an empty display_name
            self.display_name = display_name
        self._update_ansible_host(ansible_host)
        self.account = account
        self.facts = facts
        self.tags = tags or {}
        self.system_profile_facts = system_profile_facts or {}
        self.stale_timestamp = stale_timestamp
        self.reporter = reporter

    def save(self):
        self._cleanup_tags()
        db.session.add(self)

    def update(self, input_host, update_system_profile=False):
        self.update_canonical_facts(input_host.canonical_facts)

        # TODO: Remove this eventually when Sat 6.7 stops sending fqdns as display_names (See RHCLOUD-5954)
        # NOTE: For this particular issue, display_name changes from "puptoo" and "yupana" are ignored
        if input_host.reporter != "yupana" and input_host.reporter != "rhsm-conduit":
            self.update_display_name(input_host.display_name)

        self._update_ansible_host(input_host.ansible_host)

        self.update_facts(input_host.facts)

        self._update_tags(input_host.tags)

        if update_system_profile:
            self._update_system_profile(input_host.system_profile_facts)

        self._update_stale_timestamp(input_host.stale_timestamp, input_host.reporter)

    def patch(self, patch_data):
        logger.debug("patching host (id=%s) with data: %s", self.id, patch_data)

        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        self._update_ansible_host(patch_data.get("ansible_host"))

        self.update_display_name(patch_data.get("display_name"))

    def _update_ansible_host(self, ansible_host):
        if ansible_host is not None:
            # Allow a user to clear out the ansible host with an empty string
            self.ansible_host = ansible_host

    def update_display_name(self, input_display_name):
        if input_display_name:
            self.display_name = input_display_name
        elif not self.display_name:
            # This is the case where the display_name is not set on the
            # existing host record and the input host does not have it set
            if "fqdn" in self.canonical_facts:
                self.display_name = self.canonical_facts["fqdn"]
            else:
                self.display_name = self.id

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
        if (
            stale_timestamp
            and reporter
            and (
                (not self.reporter and not self.stale_timestamp)
                or (reporter == self.reporter and stale_timestamp >= self.stale_timestamp)
                or (reporter != self.reporter and stale_timestamp <= self.stale_timestamp)
                or (self.stale_timestamp < _time_now())
            )
        ):
            self.stale_timestamp = stale_timestamp
            self.reporter = reporter

    def replace_facts_in_namespace(self, namespace, facts_dict):
        self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

    def _update_tags(self, tags_dict):
        if not self.tags:  # fixme: Host tags should never be None, in DB neither NULL nor 'null'
            self.tags = {}

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

    def _update_system_profile(self, input_system_profile):
        logger.debug("Updating host's (id=%s) system profile", self.id)
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            # Update the fields that were passed in
            self.system_profile_facts = {**self.system_profile_facts, **input_system_profile}
        orm.attributes.flag_modified(self, "system_profile_facts")

    def registered_with_insights(self):
        return "insights_id" in self.canonical_facts

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' display_name='{self.display_name}' "
            f"canonical_facts={self.canonical_facts}>"
        )


class DiskDeviceSchema(Schema):
    device = fields.Str(validate=validate.Length(max=2048))
    label = fields.Str(validate=validate.Length(max=1024))
    options = fields.Dict(validate=check_empty_keys)
    mount_point = fields.Str(validate=validate.Length(max=2048))
    type = fields.Str(validate=validate.Length(max=256))


class YumRepoSchema(Schema):
    id = fields.Str(validate=validate.Length(max=256))
    name = fields.Str(validate=validate.Length(max=1024))
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Str(validate=validate.Length(max=2048))


class DnfModuleSchema(Schema):
    name = fields.Str(validate=validate.Length(max=128))
    stream = fields.Str(validate=validate.Length(max=128))


class InstalledProductSchema(Schema):
    name = fields.Str(validate=validate.Length(max=512))
    id = fields.Str(validate=validate.Length(max=64))
    status = fields.Str(validate=validate.Length(max=256))


class NetworkInterfaceSchema(Schema):
    ipv4_addresses = fields.List(fields.Str())
    ipv6_addresses = fields.List(fields.Str())
    state = fields.Str(validate=validate.Length(max=25))
    mtu = fields.Int()
    mac_address = fields.Str(validate=validate.Length(max=59))
    name = fields.Str(validate=validate.Length(min=1, max=50))
    type = fields.Str(validate=validate.Length(max=18))


class SystemProfileSchema(Schema):
    number_of_cpus = fields.Int()
    number_of_sockets = fields.Int()
    cores_per_socket = fields.Int()
    system_memory_bytes = fields.Int()
    infrastructure_type = fields.Str(validate=validate.Length(max=100))
    infrastructure_vendor = fields.Str(validate=validate.Length(max=100))
    network_interfaces = fields.List(fields.Nested(NetworkInterfaceSchema()))
    disk_devices = fields.List(fields.Nested(DiskDeviceSchema()))
    bios_vendor = fields.Str(validate=validate.Length(max=100))
    bios_version = fields.Str(validate=validate.Length(max=100))
    bios_release_date = fields.Str(validate=validate.Length(max=50))
    cpu_flags = fields.List(fields.Str(validate=validate.Length(max=30)))
    os_release = fields.Str(validate=validate.Length(max=100))
    os_kernel_version = fields.Str(validate=validate.Length(max=100))
    arch = fields.Str(validate=validate.Length(max=50))
    kernel_modules = fields.List(fields.Str(validate=validate.Length(max=255)))
    last_boot_time = fields.Str(validate=validate.Length(max=50))
    running_processes = fields.List(fields.Str(validate=validate.Length(max=1000)))
    subscription_status = fields.Str(validate=validate.Length(max=100))
    subscription_auto_attach = fields.Str(validate=validate.Length(max=100))
    katello_agent_running = fields.Bool()
    satellite_managed = fields.Bool()
    cloud_provider = fields.Str(validate=validate.Length(max=100))
    yum_repos = fields.List(fields.Nested(YumRepoSchema()))
    dnf_modules = fields.List(fields.Nested(DnfModuleSchema()))
    installed_products = fields.List(fields.Nested(InstalledProductSchema()))
    insights_client_version = fields.Str(validate=validate.Length(max=50))
    insights_egg_version = fields.Str(validate=validate.Length(max=50))
    captured_date = fields.Str(validate=validate.Length(max=32))
    installed_packages = fields.List(fields.Str(validate=validate.Length(max=512)))
    installed_services = fields.List(fields.Str(validate=validate.Length(max=512)))
    enabled_services = fields.List(fields.Str(validate=validate.Length(max=512)))


class FactsSchema(Schema):
    namespace = fields.Str()
    facts = fields.Dict(validate=check_empty_keys)


class TagsSchema(Schema):
    namespace = fields.Str(required=False, allow_none=True, validate=TAG_NAMESPACE_VALIDATION)
    key = fields.Str(required=True, allow_none=False, validate=TAG_KEY_VALIDATION)
    value = fields.Str(required=False, allow_none=True, validate=TAG_VALUE_VALIDATION)


class HostSchema(Schema):
    display_name = fields.Str(validate=validate.Length(min=1, max=200))
    ansible_host = fields.Str(validate=validate.Length(min=0, max=255))
    account = fields.Str(required=True, validate=validate.Length(min=1, max=10))
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_satellite_id)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)), validate=validate.Length(min=1))
    mac_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=59)), validate=validate.Length(min=1))
    external_id = fields.Str(validate=validate.Length(min=1, max=500))
    facts = fields.List(fields.Nested(FactsSchema))
    tags = fields.Raw(allow_none=True)
    system_profile = fields.Nested(SystemProfileSchema)
    stale_timestamp = fields.DateTime(required=True, timezone=True)
    reporter = fields.Str(required=True, validate=validate.Length(min=1, max=255))

    @validates("stale_timestamp")
    def has_timezone_info(self, timestamp):
        if timestamp.tzinfo is None:
            raise ValidationError("Timestamp must contain timezone info")

    @validates("tags")
    def validate_tags(self, tags):
        if isinstance(tags, list):
            return self._validate_tags_list(tags)
        elif isinstance(tags, dict):
            return self._validate_tags_dict(tags)
        elif tags is None:
            return True
        else:
            raise ValidationError("Tags must be either an object, an array or null.")

    @staticmethod
    def _validate_tags_list(tags):
        TagsSchema(many=True, strict=True).validate(tags)
        return True

    @staticmethod
    def _validate_tags_dict(tags):
        for namespace, ns_tags in tags.items():
            TAG_NAMESPACE_VALIDATION(namespace)
            if ns_tags is None:
                continue
            if not isinstance(ns_tags, dict):
                raise ValidationError("Tags in a namespace must be an object or null.")

            for key, values in ns_tags.items():
                TAG_KEY_VALIDATION(key)
                if values is None:
                    continue
                if not isinstance(values, list):
                    raise ValidationError("Tag values must be an array or null.")

                for value in values:
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise ValidationError("Tag value must be a string or null.")
                    TAG_VALUE_VALIDATION(value)

        return True


class PatchHostSchema(Schema):
    ansible_host = fields.Str(validate=validate.Length(min=0, max=255))
    display_name = fields.Str(validate=validate.Length(min=1, max=200))
