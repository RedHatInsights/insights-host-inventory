from app.exceptions import InputFormatException
from app.models import Host as Host


__all__ = ("deserialize_host", "serialize_host", "serialize_host_system_profile", "serialize_canonical_facts")


_CANONICAL_FACTS_FIELDS = (
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


def deserialize_host(data):
    canonical_facts = _deserialize_canonical_facts(data)
    facts = _deserialize_facts(data.get("facts"))
    return Host(
        canonical_facts,
        data.get("display_name", None),
        data.get("ansible_host"),
        data.get("account"),
        facts,
        data.get("system_profile", {}),
    )


def serialize_host(host):
    json_dict = serialize_canonical_facts(host.canonical_facts)
    json_dict["id"] = str(host.id)
    json_dict["account"] = host.account
    json_dict["display_name"] = host.display_name
    json_dict["ansible_host"] = host.ansible_host
    json_dict["facts"] = _serialize_facts(host.facts)
    json_dict["created"] = host.created_on.isoformat() + "Z"
    json_dict["updated"] = host.modified_on.isoformat() + "Z"
    return json_dict


def serialize_host_system_profile(host):
    json_dict = {"id": str(host.id), "system_profile": host.system_profile_facts or {}}
    return json_dict


def _deserialize_canonical_facts(data):
    canonical_fact_list = {}
    for cf in _CANONICAL_FACTS_FIELDS:
        # Do not allow the incoming canonical facts to be None or ''
        if cf in data and data[cf]:
            canonical_fact_list[cf] = data[cf]
    return canonical_fact_list


def serialize_canonical_facts(canonical_facts):
    canonical_fact_dict = dict.fromkeys(_CANONICAL_FACTS_FIELDS, None)
    for cf in _CANONICAL_FACTS_FIELDS:
        if cf in canonical_facts:
            canonical_fact_dict[cf] = canonical_facts[cf]
    return canonical_fact_dict


def _deserialize_facts(data):
    if data is None:
        data = []

    fact_dict = {}
    for fact in data:
        if "namespace" in fact and "facts" in fact:
            if fact["namespace"] in fact_dict:
                fact_dict[fact["namespace"]].update(fact["facts"])
            else:
                fact_dict[fact["namespace"]] = fact["facts"]
        else:
            # The facts from the request are formatted incorrectly
            raise InputFormatException(
                "Invalid format of Fact object.  Fact must contain 'namespace' and 'facts' keys."
            )
    return fact_dict


def _serialize_facts(facts):
    fact_list = [{"namespace": namespace, "facts": facts if facts else {}} for namespace, facts in facts.items()]
    return fact_list
