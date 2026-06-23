from copy import deepcopy
from typing import Any

from app.logging import get_logger
from app.models.constants import WORKLOADS_FIELDS
from app.models.schemas import HostDynamicSystemProfileSchema
from app.models.schemas import HostStaticSystemProfileSchema
from app.models.system_profile_normalizer import SystemProfileNormalizer

logger = get_logger(__name__)

# Define which fields belong to static vs dynamic system profiles using x-dynamic markers
PRIMARY_KEY_FIELDS = ["org_id", "host_id"]

# Use x-dynamic markers from YAML schema to determine field categorization
_normalizer = SystemProfileNormalizer()
STATIC_FIELDS = list(_normalizer.get_static_fields())
DYNAMIC_FIELDS = list(_normalizer.get_dynamic_fields())


def split_system_profile_data(system_profile_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Split system profile data into static and dynamic components.

    Args:
        system_profile_data: The complete system profile JSONB data

    Returns:
        Tuple of (static_data, dynamic_data) dictionaries
    """
    if not system_profile_data:
        return {}, {}

    static_data = {}
    dynamic_data = {}

    for key, value in system_profile_data.items():
        if value is None:
            pass
        elif key in STATIC_FIELDS:
            static_data[key] = value
        elif key in DYNAMIC_FIELDS:
            dynamic_data[key] = value
        else:
            raise ValueError(f"Unknown system profile field '{key}'")

    return static_data, dynamic_data


def map_system_profile_fields(
    org_id: str, host_id: str, system_profile_data: tuple[dict[str, Any], dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    static_data, dynamic_data = system_profile_data

    mapped_data_static = {"org_id": org_id, "host_id": host_id}
    mapped_data_dynamic = {"org_id": org_id, "host_id": host_id}

    # Add all static fields
    for field in STATIC_FIELDS:
        if field in static_data:
            mapped_data_static[field] = static_data[field]

    # Add all dynamic fields
    for field in DYNAMIC_FIELDS:
        if field in dynamic_data:
            mapped_data_dynamic[field] = dynamic_data[field]

    return mapped_data_static, mapped_data_dynamic


def _get_nested_value(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _remove_nested_field(data: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    if len(parts) == 1:
        data.pop(parts[0], None)
        return

    current = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]

    if isinstance(current, dict):
        current.pop(parts[-1], None)
        if not current and len(parts) > 1:
            data.pop(parts[0], None)


# Legacy root-level workload fields migrated to workloads.* on ingest. workloads.* takes precedence.
_WORKLOAD_INGEST_MIGRATION_CONFIG: dict[str, dict[str, Any]] = {
    "sap": {
        "flat_fields": {
            "sap_system": "sap_system",
            "sap_sids": "sids",
            "sap_instance_number": "instance_number",
            "sap_version": "version",
        },
        "nested_field": "sap",
        "nested_mapping": {
            "sap_system": "sap_system",
            "sids": "sids",
            "instance_number": "instance_number",
            "version": "version",
        },
    },
    "ansible": {"nested_field": "ansible"},
    "intersystems": {"nested_field": "intersystems"},
    "mssql": {"nested_field": "mssql"},
    "crowdstrike": {"nested_field": "third_party_services.crowdstrike"},
    "rhel_ai": {"nested_field": "rhel_ai"},
}


def _migrate_workload_to_workloads(
    system_profile: dict[str, Any],
    workloads: dict[str, Any],
    workload_type: str,
    config: dict[str, Any],
) -> None:
    if workload_type in workloads:
        return

    migrated_data: dict[str, Any] = {}

    if "flat_fields" in config:
        for legacy_key, new_key in config["flat_fields"].items():
            if legacy_key in system_profile:
                migrated_data[new_key] = system_profile[legacy_key]

    if "nested_field" in config:
        nested_value = _get_nested_value(system_profile, config["nested_field"])
        if isinstance(nested_value, dict):
            if "nested_mapping" in config:
                for legacy_key, new_key in config["nested_mapping"].items():
                    if legacy_key in nested_value:
                        migrated_data[new_key] = nested_value[legacy_key]
            else:
                migrated_data.update(deepcopy(nested_value))

    if migrated_data:
        workloads[workload_type] = migrated_data


def _remove_legacy_fields_for_workload(system_profile: dict[str, Any], config: dict[str, Any]) -> None:
    if "flat_fields" in config:
        for flat_field in config["flat_fields"]:
            system_profile.pop(flat_field, None)

    if "nested_field" in config:
        _remove_nested_field(system_profile, config["nested_field"])


def migrate_legacy_workload_root_fields_to_workloads(system_profile_data: dict[str, Any]) -> dict[str, Any]:
    """Move legacy root-level workload fields into workloads.* before storage."""
    workloads = system_profile_data.setdefault("workloads", {})

    for workload_type, config in _WORKLOAD_INGEST_MIGRATION_CONFIG.items():
        _migrate_workload_to_workloads(system_profile_data, workloads, workload_type, config)
        _remove_legacy_fields_for_workload(system_profile_data, config)

    if not workloads:
        system_profile_data.pop("workloads", None)

    return system_profile_data


def strip_legacy_workload_root_fields(system_profile_data: dict[str, Any]) -> dict[str, Any]:
    """Remove deprecated top-level workload fields before splitting for storage."""
    for field in WORKLOADS_FIELDS:
        system_profile_data.pop(field, None)
    return system_profile_data


def validate_and_transform(
    org_id: str, host_id: str, system_profile_data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Combined validation and transformation of system profile data.

    Args:
        org_id: Organization ID
        host_id: Host ID
        system_profile_data: The complete system profile JSONB data

    Returns:
        Tuple of validated (static_data, dynamic_data) dictionaries ready for database insertion

    Raises:
        ValidationError: If the data fails validation
    """
    # Normalize legacy root-level workload fields into workloads.*, then drop legacy keys
    system_profile_data = migrate_legacy_workload_root_fields_to_workloads(deepcopy(system_profile_data))
    system_profile_data = strip_legacy_workload_root_fields(system_profile_data)
    static_data, dynamic_data = split_system_profile_data(system_profile_data)

    # Map to table schemas
    static_mapped, dynamic_mapped = map_system_profile_fields(org_id, host_id, (static_data, dynamic_data))

    # Validate using schemas
    static_schema = HostStaticSystemProfileSchema()
    dynamic_schema = HostDynamicSystemProfileSchema()

    # This will raise ValidationError if data is invalid
    validated_static = static_schema.load(static_mapped)
    validated_dynamic = dynamic_schema.load(dynamic_mapped)

    return validated_static, validated_dynamic
