import logging
import uuid

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, validate, validates, ValidationError
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import orm

from app.exceptions import InventoryException, InputFormatException
from app.validators import (verify_uuid_format,
                            verify_ip_address_format,
                            verify_mac_address_format)


logger = logging.getLogger(__name__)

db = SQLAlchemy()


def _set_display_name_on_save(context):
    """
    This method sets the display_name if it has not been set previously.
    This logic happens during the saving of the host record so that
    the id exists and can be used as the display_name if necessary.
    """
    params = context.get_current_parameters()
    if not params['display_name']:
        return params["canonical_facts"].get("fqdn") or params['id']


class Host(db.Model):
    __tablename__ = "hosts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    display_name = db.Column(db.String(200), default=_set_display_name_on_save)
    created_on = db.Column(db.DateTime, default=datetime.utcnow)
    modified_on = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)
    system_profile_facts = db.Column(JSONB)

    def __init__(
        self,
        canonical_facts,
        display_name=display_name,
        account=account,
        facts=None,
        system_profile_facts=None,
    ):

        if not canonical_facts:
            raise InventoryException(title="Invalid request",
                                     detail="At least one of the canonical "
                                     "fact fields must be present.")

        self.canonical_facts = canonical_facts

        if display_name:
            # Only set the display_name field if input the display_name has
            # been set...this will make it so that the "default" logic will
            # get called during the save to fill in an empty display_name
            self.display_name = display_name
        self.account = account
        self.facts = facts
        self.system_profile_facts = system_profile_facts or {}

    @classmethod
    def from_json(cls, d):
        canonical_facts = CanonicalFacts.from_json(d)
        facts = Facts.from_json(d.get("facts"))
        return cls(
            canonical_facts,
            d.get("display_name", None),
            d.get("account"),
            facts,
            d.get("system_profile", {}),
        )

    def to_json(self):
        json_dict = CanonicalFacts.to_json(self.canonical_facts)
        json_dict["id"] = str(self.id)
        json_dict["account"] = self.account
        json_dict["display_name"] = self.display_name
        json_dict["facts"] = Facts.to_json(self.facts)
        json_dict["created"] = self.created_on.isoformat()+"Z"
        json_dict["updated"] = self.modified_on.isoformat()+"Z"
        return json_dict

    def to_system_profile_json(self):
        json_dict = {"id": str(self.id),
                     "system_profile": self.system_profile_facts or {}
                     }
        return json_dict

    def save(self):
        db.session.add(self)

    def update(self, input_host):
        self.update_canonical_facts(input_host.canonical_facts)

        self.update_display_name(input_host)

        self.update_facts(input_host.facts)

        self._update_system_profile(input_host.system_profile_facts)

    def update_display_name(self, input_host):
        if input_host.display_name:
            self.display_name = input_host.display_name
        elif not self.display_name:
            # This is the case where the display_name is not set on the
            # existing host record and the input host does not have it set
            if "fqdn" in self.canonical_facts:
                self.display_name = self.canonical_facts["fqdn"]
            else:
                self.display_name = self.id

    def update_canonical_facts(self, canonical_facts):
        logger.debug(("Updating host's (id=%s) canonical_facts (%s)"
                      " with input canonical_facts=%s")
                     % (self.id, self.canonical_facts, canonical_facts))
        self.canonical_facts.update(canonical_facts)
        logger.debug("Host (id=%s) has updated canonical_facts (%s)"
                     % (self.id, self.canonical_facts))
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
        if not self.system_profile_facts:
            self.system_profile_facts = input_system_profile
        else:
            # Update the fields that were passed in
            self.system_profile_facts = {**self.system_profile_facts,
                                         **input_system_profile}
        orm.attributes.flag_modified(self, "system_profile_facts")

    def __repr__(self):
        tmpl = "<Host id='%s' account='%s' display_name='%s' canonical_facts=%s>"
        return tmpl % (
            self.id,
            self.account,
            self.display_name,
            self.canonical_facts,
        )


