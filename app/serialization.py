from datetime import timezone

from dateutil.parser import isoparse
from marshmallow import ValidationError

from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import CanonicalFactsSchema
from app.models import Host as Host
from app.models import MqHostSchema
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

DEFAULT_FIELDS = (
    "id",
    "account",
    "display_name",
    "ansible_host",
    "facts",
    "reporter",
    "stale_timestamp",
    "stale_warning_timestamp",
    "culled_timestamp",
    "created",
    "updated",
)


def deserialize_host(raw_data, schema):
    try:
        validated_data = schema(strict=True).load(raw_data).data
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
        validated_data["stale_timestamp"],
        validated_data["reporter"],
    )


def deserialize_host_mq(raw_data):
    return deserialize_host(raw_data, MqHostSchema)


def deserialize_canonical_facts(raw_data):
    try:
        validated_data = CanonicalFactsSchema(strict=True).load(raw_data).data
    except ValidationError as e:
        raise ValidationException(str(e.messages)) from None
    return _deserialize_canonical_facts(validated_data)


def deserialize_host_xjoin(data):
    host = Host(
        canonical_facts=data["canonical_facts"],
        display_name=data["display_name"],
        ansible_host=data["ansible_host"],
        account=data["account"],
        facts=data["facts"] or {},
        tags={},  # Not a part of host list output
        system_profile_facts={},  # Not a part of host list output
        stale_timestamp=_deserialize_datetime(data["stale_timestamp"]),
        reporter=data["reporter"],
    )
    for field in ("created_on", "modified_on"):
        setattr(host, field, _deserialize_datetime(data[field]))
    host.id = data["id"]
    return host


def serialize_host(host, staleness_timestamps, fields=DEFAULT_FIELDS):
    if host.stale_timestamp:
        stale_timestamp = staleness_timestamps.stale_timestamp(host.stale_timestamp)
        stale_warning_timestamp = staleness_timestamps.stale_warning_timestamp(host.stale_timestamp)
        culled_timestamp = staleness_timestamps.culled_timestamp(host.stale_timestamp)
    else:
        stale_timestamp = None
        stale_warning_timestamp = None
        culled_timestamp = None

    serialized_host = {**serialize_canonical_facts(host.canonical_facts)}

    if "id" in fields:
        serialized_host["id"] = _serialize_uuid(host.id)
    if "account" in fields:
        serialized_host["account"] = host.account
    if "display_name" in fields:
        serialized_host["display_name"] = host.display_name
    if "ansible_host" in fields:
        serialized_host["ansible_host"] = host.ansible_host
    if "facts" in fields:
        serialized_host["facts"] = _serialize_facts(host.facts)
    if "reporter" in fields:
        serialized_host["reporter"] = host.reporter
    if "stale_timestamp" in fields:
        serialized_host["stale_timestamp"] = stale_timestamp and _serialize_datetime(stale_timestamp)
    if "stale_warning_timestamp" in fields:
        serialized_host["stale_warning_timestamp"] = stale_timestamp and _serialize_datetime(stale_warning_timestamp)
    if "culled_timestamp" in fields:
        serialized_host["culled_timestamp"] = stale_timestamp and _serialize_datetime(culled_timestamp)
        # without astimezone(timezone.utc) the isoformat() method does not include timezone offset even though iso-8601
        # requires it
    if "created" in fields:
        serialized_host["created"] = _serialize_datetime(host.created_on)
    if "updated" in fields:
        serialized_host["updated"] = _serialize_datetime(host.modified_on)
    if "tags" in fields:
        serialized_host["tags"] = _serialize_tags(host.tags)
    if "system_profile" in fields:
        serialized_host["system_profile"] = host.system_profile_facts or {}

    return serialized_host


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


def _deserialize_datetime(s):
    dt = isoparse(s)
    if not dt.tzinfo:
        raise ValueError(f'Timezone not specified in "{s}".')
    return dt.astimezone(timezone.utc)


def _serialize_uuid(u):
    return str(u)


def _deserialize_tags(tags):
    if isinstance(tags, list):
        return _deserialize_tags_list(tags)
    elif isinstance(tags, dict):
        return _deserialize_tags_dict(tags)
    elif tags is None:
        return {}
    else:
        raise ValueError("Tags must be dict, list or None.")


def _deserialize_tags_list(tags):
    deserialized = {}

    for tag_data in tags:
        namespace = Tag.deserialize_namespace(tag_data.get("namespace"))
        if namespace not in deserialized:
            deserialized[namespace] = {}

        key = tag_data.get("key")
        if not key:
            raise ValueError("Key cannot be empty.")

        if key not in deserialized[namespace]:
            deserialized[namespace][key] = []

        value = tag_data.get("value")
        if value and value not in deserialized[namespace][key]:
            deserialized[namespace][key].append(value)

    return deserialized


def _deserialize_tags_dict(tags):
    deserialized_tags = {}

    for namespace, tags_ns in tags.items():
        deserialized_namespace = Tag.deserialize_namespace(namespace)
        if deserialized_namespace not in deserialized_tags:
            deserialized_tags[deserialized_namespace] = {}
        deserialized_tags_ns = deserialized_tags[deserialized_namespace]

        if not tags_ns:
            continue

        for key, values in tags_ns.items():
            if not key:
                raise ValueError("Key cannot be empty.")

            if key not in deserialized_tags_ns:
                deserialized_tags_ns[key] = []
            deserialized_tags_key = deserialized_tags_ns[key]

            if not values:
                continue

            for value in values:
                if value and value not in deserialized_tags_key:
                    deserialized_tags_key.append(value)

    return deserialized_tags


def _serialize_tags(tags):
    return [tag.data() for tag in Tag.create_tags_from_nested(tags)]
