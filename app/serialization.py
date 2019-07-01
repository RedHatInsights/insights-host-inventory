from app.models import Host as ModelsHost
from app.exceptions import InputFormatException


__all__ = ("Host", "CanonicalFacts", "Facts")


class Host:

    @classmethod
    def from_json(cls, d):
        canonical_facts = CanonicalFacts.from_json(d)
        facts = Facts.from_json(d.get("facts"))
        return ModelsHost(
            canonical_facts,
            d.get("display_name", None),
            d.get("ansible_host"),
            d.get("account"),
            facts,
            d.get("system_profile", {}),
        )

    @classmethod
    def to_json(cls, host):
        json_dict = CanonicalFacts.to_json(host.canonical_facts)
        json_dict["id"] = str(host.id)
        json_dict["account"] = host.account
        json_dict["display_name"] = host.display_name
        json_dict["ansible_host"] = host.ansible_host
        json_dict["facts"] = Facts.to_json(host.facts)
        json_dict["created"] = host.created_on.isoformat() + "Z"
        json_dict["updated"] = host.modified_on.isoformat() + "Z"
        return json_dict

    @classmethod
    def to_system_profile_json(cls, host):
        json_dict = {"id": str(host.id),
            "system_profile": host.system_profile_facts or {}
        }
        return json_dict


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
