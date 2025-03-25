from __future__ import annotations

from datetime import datetime
from datetime import timezone

from dateutil.parser import isoparse
from marshmallow import ValidationError

from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.common import inventory_config
from app.culling import Conditions
from app.culling import Timestamps
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import CanonicalFactsSchema
from app.models import Host
from app.models import HostSchema
from app.models import LimitedHost
from app.models import LimitedHostSchema
from app.staleness_serialization import get_staleness_timestamps
from app.utils import Tag
from lib.feature_flags import FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS
from lib.feature_flags import get_flag_value

__all__ = (
    "deserialize_host",
    "serialize_host",
    "serialize_host_system_profile",
    "serialize_canonical_facts",
)


_EXPORT_SERVICE_FIELDS = [
    "host_id",
    "fqdn",
    "subscription_manager_id",
    "satellite_id",
    "display_name",
    "group_id",
    "group_name",
    "os_release",
    "updated",
    "state",
    "tags",
    "host_type",
]

_CANONICAL_FACTS_FIELDS = (
    "insights_id",
    "subscription_manager_id",
    "satellite_id",
    "bios_uuid",
    "ip_addresses",
    "fqdn",
    "mac_addresses",
    "provider_id",
    "provider_type",
)

DEFAULT_FIELDS = (
    "id",
    "account",
    "org_id",
    "display_name",
    "ansible_host",
    "facts",
    "reporter",
    "per_reporter_staleness",
    "stale_timestamp",
    "stale_warning_timestamp",
    "culled_timestamp",
    "created",
    "updated",
    "groups",
)

ADDITIONAL_HOST_MQ_FIELDS = (
    "tags",
    "system_profile",
)

ADDITIONAL_EXPORT_SERVICE_FIELDS = (
    "fqdn",
    "state",
    "tags",
    "host_type",
)


def deserialize_host(
    raw_data: dict, schema: type[HostSchema | LimitedHostSchema] = HostSchema, system_profile_spec: dict | None = None
) -> Host | LimitedHost:
    try:
        validated_data = schema(system_profile_schema=system_profile_spec).load(raw_data)
    except ValidationError as e:
        # Get the field name and data for each invalid field
        invalid_data = {k: e.data.get(k, "<missing>") for k in e.messages.keys()}
        raise ValidationException(str(e.messages) + "; Invalid data: " + str(invalid_data)) from None

    canonical_facts = _deserialize_canonical_facts(validated_data)
    facts = _deserialize_facts(validated_data.get("facts"))
    tags = _deserialize_tags(validated_data.get("tags"))
    tags_alt = validated_data.get("tags_alt", [])
    return schema.build_model(validated_data, canonical_facts, facts, tags, tags_alt)


def deserialize_canonical_facts(raw_data, all=False):
    if all:
        return _deserialize_all_canonical_facts(raw_data)

    try:
        validated_data = CanonicalFactsSchema().load(raw_data, partial=all)
    except ValidationError as e:
        raise ValidationException(str(e.messages)) from None

    return _deserialize_canonical_facts(validated_data)


# Removes any null canonical facts from a serialized host.
def remove_null_canonical_facts(serialized_host: dict):
    for field_name in [f for f in _CANONICAL_FACTS_FIELDS if serialized_host[f] is None]:
        del serialized_host[field_name]


