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
from app.models import HostSchema
from app.utils import Tag


__all__ = ("deserialize_host", "serialize_host", "serialize_host_system_profile", "serialize_canonical_facts")


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


def deserialize_host(raw_data, schema=HostSchema, system_profile_spec=None):
    try:
        validated_data = schema(system_profile_schema=system_profile_spec).load(raw_data)
    except ValidationError as e:
        # Get the field name and data for each invalid field
        invalid_data = {k: e.data.get(k, "<missing>") for k in e.messages.keys()}
        raise ValidationException(str(e.messages) + "; Invalid data: " + str(invalid_data)) from None

    canonical_facts = _deserialize_canonical_facts(validated_data)
    facts = _deserialize_facts(validated_data.get("facts"))
    tags = _deserialize_tags(validated_data.get("tags"))
    return schema.build_model(validated_data, canonical_facts, facts, tags)


def deserialize_canonical_facts(raw_data, all=False):
    if all:
        return _deserialize_all_canonical_facts(raw_data)

    try:
        validated_data = CanonicalFactsSchema().load(raw_data, partial=all)
    except ValidationError as e:
        raise ValidationException(str(e.messages)) from None

    return _deserialize_canonical_facts(validated_data)


def serialize_host(
    host,
    staleness_timestamps,
    for_mq=True,
    additional_fields=tuple(),
    staleness=None,
    system_profile_fields=None,
    omit_null_facts=False,
):
    # TODO: In future, this must handle groups staleness
    if host.host_type == "edge" or (
        hasattr(host, "system_profile_facts")
        and host.system_profile_facts
        and host.system_profile_facts.get("host_type") == "edge"
    ):
        stale_timestamp = staleness_timestamps.stale_timestamp(host.modified_on, staleness["immutable_time_to_stale"])
        stale_warning_timestamp = staleness_timestamps.stale_warning_timestamp(
            host.modified_on, staleness["immutable_time_to_stale_warning"]
        )
        culled_timestamp = staleness_timestamps.culled_timestamp(
            host.modified_on, staleness["immutable_time_to_delete"]
        )
    else:
        stale_timestamp = staleness_timestamps.stale_timestamp(
            host.modified_on, staleness["conventional_time_to_stale"]
        )
        stale_warning_timestamp = staleness_timestamps.stale_warning_timestamp(
            host.modified_on, staleness["conventional_time_to_stale_warning"]
        )
        culled_timestamp = staleness_timestamps.culled_timestamp(
            host.modified_on, staleness["conventional_time_to_delete"]
        )

    serialized_host = {**serialize_canonical_facts(host.canonical_facts, omit_null_facts=omit_null_facts)}

    fields = DEFAULT_FIELDS + additional_fields
    if for_mq:
        fields += ADDITIONAL_HOST_MQ_FIELDS

    if "id" in fields:
        serialized_host["id"] = _serialize_uuid(host.id)
    if "account" in fields:
        serialized_host["account"] = host.account
    if "org_id" in fields:
        serialized_host["org_id"] = host.org_id
    if "display_name" in fields:
        serialized_host["display_name"] = host.display_name
    if "ansible_host" in fields:
        serialized_host["ansible_host"] = host.ansible_host
    if "facts" in fields:
        serialized_host["facts"] = serialize_facts(host.facts)
    if "reporter" in fields:
        serialized_host["reporter"] = host.reporter
    if "per_reporter_staleness" in fields:
        serialized_host["per_reporter_staleness"] = _serialize_per_reporter_staleness(
            host, staleness, staleness_timestamps
        )
    if "stale_timestamp" in fields:
        serialized_host["stale_timestamp"] = stale_timestamp and _serialize_staleness_to_string(stale_timestamp)
    if "stale_warning_timestamp" in fields:
        serialized_host["stale_warning_timestamp"] = stale_warning_timestamp and _serialize_staleness_to_string(
            stale_warning_timestamp
        )
    if "culled_timestamp" in fields:
        serialized_host["culled_timestamp"] = culled_timestamp and _serialize_staleness_to_string(culled_timestamp)
        # without astimezone(timezone.utc) the isoformat() method does not include timezone offset even though iso-8601
        # requires it
    if "created" in fields:
        serialized_host["created"] = _serialize_datetime(host.created_on)
    if "updated" in fields:
        serialized_host["updated"] = _serialize_datetime(host.modified_on)
    if "tags" in fields:
        serialized_host["tags"] = _serialize_tags(host.tags)
    if "system_profile" in fields:
        if host.system_profile_facts:
            if system_profile_fields:
                serialized_host["system_profile"] = {
                    k: v for (k, v) in host.system_profile_facts.items() if k in system_profile_fields
                }
            else:
                serialized_host["system_profile"] = host.system_profile_facts
        else:
            serialized_host["system_profile"] = {}

        if system_profile_fields and system_profile_fields.count("host_type") < 2:
            if serialized_host["system_profile"].get("host_type"):
                del serialized_host["system_profile"]["host_type"]
    if "groups" in fields:
        # For MQ messages, we only include name and ID.
        if for_mq and host.groups:
            serialized_host["groups"] = [
                {key: group[key] for key in group if key in ["name", "id"]} for group in host.groups
            ]
        else:
            serialized_host["groups"] = host.groups or []
    if "os_release" in fields:
        if "os_release" in host.system_profile_facts:
            serialized_host["os_release"] = host.system_profile_facts["os_release"]
        else:
            serialized_host["os_release"] = None

    if "state" in fields:
        serialized_host["state"] = Conditions.find_host_state(
            stale_timestamp=stale_timestamp, stale_warning_timestamp=stale_warning_timestamp
        )

    if "host_type" in fields:
        serialized_host["host_type"] = host.host_type
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
def _get_unculled_hosts(group, identity):
    hosts = []
    staleness_timestamps = Timestamps.from_config(inventory_config())
    staleness = get_staleness_obj(identity)
    for host in group.hosts:
        serialized_host = serialize_host(host, staleness_timestamps=staleness_timestamps, staleness=staleness)
        if _deserialize_datetime(serialized_host["culled_timestamp"]) > datetime.now(tz=timezone.utc):
            hosts.append(host)

    return hosts


