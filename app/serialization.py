from datetime import timezone
from functools import partial

from dateutil.parser import isoparse
from marshmallow import ValidationError

from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import Host as Host
from app.models import HttpHostSchema
from app.models import MqHostSchema
from app.models import SystemProfileSchema
from app.utils import Tag

__all__ = ("deserialize_host", "serialize_host", "serialize_host_system_profile", "serialize_canonical_facts")


_CANONICAL_FACTS_FIELDS = {
    "insights_id",
    "rhel_machine_id",
    "subscription_manager_id",
    "satellite_id",
    "bios_uuid",
    "ip_addresses",
    "fqdn",
    "mac_addresses",
    "external_id",
}

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


def deserialize_host_http(raw_data):
    return deserialize_host(raw_data, HttpHostSchema)


def deserialize_host_mq(raw_data):
    return deserialize_host(raw_data, MqHostSchema)


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


def serialize_host(host, staleness_timestamps, fields=DEFAULT_FIELDS, canonical_fields=_CANONICAL_FACTS_FIELDS):
    return {
        **serialize_canonical_facts(host.canonical_facts, canonical_fields),
        **_serialize_host_fields(host, fields, staleness_timestamps),
    }


def _valid_host_query_attributes():
    valid_attributes = set(HttpHostSchema(strict=True).fields)
    valid_attributes = valid_attributes.union({"created", "updated", "stale_warning_timestamp", "culled_timestamp"})
    valid_attributes.remove("system_profile")
    return valid_attributes


def _error_invalid_attribute(valid_attributes):
    raise KeyError(
        "Requested attribute not present in schema. Valid attributes include: " f"{', '.join(valid_attributes)}"
    )


def serialize_host_sparse(host, staleness_timestamps, sparse_fieldset):
    host_fields = {"id"}
    canonical_fields = set()

    if "host" in sparse_fieldset:
        requested_host_fields = set(sparse_fieldset["host"].split(","))
        canonical_fields |= requested_host_fields & _CANONICAL_FACTS_FIELDS
        host_fields |= requested_host_fields - canonical_fields - {"system_profile"}
        if (host_fields - _valid_host_query_attributes()) != {"id"}:
            _error_invalid_attribute(_valid_host_query_attributes() - {"id"})

    serialized_host = serialize_host(host, staleness_timestamps, host_fields, canonical_fields)

    if "system_profile" in sparse_fieldset:
        system_profile_attributes = sparse_fieldset["system_profile"].split(",")
        serialized_host["system_profile"] = {}
        for system_profile_attribute in system_profile_attributes:
            if system_profile_attribute in host.system_profile_facts:
                serialized_host["system_profile"][system_profile_attribute] = host.system_profile_facts[
                    system_profile_attribute
                ]
            elif system_profile_attribute not in SystemProfileSchema(strict=True).fields:
                _error_invalid_attribute(list(SystemProfileSchema(strict=True).fields))

    return serialized_host


def _serialize_host_fields(host, fields, staleness_timestamps):
    def raw(field):
        return getattr(host, field)

    def function(field, serialize):
        field_map = {"created": "created_on", "updated": "modified_on"}
        attr = field_map.get(field, field)
        value = getattr(host, attr)
        return serialize(value)

    def staleness_timestamp(field):
        if not host.stale_timestamp:
            return
        compute = getattr(staleness_timestamps, field)
        timestamp = compute(host.stale_timestamp)
        return _serialize_datetime(timestamp)

    def system_profile(field):
        return host.system_profile_facts or {}

    serialization_map = {
        "account": raw,
        "display_name": raw,
        "ansible_host": raw,
        "reporter": raw,
        "id": partial(function, serialize=_serialize_uuid),
        "facts": partial(function, serialize=_serialize_facts),
        "created": partial(function, serialize=_serialize_datetime),
        "updated": partial(function, serialize=_serialize_datetime),
        "tags": partial(function, serialize=_serialize_tags),
        "stale_timestamp": staleness_timestamp,
        "stale_warning_timestamp": staleness_timestamp,
        "culled_timestamp": staleness_timestamp,
        "system_profile": system_profile,
    }
    return {field: serialization_map[field](field) for field in fields}


def serialize_host_system_profile(host):
    return {"id": _serialize_uuid(host.id), "system_profile": host.system_profile_facts or {}}


def _deserialize_canonical_facts(data):
    return {field: data[field] for field in _CANONICAL_FACTS_FIELDS if data.get(field)}


def serialize_canonical_facts(canonical_facts, canonical_fields=_CANONICAL_FACTS_FIELDS):
    return {field: canonical_facts.get(field) for field in canonical_fields}


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
