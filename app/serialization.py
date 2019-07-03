from collections import defaultdict

from app.exceptions import InputFormatException
from app.models import Host as Host


__all__ = ("deserialize_host", "serialize_host", "serialize_host_system_profile")


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


def _serialize_datetime(dt):
    return dt.isoformat() + "Z"


def _serialize_uuid(u):
    return str(u)


def deserialize_host(data):
    return Host(
        _deserialize_canonical_facts(data),
        data.get("display_name"),
        data.get("ansible_host"),
        data.get("account"),
        _deserialize_facts(data.get("facts")),
        data.get("system_profile"),
    )


def serialize_host(host):
    return {
        **_serialize_canonical_facts(host.canonical_facts),
        "id": _serialize_uuid(host.id),
        "account": host.account,
        "display_name": host.display_name,
        "ansible_host": host.ansible_host,
        "facts": _serialize_facts(host.facts),
        "created": _serialize_datetime(host.created_on),
        "updated": _serialize_datetime(host.modified_on),
    }


def serialize_host_system_profile(host):
    return {"id": _serialize_uuid(host.id), "system_profile": host.system_profile_facts}


def _deserialize_canonical_facts(data):
    return {field: data[field] for field in _CANONICAL_FACTS_FIELDS if data.get(field)}


def _serialize_canonical_facts(canonical_facts):
    return {field: canonical_facts.get(field) for field in _CANONICAL_FACTS_FIELDS}


def _deserialize_facts(data):
    facts = defaultdict(lambda: {})
    for item in data or []:
        try:
            old_facts = facts[item["namespace"]]
            new_facts = item["facts"] or {}
            facts[item["namespace"]] = {**old_facts, **new_facts}
        except KeyError:
            # The facts from the request are formatted incorrectly
            raise InputFormatException(
                "Invalid format of Fact object.  Fact must contain 'namespace' and 'facts' keys."
            )
    return facts


def _serialize_facts(facts):
    return [{"namespace": namespace, "facts": facts} for namespace, facts in facts.items()]
