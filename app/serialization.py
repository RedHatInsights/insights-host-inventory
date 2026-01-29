from __future__ import annotations

from datetime import UTC
from typing import Any
from typing import TypedDict
from uuid import UUID

from dateutil.parser import isoparse
from marshmallow import ValidationError

from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.common import inventory_config
from app.config import CANONICAL_FACTS_FIELDS
from app.config import DEFAULT_INSIGHTS_ID
from app.culling import Conditions
from app.culling import Timestamps
from app.culling import should_host_stay_fresh_forever
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models import CanonicalFactsSchema
from app.models import Group
from app.models import Host
from app.models import HostSchema
from app.models import LimitedHost
from app.models import LimitedHostSchema
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.staleness_serialization import get_staleness_timestamps
from app.utils import Tag
from lib.feature_flags import FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)

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
    "last_check_in",
    "openshift_cluster_id",
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
    main_data = {**validated_data, **canonical_facts}
    return schema.build_model(main_data, facts, tags, tags_alt)


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
    for field_name in CANONICAL_FACTS_FIELDS:
        if field_name in serialized_host and serialized_host[field_name] is None:
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
    additional_fields = additional_fields or ()

    timestamps = get_staleness_timestamps(host, staleness_timestamps, staleness)

    fields = DEFAULT_FIELDS + additional_fields

    if for_mq:
        fields += ADDITIONAL_HOST_MQ_FIELDS

    # Base serialization
    serialized_host = {**serialize_canonical_facts(host)}

    # Define field mapping to avoid repeated "if" conditions
    field_mapping = {
        "id": lambda: serialize_uuid(host.id),
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
        "openshift_cluster_id": lambda: serialize_uuid(host.openshift_cluster_id),
    }

    # Process each field dynamically
    serialized_host |= {key: func() for key, func in field_mapping.items() if key in fields}

    # Handle system_profile separately due to its complexity
    if "system_profile" in fields:
        serialized_host["system_profile"] = (
            {k: v for k, v in host.system_profile_facts.items() if k in system_profile_fields}
            if host.system_profile_facts and system_profile_fields
            else host.system_profile_facts or {}
        )

        # Add backward compatibility for workload fields
        if serialized_host["system_profile"] and get_flag_value(
            FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY
        ):
            # Temporarily add workloads from source for backward compat if needed
            if "workloads" not in serialized_host["system_profile"] and host.system_profile_facts:
                workloads_data = host.system_profile_facts.get("workloads")
                if workloads_data:
                    serialized_host["system_profile"]["workloads"] = workloads_data

            serialized_host["system_profile"] = _add_workloads_backward_compatibility(
                serialized_host["system_profile"]
            )

            # Re-filter to only keep requested fields
            if system_profile_fields:
                serialized_host["system_profile"] = {
                    k: v for k, v in serialized_host["system_profile"].items() if k in system_profile_fields
                }

        if (
            system_profile_fields
            and system_profile_fields.count("host_type") < 2
            and serialized_host["system_profile"].get("host_type")
        ):
            del serialized_host["system_profile"]["host_type"]

    # Handle groups separately
    if "groups" in fields:
        serialized_host["groups"] = (
            [
                {"name": group["name"], "id": group["id"], "ungrouped": group.get("ungrouped", False)}
                for group in host.groups
            ]
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

    serialized_host["host_id"] = serialize_uuid(host.id)
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


def serialize_group_without_host_count(group: Group) -> dict:
    return {
        "id": serialize_uuid(group.id),
        "org_id": group.org_id,
        "account": group.account,
        "name": group.name,
        "ungrouped": group.ungrouped,
        "created": _serialize_datetime(group.created_on),
        "updated": _serialize_datetime(group.modified_on),
    }


def serialize_group_with_host_count(group: Group, host_count: int) -> dict:
    return {**serialize_group_without_host_count(group), "host_count": host_count}


def serialize_host_system_profile(host):
    return {"id": serialize_uuid(host.id), "system_profile": host.system_profile_facts or {}}


def _recursive_casefold(field_data):
    if isinstance(field_data, str):
        return field_data.casefold()
    elif isinstance(field_data, list):
        return [_recursive_casefold(x) for x in field_data]
    else:
        return field_data


def _deserialize_canonical_facts(data):
    """
    Deserialize canonical facts: apply case folding and filter falsy values.
    """
    return {field: _recursive_casefold(data[field]) for field in CANONICAL_FACTS_FIELDS if data.get(field)}


def _deserialize_all_canonical_facts(data):
    """
    Deserialize canonical facts: apply case folding, keeping None values.
    """
    return {field: _recursive_casefold(data[field]) if data.get(field) else None for field in CANONICAL_FACTS_FIELDS}


def serialize_canonical_facts(host: Host | LimitedHost, include_none: bool = True) -> dict[str, Any]:
    """
    Serialize canonical facts from a host object to a dictionary.

    Args:
        host: The host object (Host or LimitedHost) to serialize canonical facts from.
        include_none: If True (default), includes all canonical fact fields in the output,
            even when their values are None. If False, only includes fields with non-None values.

    Returns:
        A dictionary containing the serialized canonical facts. Empty lists for
        ip_addresses and mac_addresses are converted to None.
    """
    canonical_facts = {}
    for field in CANONICAL_FACTS_FIELDS:
        value = getattr(host, field, None)
        if isinstance(value, UUID):
            value = serialize_uuid(value)
        elif field in {"ip_addresses", "mac_addresses"} and value == []:
            value = None
        elif field == "insights_id" and value is None and include_none:
            value = DEFAULT_INSIGHTS_ID

        if value is not None or include_none:
            canonical_facts[field] = value
    return canonical_facts


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
    return dt.astimezone(UTC).isoformat()


def _serialize_staleness_to_string(dt) -> str:
    """
    This function makes sure a datetime object
    is returned as a string
    """
    if isinstance(dt, str):
        return dt
    return dt.astimezone(UTC).isoformat()


def _deserialize_datetime(s):
    dt = isoparse(s)
    if not dt.tzinfo:
        raise ValueError(f'Timezone not specified in "{s}".')
    return dt.astimezone(UTC)


def serialize_uuid(u):
    return str(u) if u else None


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
        "id": serialize_uuid(staleness.id),
        "org_id": staleness.org_id,
        "conventional_time_to_stale": staleness.conventional_time_to_stale,
        "conventional_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
        "conventional_time_to_delete": staleness.conventional_time_to_delete,
        "immutable_time_to_stale": staleness.conventional_time_to_stale,
        "immutable_time_to_stale_warning": staleness.conventional_time_to_stale_warning,
        "immutable_time_to_delete": staleness.conventional_time_to_delete,
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
    }


