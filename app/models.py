from app import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import orm

import uuid


CANONICAL_FACTS = ("insights_id",
                   "rhel_machine_id",
                   "subscription_manager_id",
                   "satellite_id",
                   "bios_uuid",
                   "ip_addresses",
                   "fqdn",
                   "mac_addresses")


def convert_fields_to_canonical_facts(json_dict):
    canonical_fact_list = {}
    for cf in CANONICAL_FACTS:
        if cf in json_dict:
            canonical_fact_list[cf] = json_dict[cf]
    return canonical_fact_list


def convert_canonical_facts_to_fields(internal_dict):
    canonical_fact_dict = dict.fromkeys(CANONICAL_FACTS, None)
    for cf in CANONICAL_FACTS:
        if cf in internal_dict:
            canonical_fact_dict[cf] = internal_dict[cf]
    return canonical_fact_dict


def convert_json_facts_to_dict(fact_list):
    # print("** convert_json_facts_to_dict")
    # print("** fact_list:", fact_list)
    fact_dict = {}
    for fact in fact_list:
        # print("** fact:", fact)
        if fact["namespace"] in fact_dict:
            fact_dict[fact["namespace"]].update(fact["facts"])
        else:
            fact_dict[fact["namespace"]] = fact["facts"]
    # print("** fact_dict:", fact_dict)
    return fact_dict


def convert_dict_to_json_facts(fact_dict):
    # print("** convert_dict_to_json_facts")
    # print("** fact_dict:", fact_dict)
    fact_list = [
        {"namespace": namespace, "facts": facts}
        for namespace, facts in fact_dict.items()
    ]
    # print("** fact_list:", fact_list)
    return fact_list


class Host(db.Model):
    __tablename__ = 'hosts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    display_name = db.Column(db.String(200))
    created_on = db.Column(db.DateTime, default=datetime.utcnow)
    modified_on = db.Column(db.DateTime,
                            default=datetime.utcnow,
                            onupdate=datetime.utcnow)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)

    def __init__(
        self,
        canonical_facts,
        display_name=display_name,
        account=account,
        tags=None,
        facts=None,
    ):
        self.canonical_facts = canonical_facts
        self.display_name = display_name
        self.account = account
        self.tags = tags
        self.facts = facts

    @classmethod
    def from_json(cls, d):
        return cls(
            # Internally store the canonical facts as a dict
            convert_fields_to_canonical_facts(d),
            d.get("display_name", None),
            d.get("account"),
            d.get("tags", []),
            # Internally store the facts in a dict
            convert_json_facts_to_dict(d.get("facts", [])),
        )

    def to_json(self):
        json_dict = convert_canonical_facts_to_fields(self.canonical_facts)
        json_dict["id"] = self.id
        json_dict["account"] = self.account
        json_dict["display_name"] = self.display_name
        json_dict["tags"] = self.tags
        # Internally store the facts in a dict
        json_dict["facts"] = convert_dict_to_json_facts(self.facts)
        json_dict["created"] = self.created_on
        json_dict["updated"] = self.modified_on
        return json_dict

    def update(self, input_host):

        self.update_canonical_facts(input_host.canonical_facts)

        self.update_display_name(input_host.display_name)

        self.update_facts(input_host.facts)

        self.update_tags(input_host.tags)

        db.session.commit()

    def update_display_name(self, display_name):
        if display_name:
            self.display_name = display_name

    def update_canonical_facts(self, canonical_facts):
        # FIXME: make sure new canonical facts are added
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
        if self.facts[namespace]:
            self.facts[namespace] = {**self.facts[namespace], **facts_dict}
        else:
            # The value currently stored in the namespace is None so replace it
            self.facts[namespace] = facts_dict
        orm.attributes.flag_modified(self, "facts")

    def update_tags(self, tags):
        if tags:
            # FIXME: think about storing tags as a dict internally
            self.tags.extend(tags)
            orm.attributes.flag_modified(self, "tags")

    def add_tag(self, tag):
        if tag:
            # FIXME: think about storing tags as a dict internally
            if tag not in self.tags:
                self.tags.append(tag)
                orm.attributes.flag_modified(self, "tags")

    def remove_tag(self, tag):
        if tag:
            # FIXME: think about storing tags as a dict internally
            if tag in self.tags:
                self.tags.remove(tag)
                orm.attributes.flag_modified(self, "tags")

    def save(self):
        db.session.add(self)
        db.session.commit()

    def __repr__(self):
        tmpl = "<Host '%s' '%d' canonical_facts=%s facts=%s tags=%s>"
        return tmpl % (
            self.display_name, self.id, self.canonical_facts, self.facts, self.tags
        )