def serialize_host(
    host,
    staleness_timestamps,
    for_mq=True,
    additional_fields=None,
    staleness=None,
    system_profile_fields=None,
):
    # Ensure additional_fields is a tuple
    additional_fields = additional_fields or tuple()

    timestamps = get_staleness_timestamps(host, staleness_timestamps, staleness)

    if get_flag_value(FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS):
        fields = DEFAULT_FIELDS + ("last_check_in",) + additional_fields
    else:
        fields = DEFAULT_FIELDS + additional_fields

    if for_mq:
        fields += ADDITIONAL_HOST_MQ_FIELDS

    # Base serialization
    serialized_host = {**serialize_canonical_facts(host.canonical_facts)}

    # Define field mapping to avoid repeated "if" conditions
    field_mapping = {
        "id": lambda: _serialize_uuid(host.id),
        "account": lambda: host.account,
        "org_id": lambda: host.org_id,
        "display_name": lambda: host.display_name,
        "ansible_host": lambda: host.ansible_host,
        "facts": lambda: serialize_facts(host.facts),
        "reporter": lambda: host.reporter,
        "per_reporter_staleness": lambda: _serialize_per_reporter_staleness(host, staleness, staleness_timestamps),
        "stale_timestamp": lambda: _serialize_staleness_to_string(timestamps["stale_timestamp"]),
        "stale_warning_timestamp": lambda: _serialize_staleness_to_string(timestamps["stale_warning_timestamp"]),
        "culled_timestamp": lambda: _serialize_staleness_to_string(timestamps["culled_timestamp"]),
        "created": lambda: _serialize_datetime(host.created_on),
        "updated": lambda: _serialize_datetime(host.modified_on),
        "last_check_in": lambda: _serialize_datetime(host.last_check_in),
        "tags": lambda: _serialize_tags(host.tags),
        "tags_alt": lambda: host.tags_alt,
        "state": lambda: Conditions.find_host_state(
            stale_timestamp=timestamps["stale_timestamp"],
            stale_warning_timestamp=timestamps["stale_warning_timestamp"],
        ),
        "host_type": lambda: host.host_type,
        "os_release": lambda: host.system_profile_facts.get("os_release", None),
    }

    # Process each field dynamically
    serialized_host.update({key: func() for key, func in field_mapping.items() if key in fields})

    # Handle system_profile separately due to its complexity
    if "system_profile" in fields:
        serialized_host["system_profile"] = (
            {k: v for k, v in host.system_profile_facts.items() if k in system_profile_fields}
            if host.system_profile_facts and system_profile_fields
            else host.system_profile_facts or {}
        )
        if (
            system_profile_fields
            and system_profile_fields.count("host_type") < 2
            and serialized_host["system_profile"].get("host_type")
        ):
            del serialized_host["system_profile"]["host_type"]

    # Handle groups separately
    if "groups" in fields:
        serialized_host["groups"] = (
            [{key: group[key] for key in ["name", "id"]} for group in host.groups]
            if for_mq and host.groups
            else host.groups or []
        )

    return serialized_host


def serialize_host_for_export_svc(
    host,
    staleness_timestamps,
    staleness=None,
):
    serialized_host = serialize_host(
        host, staleness_timestamps=staleness_timestamps, staleness=staleness, additional_fields=("os_release", "state")
    )

    serialized_host["host_id"] = _serialize_uuid(host.id)
    serialized_host["hostname"] = host.display_name
    if host.groups:
        serialized_host["group_id"] = host.groups[0]["id"]  # Assuming just one group per host
        serialized_host["group_name"] = host.groups[0]["name"]  # Assuming just one group per host
    else:
        serialized_host["group_id"] = None  # Assuming just one group per host
        serialized_host["group_name"] = None  # Assuming just one group per host
    serialized_host["host_type"] = host.host_type
    if not host.host_type:
        # For export service, host_type should be exported as conventional
        # if the host is not an edge one instead of None.
        serialized_host["host_type"] = "conventional"

    serialized_host = {key: serialized_host[key] for key in _EXPORT_SERVICE_FIELDS}
    return serialized_host


# get hosts not marked for deletion
def _get_unculled_hosts(group, org_id):
    hosts = []
    staleness_timestamps = Timestamps.from_config(inventory_config())
    staleness = get_staleness_obj(org_id)
    for host in group.hosts:
        serialized_host = serialize_host(host, staleness_timestamps=staleness_timestamps, staleness=staleness)
        if _deserialize_datetime(serialized_host["culled_timestamp"]) > datetime.now(tz=timezone.utc):
            hosts.append(host)

    return hosts


def serialize_group(group, org_id):
    unculled_hosts = _get_unculled_hosts(group, org_id)
    return {
        "id": _serialize_uuid(group.id),
        "org_id": group.org_id,
        "account": group.account,
        "name": group.name,
        "host_count": len(unculled_hosts),
        "created": _serialize_datetime(group.created_on),
        "updated": _serialize_datetime(group.modified_on),
    }


def serialize_host_system_profile(host):
    return {"id": _serialize_uuid(host.id), "system_profile": host.system_profile_facts or {}}