class _WorkloadCompatConfig(TypedDict, total=False):
    """Type definition for workload backward compatibility configuration."""

    path: list[str]
    fields: dict[str, str]
    flat_fields: dict[str, str]


def _map_host_type_for_backward_compatibility(host_type: str | None) -> str:
    """
    Map host_type values for backward compatibility with downstream apps.

    Downstream applications only recognize 'edge' as a special value.
    All other values (bootc, conventional, cluster) should be mapped to empty string
    to maintain backward compatibility.

    Args:
        host_type: The host_type value from the database/system profile

    Returns:
        str: Backward-compatible host_type value:
            - "edge" for actual edge systems (only explicit "edge")
            - "" (empty string) for all other types (bootc, conventional, cluster, etc.)

    Note:
        This mapping is only applied to Kafka events, not API responses.
        API responses return the actual database values.
    """
    return "edge" if host_type == "edge" else ""


def _add_workloads_backward_compatibility(system_profile: dict) -> dict:
    """
    Populate legacy workload fields with data from workloads.* for backward compatibility,
    and remove None values from workloads.* to comply with OpenAPI spec.

    This ensures subscribers can transition from legacy root-level fields to the new
    workloads structure for SAP, Ansible, InterSystems, MSSQL, and CrowdStrike.

    Args:
        system_profile: The system profile dictionary

    Returns:
        Modified system_profile with populated legacy workload fields
    """
    workloads = system_profile.get("workloads", {})
    if not workloads:
        return system_profile

    # define every workload's nested‐path + field mappings (and any flat mappings)
    COMPAT_CONFIG: dict[str, _WorkloadCompatConfig] = {
        "sap": {
            "path": ["sap"],
            "fields": {
                "sap_system": "sap_system",
                "sids": "sids",
                "instance_number": "instance_number",
                "version": "version",
            },
            "flat_fields": {
                "sap_system": "sap_system",
                "sids": "sap_sids",
                "instance_number": "sap_instance_number",
                "version": "sap_version",
            },
        },
        "ansible": {
            "path": ["ansible"],
            "fields": {
                "controller_version": "controller_version",
                "hub_version": "hub_version",
                "catalog_worker_version": "catalog_worker_version",
                "sso_version": "sso_version",
            },
        },
        "intersystems": {
            "path": ["intersystems"],
            "fields": {
                "is_intersystems": "is_intersystems",
                "running_instances": "running_instances",
            },
        },
        "mssql": {
            "path": ["mssql"],
            "fields": {
                "version": "version",
            },
        },
        "crowdstrike": {
            "path": ["third_party_services", "crowdstrike"],
            "fields": {
                "falcon_aid": "falcon_aid",
                "falcon_backend": "falcon_backend",
                "falcon_version": "falcon_version",
            },
        },
    }

    for wl_key, cfg in COMPAT_CONFIG.items():
        data = workloads.get(wl_key)
        if not data:
            continue

        # Remove None values from workloads.* to comply with OpenAPI spec
        none_keys = [k for k, v in data.items() if v is None]
        for k in none_keys:
            del data[k]

        # ensure nested path exists
        target = system_profile
        for p in cfg["path"]:
            target = target.setdefault(p, {})

        # copy each mapped field (skip None values to comply with OpenAPI spec)
        for new_field, out_key in cfg["fields"].items():
            if data.get(new_field) is not None:
                target[out_key] = data[new_field]

        # handle any top‐level “flat” mappings
        for new_field, out_key in cfg.get("flat_fields", {}).items():
            if data.get(new_field) is not None:
                system_profile[out_key] = data[new_field]

    return system_profile


# I could do this one as well ####################################
def _serialize_per_reporter_staleness(host, staleness, staleness_timestamps):
    for reporter in host.per_reporter_staleness:
        # For hosts that should stay fresh forever, use far-future timestamps
        if should_host_stay_fresh_forever(host):
            stale_timestamp = FAR_FUTURE_STALE_TIMESTAMP
            stale_warning_timestamp = FAR_FUTURE_STALE_TIMESTAMP
            delete_timestamp = FAR_FUTURE_STALE_TIMESTAMP
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