def serialize_group(group, identity):
    unculled_hosts = _get_unculled_hosts(group, identity)
    return {
        "id": _serialize_uuid(group.id),
        "org_id": group.org_id,
        "account": group.account,
        "name": group.name,
        "host_count": len(unculled_hosts),
        "created": _serialize_datetime(group.created_on),
        "updated": _serialize_datetime(group.modified_on),
    }


def serialize_assignment_rule(assign_rule):
    return {
        "id": _serialize_uuid(assign_rule.id),
        "org_id": assign_rule.org_id,
        "account": assign_rule.account,
        "name": assign_rule.name,
        "description": assign_rule.description,
        "group_id": _serialize_uuid(assign_rule.group_id),
        "filter": assign_rule.filter,
        "enabled": assign_rule.enabled,
        "created": _serialize_datetime(assign_rule.created_on),
        "modified": _serialize_datetime(assign_rule.modified_on),
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


def serialize_canonical_facts(canonical_facts, omit_null_facts=False):
    if omit_null_facts:
        return {field: canonical_facts.get(field) for field in _CANONICAL_FACTS_FIELDS if field in canonical_facts}
    else:
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
    if os:
        if os.get("name", "").lower() == "rhel":
            major = os.get("major")
            minor = os.get("minor")
            return f"{major}.{minor}"
    return ""


def serialize_host_with_params(host, additional_fields=tuple(), system_profile_fields=None):
    timestamps = Timestamps.from_config(inventory_config())
    identity = get_current_identity()
    staleness = get_staleness_obj(identity)
    return serialize_host(host, timestamps, False, additional_fields, staleness, system_profile_fields)