def _recursive_casefold(field_data):
    if isinstance(field_data, str):
        return field_data.casefold()
    elif isinstance(field_data, list):
        return [_recursive_casefold(x) for x in field_data]
    else:
        return field_data


def _deserialize_canonical_facts(data):
    return {field: _recursive_casefold(data[field]) for field in _CANONICAL_FACTS_FIELDS if data.get(field)}


def _deserialize_all_canonical_facts(data):
    return {field: _recursive_casefold(data[field]) if data.get(field) else None for field in _CANONICAL_FACTS_FIELDS}


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
        except KeyError as e:
            # The facts from the request are formatted incorrectly
            raise InputFormatException(
                "Invalid format of Fact object.  Fact must contain 'namespace' and 'facts' keys."
            ) from e
    return facts


def serialize_facts(facts):
    return [{"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()]


def _serialize_datetime(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _serialize_staleness_to_string(dt) -> str:
    """
    This function makes sure a datetime object
    is returned as a string
    """
    if isinstance(dt, str):
        return dt
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


def serialize_staleness_response(staleness):
    return {
        "id": _serialize_uuid(staleness.id),
        "org_id": staleness.org_id,
        "conventional_time_to_stale": staleness.conventional_time_to_stale,
        "conventional_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
        "conventional_time_to_delete": staleness.conventional_time_to_delete,
        "immutable_time_to_stale": staleness.immutable_time_to_stale,
        "immutable_time_to_stale_warning": staleness.immutable_time_to_stale_warning,
        "immutable_time_to_delete": staleness.immutable_time_to_delete,
        "created": _serialize_datetime(staleness.created_on) if staleness.created_on is not None else None,
        "updated": _serialize_datetime(staleness.modified_on) if staleness.modified_on is not None else None,
    }


def serialize_staleness_to_dict(staleness_obj) -> dict:
    """
    This function serialize a staleness object
    to a simple dictionary. This contains less information
    """
    return {
        "conventional_time_to_stale": staleness_obj.conventional_time_to_stale,
        "conventional_time_to_stale_warning": staleness_obj.conventional_time_to_stale_warning,
        "conventional_time_to_delete": staleness_obj.conventional_time_to_delete,
        "immutable_time_to_stale": staleness_obj.immutable_time_to_stale,
        "immutable_time_to_stale_warning": staleness_obj.immutable_time_to_stale_warning,
        "immutable_time_to_delete": staleness_obj.immutable_time_to_delete,
    }


def _serialize_per_reporter_staleness(host, staleness, staleness_timestamps):
    for reporter in host.per_reporter_staleness:
        if host.host_type == "edge" or (
            hasattr(host, "system_profile_facts")
            and host.system_profile_facts
            and host.system_profile_facts.get("host_type") == "edge"
        ):
            stale_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["immutable_time_to_stale"],
            )
            stale_warning_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["immutable_time_to_stale_warning"],
            )
            delete_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["immutable_time_to_delete"],
            )
        else:
            stale_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["conventional_time_to_stale"],
            )
            stale_warning_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["conventional_time_to_stale_warning"],
            )
            delete_timestamp = staleness_timestamps.stale_timestamp(
                _deserialize_datetime(host.per_reporter_staleness[reporter]["last_check_in"]),
                staleness["conventional_time_to_delete"],
            )

        host.per_reporter_staleness[reporter]["stale_timestamp"] = _serialize_staleness_to_string(stale_timestamp)
        host.per_reporter_staleness[reporter]["stale_warning_timestamp"] = _serialize_staleness_to_string(
            stale_warning_timestamp
        )
        host.per_reporter_staleness[reporter]["culled_timestamp"] = _serialize_staleness_to_string(delete_timestamp)

    return host.per_reporter_staleness


def build_rhel_version_str(system_profile: dict) -> str:
    os = system_profile.get("operating_system")
    if os and os.get("name", "").lower() == "rhel":
        major = os.get("major")
        minor = os.get("minor")
        return f"{major}.{minor}"
    return ""


def serialize_host_with_params(host, additional_fields=tuple(), system_profile_fields=None):
    timestamps = Timestamps.from_config(inventory_config())
    identity = get_current_identity()
    staleness = get_staleness_obj(identity.org_id)
    return serialize_host(host, timestamps, False, additional_fields, staleness, system_profile_fields)
