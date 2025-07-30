from typing import Any

from app.logging import get_logger
from app.models.schemas import HostDynamicSystemProfileSchema
from app.models.schemas import HostStaticSystemProfileSchema

logger = get_logger(__name__)

# Define which fields belong to static vs dynamic system profiles
STATIC_FIELDS = {
    "arch",
    "basearch",
    "bios_release_date",
    "bios_vendor",
    "bios_version",
    "bootc_status",
    "cloud_provider",
    "conversions",
    "cores_per_socket",
    "cpu_model",
    "disk_devices",
    "dnf_modules",
    "enabled_services",
    "gpg_pubkeys",
    "greenboot_fallback_detected",
    "greenboot_status",
    "host_type",
    "image_builder",
    "infrastructure_type",
    "infrastructure_vendor",
    "insights_client_version",
    "installed_packages_delta",
    "installed_services",
    "intersystems",
    "is_marketplace",
    "katello_agent_running",
    "number_of_cpus",
    "number_of_sockets",
    "operating_system",
    "os_kernel_version",
    "os_release",
    "owner_id",
    "public_dns",
    "public_ipv4_addresses",
    "releasever",
    "rhc_client_id",
    "rhc_config_state",
    "rhel_ai",
    "rhsm",
    "rpm_ostree_deployments",
    "satellite_managed",
    "selinux_config_file",
    "selinux_current_mode",
    "subscription_auto_attach",
    "subscription_status",
    "system_purpose",
    "system_update_method",
    "third_party_services",
    "threads_per_core",
    "tuned_profile",
    "virtual_host_uuid",
    "yum_repos",
}

DYNAMIC_FIELDS = {
    "captured_date",
    "running_processes",
    "last_boot_time",
    "installed_packages",
    "network_interfaces",
    "installed_products",
    "cpu_flags",
    "insights_egg_version",
    "kernel_modules",
    "system_memory_bytes",
    "systemd",
    "workloads",
}


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
        else:
            logger.warning(f"Unknown system profile field '{key}' - adding to static data")
            static_data[key] = value

    return static_data, dynamic_data


def map_to_static_fields(org_id: str, host_id: str, static_data: dict[str, Any]) -> dict[str, Any]:
    """
    Transform static system profile data for the static table.

    Args:
        org_id: Organization ID
        host_id: Host ID
        static_data: Static system profile data

    Returns:
        Dictionary suitable for HostStaticSystemProfile model
    """
    mapped_data = {"org_id": org_id, "host_id": host_id}

    # Add all static fields
    for field in STATIC_FIELDS:
        if field in static_data:
            mapped_data[field] = static_data[field]

    return mapped_data


def map_to_dynamic_fields(org_id: str, host_id: str, dynamic_data: dict[str, Any]) -> dict[str, Any]:
    """
    Transform dynamic system profile data for the dynamic table.

    Args:
        org_id: Organization ID
        host_id: Host ID
        dynamic_data: Dynamic system profile data

    Returns:
        Dictionary suitable for HostDynamicSystemProfile model
    """
    mapped_data = {"org_id": org_id, "host_id": host_id}

    # Add all dynamic fields
    for field in DYNAMIC_FIELDS:
        if field in dynamic_data:
            mapped_data[field] = dynamic_data[field]

    return mapped_data


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
    static_mapped = map_to_static_fields(org_id, host_id, static_data)
    dynamic_mapped = map_to_dynamic_fields(org_id, host_id, dynamic_data)

    # Validate using schemas
    static_schema = HostStaticSystemProfileSchema()
    dynamic_schema = HostDynamicSystemProfileSchema()

    # This will raise ValidationError if data is invalid
    validated_static = static_schema.load(static_mapped)
    validated_dynamic = dynamic_schema.load(dynamic_mapped)

    return validated_static, validated_dynamic
