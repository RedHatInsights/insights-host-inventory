import uuid

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import orm

from app.exceptions import InputFormatException


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

SYSTEM_PROFILE_FIELDS = (
    "number_of_cpus",
    "number_of_sockets",
    "cores_per_socket",
    "system_memory",
    "infrastructure_type",
    "infrastructure_vendor",
    "serial_number",
    "ipv4_addresses",
    "ipv6_addresses",
    "mac_addresses",
    "network_interfaces",
    "disk_devices",
    "bios_vendor",
    "bios_version",
    "bios_release_date",
    "bios_compatible_support_modules",
    "os_release",
    "os_kernel_version",
    "arch",
    "kernel_modules",
    "last_boot_time",
    "running_processes",
    "subscription_status",
    "subscription_auto_attach",
    "katello_agent_running",
    "satellite_managed",
    "rpm_repos_enabled",
    "installed_products",
    "insights_client_version",
    "insights_egg_version",
    "installed_packages",
    "installed_services",
    "enabled_services",
)


def output_host_with_system_profile(host):
    return {"id": host.id,
            "system_profile": convert_db_fields_to_json_fields(
                SYSTEM_PROFILE_FIELDS,
                host.system_profile_facts
                ),
            }


def convert_json_fields_to_db_fields(db_field_list, json_dict):
    db_dict = {db_field_name: json_dict[db_field_name]
               for db_field_name in db_field_list
                   if db_field_name in json_dict and json_dict[db_field_name]}
    return db_dict


def convert_db_fields_to_json_fields(db_field_list, db_dict):
    json_dict = dict.fromkeys(db_field_list, None)
    for db_field_name in db_field_list:
        if db_field_name in db_dict:
            json_dict[db_field_name] = db_dict[db_field_name]
    return json_dict


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
        self.system_profile_facts = system_profile_facts

    @classmethod
    def from_json(cls, d):
        return cls(
            # Internally store the canonical facts as a dict
            convert_fields_to_canonical_facts(d),
            d.get("display_name", None),
            d.get("account"),
            # Internally store the facts in a dict
            convert_json_facts_to_dict(d.get("facts", [])),
            convert_json_fields_to_db_fields(SYSTEM_PROFILE_FIELDS,
                                             d.get("system_profile", {})),
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

    def save(self):
        db.session.add(self)

    def update(self, input_host):
        self.update_canonical_facts(input_host.canonical_facts)

        self.update_display_name(input_host)

        self.update_facts(input_host.facts)

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
        self.canonical_facts.update(canonical_facts)
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

    def __repr__(self):
        tmpl = "<Host '%s' '%s' canonical_facts=%s facts=%s>"
        return tmpl % (
            self.display_name,
            self.id,
            self.canonical_facts,
            self.facts,
        )
