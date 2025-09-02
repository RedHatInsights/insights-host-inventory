from typing import Any

from sqlalchemy import inspect

from app.logging import get_logger
from app.models.schemas import HostDynamicSystemProfileSchema
from app.models.schemas import HostStaticSystemProfileSchema
from app.models.system_profile_dynamic import HostDynamicSystemProfile
from app.models.system_profile_static import HostStaticSystemProfile

logger = get_logger(__name__)

# Define which fields belong to static vs dynamic system profiles
PRIMARY_KEY_FIELDS = ["org_id", "host_id"]

STATIC_FIELDS = [c.key for c in inspect(HostStaticSystemProfile).mapper.columns if c.key not in PRIMARY_KEY_FIELDS]

DYNAMIC_FIELDS = [c.key for c in inspect(HostDynamicSystemProfile).mapper.columns if c.key not in PRIMARY_KEY_FIELDS]

WORKLOADS_FIELDS = {"ansible", "crowdstrike", "ibm_db2", "intersystems", "mssql", "oracle_db", "rhel_ai", "sap"}


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
        if key in STATIC_FIELDS:
            static_data[key] = value
        elif key in DYNAMIC_FIELDS:
            dynamic_data[key] = value
        # Workaround until we transition workloads fields usage
        elif key in WORKLOADS_FIELDS or "sap" in key:
            pass
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
    # Split the data
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
