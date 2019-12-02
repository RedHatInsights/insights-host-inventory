from datetime import timezone

from marshmallow import ValidationError

from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import Host as Host
from app.models import HostSchema
from app.utils import Tag


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


def deserialize_host(raw_data):
    try:
        validated_data = HostSchema(strict=True).load(raw_data).data
    except ValidationError as e:
        raise ValidationException(str(e.messages)) from None

    canonical_facts = _deserialize_canonical_facts(validated_data)
    facts = _deserialize_facts(validated_data.get("facts"))
    tags = _deserialize_tags(validated_data.get("tags"))
    return Host(
        canonical_facts,
        validated_data.get("display_name"),
        validated_data.get("ansible_host"),
        validated_data.get("account"),
        facts,
        tags,
        validated_data.get("system_profile", {}),
        validated_data.get("stale_timestamp"),
        validated_data.get("reporter"),
    )


def serialize_host(host, staleness_offset):
    if host.stale_timestamp:
        stale_timestamp = staleness_offset.stale_timestamp(host.stale_timestamp)
        stale_warning_timestamp = staleness_offset.stale_warning_timestamp(host.stale_timestamp)
        culled_timestamp = staleness_offset.culled_timestamp(host.stale_timestamp)
    else:
        stale_timestamp = None
        stale_warning_timestamp = None
        culled_timestamp = None

    return {
        **serialize_canonical_facts(host.canonical_facts),
        "id": _serialize_uuid(host.id),
        "account": host.account,
        "display_name": host.display_name,
        "ansible_host": host.ansible_host,
        "facts": _serialize_facts(host.facts),
        "reporter": host.reporter,
        "stale_timestamp": stale_timestamp and _serialize_datetime(stale_timestamp),
        "stale_warning_timestamp": stale_timestamp and _serialize_datetime(stale_warning_timestamp),
        "culled_timestamp": stale_timestamp and _serialize_datetime(culled_timestamp),
        # without astimezone(timezone.utc) the isoformat() method does not include timezone offset even though iso-8601
        # requires it
        "created": _serialize_datetime(host.created_on),
        "updated": _serialize_datetime(host.modified_on),
    }


def serialize_host_system_profile(host):
    return {"id": _serialize_uuid(host.id), "system_profile": host.system_profile_facts or {}}


def _deserialize_canonical_facts(data):
    return {field: data[field] for field in _CANONICAL_FACTS_FIELDS if data.get(field)}


def serialize_canonical_facts(canonical_facts):
    return {field: canonical_facts.get(field) for field in _CANONICAL_FACTS_FIELDS}


def _deserialize_facts(data):
    facts = {}
    for fact in [] if data is None else data:
        try:
            if fact["namespace"] in facts:
                facts[fact["namespace"]].update(fact["facts"])
            else:
                facts[fact["namespace"]] = fact["facts"]
        except KeyError:
            # The facts from the request are formatted incorrectly
            raise InputFormatException(
                "Invalid format of Fact object.  Fact must contain 'namespace' and 'facts' keys."
            )
    return facts


def _serialize_facts(facts):
    return [{"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()]


def _serialize_datetime(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _serialize_uuid(u):
    return str(u)


def _deserialize_tags(tags):
    # TODO: Move the deserialization logic to this method.
    return Tag.create_nested_from_tags(Tag.create_structered_tags_from_tag_data_list(tags))
