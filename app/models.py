import uuid
from contextlib import contextmanager
from datetime import datetime

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
from app.validators import verify_uuid_format


logger = get_logger(__name__)

db = SQLAlchemy()


@contextmanager
def db_session_guard():
    session = db.session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.remove()


def _set_display_name_on_save(context):
    """
    This method sets the display_name if it has not been set previously.
    This logic happens during the saving of the host record so that
    the id exists and can be used as the display_name if necessary.
    """
    params = context.get_current_parameters()
    if not params["display_name"]:
        return params["canonical_facts"].get("fqdn") or params["id"]


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
    created_on = db.Column(db.DateTime, default=datetime.utcnow)
    modified_on = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)
    system_profile_facts = db.Column(JSONB)

    def __init__(
        self,
        canonical_facts,
        display_name=None,
        ansible_host=None,
        account=None,
        facts=None,
        system_profile_facts=None,
    ):

        if not canonical_facts:
            raise InventoryException(
                title="Invalid request", detail="At least one of the canonical fact fields must be present."
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
        self.system_profile_facts = system_profile_facts or {}

    def save(self):
        db.session.add(self)

    def update(self, input_host, update_system_profile=False):
        self.update_canonical_facts(input_host.canonical_facts)

        self.update_display_name(input_host.display_name)

        self._update_ansible_host(input_host.ansible_host)

        self.update_facts(input_host.facts)

        if update_system_profile:
            self._update_system_profile(input_host.system_profile_facts)

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

    def replace_facts_in_namespace(self, namespace, facts_dict):
        self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

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

    def __repr__(self):
        return (
            f"<Host id='{self.id}' account='{self.account}' display_name='{self.display_name}' "
            f"canonical_facts={self.canonical_facts}>"
        )


class DiskDeviceSchema(Schema):
    device = fields.Str(validate=validate.Length(max=2048))
    label = fields.Str(validate=validate.Length(max=1024))
    options = fields.Dict()
    mount_point = fields.Str(validate=validate.Length(max=2048))
    type = fields.Str(validate=validate.Length(max=256))


class YumRepoSchema(Schema):
    name = fields.Str(validate=validate.Length(max=1024))
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Str(validate=validate.Length(max=2048))


class InstalledProductSchema(Schema):
    name = fields.Str(validate=validate.Length(max=512))
    id = fields.Str(validate=validate.Length(max=64))
    status = fields.Str(validate=validate.Length(max=256))


class NetworkInterfaceSchema(Schema):
    ipv4_addresses = fields.List(fields.Str())
    ipv6_addresses = fields.List(fields.Str())
    state = fields.Str(validate=validate.Length(max=25))
    mtu = fields.Int()
    mac_address = fields.Str(validate=validate.Length(max=18))
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
    installed_products = fields.List(fields.Nested(InstalledProductSchema()))
    insights_client_version = fields.Str(validate=validate.Length(max=50))
    insights_egg_version = fields.Str(validate=validate.Length(max=50))
    installed_packages = fields.List(fields.Str(validate=validate.Length(max=512)))
    installed_services = fields.List(fields.Str(validate=validate.Length(max=512)))
    enabled_services = fields.List(fields.Str(validate=validate.Length(max=512)))


class FactsSchema(Schema):
    namespace = fields.Str()
    facts = fields.Dict()


class HostSchema(Schema):
    display_name = fields.Str(validate=validate.Length(min=1, max=200))
    ansible_host = fields.Str(validate=validate.Length(min=0, max=255))
    account = fields.Str(required=True, validate=validate.Length(min=1, max=10))
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_uuid_format)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    mac_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    external_id = fields.Str(validate=validate.Length(min=1, max=500))
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Nested(SystemProfileSchema)

    @validates("ip_addresses")
    def validate_ip_addresses(self, ip_address_list):
        if len(ip_address_list) < 1:
            raise ValidationError("Array must contain at least one item")

    @validates("mac_addresses")
    def validate_mac_addresses(self, mac_address_list):
        if len(mac_address_list) < 1:
            raise ValidationError("Array must contain at least one item")


class PatchHostSchema(Schema):
    ansible_host = fields.Str(validate=validate.Length(min=0, max=255))
    display_name = fields.Str(validate=validate.Length(min=1, max=200))
