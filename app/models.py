import logging
import uuid

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, validate, validates, ValidationError, post_load
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import orm

from api.json_validators import verify_uuid_format
from app.exceptions import InputFormatException


logger = logging.getLogger(__name__)

db = SQLAlchemy()


CANONICAL_FACTS = (
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


def load_host_from_json_dict(host_dict):
    host, error = HostSchema().load(host_dict)
    if error:
        print("error:", error)
        raise InputFormatException("Host parsing error: %s" % error)
    return host


def _load_system_profile_data_from_json_dict(json_dict):
    # Marshmallow ignores data that does not match the schema.
    # This allow us to pick out _only_ the system profile data and
    # shove it into system_profile_facts column.
    (data, error) = SystemProfileSchema().load(json_dict)
    if error:
        raise InputFormatException("system_profile parsing error: %s" % error)
    return data


def convert_fields_to_canonical_facts(json_dict):
    canonical_fact_list = {}
    for cf in CANONICAL_FACTS:
        # Do not allow the incoming canonical facts to be None or ''
        if cf in json_dict and json_dict[cf]:
            canonical_fact_list[cf] = json_dict[cf]
    return canonical_fact_list


def convert_canonical_facts_to_fields(internal_dict):
    canonical_fact_dict = dict.fromkeys(CANONICAL_FACTS, None)
    for cf in CANONICAL_FACTS:
        if cf in internal_dict:
            canonical_fact_dict[cf] = internal_dict[cf]
    return canonical_fact_dict


def convert_json_facts_to_dict(fact_list):
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


def convert_dict_to_json_facts(fact_dict):
    fact_list = [
        {"namespace": namespace, "facts": facts if facts else {}}
        for namespace, facts in fact_dict.items()
    ]
    return fact_list


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
        return cls(
            # Internally store the canonical facts as a dict
            convert_fields_to_canonical_facts(d),
            d.get("display_name", None),
            d.get("account"),
            # Internally store the facts in a dict
            convert_json_facts_to_dict(d.get("facts", [])),
            _load_system_profile_data_from_json_dict(d.get("system_profile",
                                                           {})),
        )

    def to_json(self):
        json_dict = convert_canonical_facts_to_fields(self.canonical_facts)
        json_dict["id"] = self.id
        json_dict["account"] = self.account
        json_dict["display_name"] = self.display_name
        # Internally store the facts in a dict
        json_dict["facts"] = convert_dict_to_json_facts(self.facts)
        json_dict["created"] = self.created_on
        json_dict["updated"] = self.modified_on
        return json_dict

    def to_system_profile_json(self):
        json_dict = {"id": self.id,
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
    base_url = fields.Url()


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
    external_id = fields.Str()
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Nested(SystemProfileSchema)

    def process_facts(self, data):
        print("HERE - pre_load")
        fact_dict = {}
        fact_list = data.get("facts", [])
        for fact in fact_list:
            print("fact", fact)
            if "namespace" in fact and "facts" in fact:
                if fact["namespace"] in fact_dict:
                    fact_dict[fact["namespace"]].update(fact["facts"])
                else:
                    fact_dict[fact["namespace"]] = fact["facts"]
            else:
                # The facts from the request are formatted incorrectly
                raise ValidationError("Invalid format of Fact object.  Fact "
                                      "must contain 'namespace' and 'facts' keys.")
        data["facts"] = fact_dict
        print("fact_dict", fact_dict)
        return data

    @post_load
    def make_host(self, data):
        print("HERE - post_load")
        print("data:", data)
        self.process_facts(data)

        cf_fields = convert_fields_to_canonical_facts(data)
        print("cf_fields:", cf_fields)
        return Host(cf_fields,
                    data.get("display_name"),
                    data.get("account"),
                    data.get("facts"),
                    data.get("system_profile"))

    @validates("ip_addresses")
    def validate_ip_addresses(self, value):
        if len(value) < 1:
            raise ValidationError("Array must contain at least one item")

    @validates("mac_addresses")
    def validate_mac_addresses(self, value):
        if len(value) < 1:
            raise ValidationError("Array must contain at least one item")