class CanonicalFacts:
    """
    There is a mismatch between how the canonical facts are sent as JSON
    and how the canonical facts are stored in the DB.  This class contains
    the logic that is responsible for performing the conversion.

    The canonical facts will be stored as a dict in a single json column
    in the DB.
    """

    field_names = (
        "insights_id",
        "rhel_machine_id",
        "subscription_manager_id",
        "satellite_id",
        "bios_uuid",
        "ip_addresses",
        "fqdn",
        "mac_addresses",
        "external_id",
    )

    @staticmethod
    def from_json(json_dict):
        canonical_fact_list = {}
        for cf in CanonicalFacts.field_names:
            # Do not allow the incoming canonical facts to be None or ''
            if cf in json_dict and json_dict[cf]:
                canonical_fact_list[cf] = json_dict[cf]
        return canonical_fact_list

    @staticmethod
    def to_json(internal_dict):
        canonical_fact_dict = dict.fromkeys(CanonicalFacts.field_names, None)
        for cf in CanonicalFacts.field_names:
            if cf in internal_dict:
                canonical_fact_dict[cf] = internal_dict[cf]
        return canonical_fact_dict


class Facts:
    """
    There is a mismatch between how the facts are sent as JSON
    and how the facts are stored in the DB.  This class contains
    the logic that is responsible for performing the conversion.

    The facts will be stored as a dict in a single json column
    in the DB.
    """

    @staticmethod
    def from_json(fact_list):
        if fact_list is None:
            fact_list = []

        fact_dict = {}
        for fact in fact_list:
            if "namespace" in fact and "facts" in fact:
                if fact["namespace"] in fact_dict:
                    fact_dict[fact["namespace"]].update(fact["facts"])
                else:
                    fact_dict[fact["namespace"]] = fact["facts"]
            else:
                # The facts from the request are formatted incorrectly
                raise InputFormatException("Invalid format of Fact object.  Fact "
                                           "must contain 'namespace' and 'facts' keys.")
        return fact_dict

    @staticmethod
    def to_json(fact_dict):
        fact_list = [
            {"namespace": namespace, "facts": facts if facts else {}}
            for namespace, facts in fact_dict.items()
        ]
        return fact_list


class DiskDeviceSchema(Schema):
    device = fields.Str()
    label = fields.Str()
    options = fields.Dict()
    mount_point = fields.Str()
    type = fields.Str()


class YumRepoSchema(Schema):
    name = fields.Str()
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Str()


class InstalledProductSchema(Schema):
    name = fields.Str()
    id = fields.Str()
    status = fields.Str()


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
    yum_repos = fields.List(fields.Nested(YumRepoSchema()))
    installed_products = fields.List(fields.Nested(InstalledProductSchema()))
    insights_client_version = fields.Str(validate=validate.Length(max=50))
    insights_egg_version = fields.Str(validate=validate.Length(max=50))
    installed_packages = fields.List(fields.Str())
    installed_services = fields.List(fields.Str())
    enabled_services = fields.List(fields.Str())


class FactsSchema(Schema):
    namespace = fields.Str()
    facts = fields.Dict()


class HostSchema(Schema):
    display_name = fields.Str(validate=validate.Length(min=1, max=200))
    account = fields.Str(required=True,
                         validate=validate.Length(min=1, max=10))
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_uuid_format)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    external_id = fields.Str(validate=validate.Length(min=1, max=500))
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Nested(SystemProfileSchema)

    @validates("ip_addresses")
    def validate_ip_addresses(self, ip_address_list):
        if len(ip_address_list) < 1:
            raise ValidationError("Array must contain at least one item")

        for ip_address in ip_address_list:
            if verify_ip_address_format(ip_address) is not True:
                raise ValidationError("Invalid ip address")

    @validates("mac_addresses")
    def validate_mac_addresses(self, mac_address_list):
        if len(mac_address_list) < 1:
            raise ValidationError("Array must contain at least one item")

        for mac_address in mac_address_list:
            if verify_mac_address_format(mac_address) is not True:
                raise ValidationError("Invalid mac address")

