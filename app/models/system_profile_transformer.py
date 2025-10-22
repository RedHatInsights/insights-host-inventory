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
        if value is None or value == {} or value == []:
            pass
        elif key in STATIC_FIELDS:
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
