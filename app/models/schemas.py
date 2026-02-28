import contextlib
from copy import deepcopy
from typing import Any
from typing import TypedDict

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as jsonschema_validate
from jsonschema.validators import Draft4Validator
from marshmallow import EXCLUDE
from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields
from marshmallow import post_load
from marshmallow import pre_load
from marshmallow import validate as marshmallow_validate
from marshmallow import validates
from marshmallow import validates_schema

from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import get_logger
from app.models.constants import MAX_CANONICAL_FACTS_VERSION
from app.models.constants import MIN_CANONICAL_FACTS_VERSION
from app.models.constants import TAG_KEY_VALIDATION
from app.models.constants import TAG_NAMESPACE_VALIDATION
from app.models.constants import TAG_VALUE_VALIDATION
from app.models.constants import ZERO_MAC_ADDRESS
from app.models.constants import ProviderType
from app.models.host import Host
from app.models.host import LimitedHost
from app.models.system_profile_normalizer import SystemProfileNormalizer
from app.validators import check_empty_keys
from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format

logger = get_logger(__name__)


def verify_uuid_format_not_empty_dict(value):
    """Validate UUID format and reject empty dict."""
    if isinstance(value, dict) and len(value) == 0:
        raise MarshmallowValidationError("Value cannot be an empty dictionary")
    return verify_uuid_format(value)


class DiskDeviceSchema(MarshmallowSchema):
    device = fields.Str(validate=marshmallow_validate.Length(max=2048))
    label = fields.Str(validate=marshmallow_validate.Length(max=1024))
    options = fields.Dict(validate=check_empty_keys)
    mount_point = fields.Str(validate=marshmallow_validate.Length(max=2048))
    type = fields.Str(validate=marshmallow_validate.Length(max=256))


class RhsmSchema(MarshmallowSchema):
    version = fields.Str(validate=marshmallow_validate.Length(max=256))
    environment_ids = fields.List(fields.Str(validate=marshmallow_validate.Length(max=256)))


class OperatingSystemSchema(MarshmallowSchema):
    major = fields.Int()
    minor = fields.Int()
    name = fields.Str(validate=marshmallow_validate.Length(max=256))


class YumRepoSchema(MarshmallowSchema):
    id = fields.Str(validate=marshmallow_validate.Length(max=256))
    name = fields.Str(validate=marshmallow_validate.Length(max=1024))
    gpgcheck = fields.Bool()
    enabled = fields.Bool()
    base_url = fields.Str(validate=marshmallow_validate.Length(max=2048))
    mirrorlist = fields.Str(validate=marshmallow_validate.Length(max=2048))


class DnfModuleSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(max=128))
    stream = fields.Str(validate=marshmallow_validate.Length(max=2048))
    status = fields.List(fields.Str(validate=marshmallow_validate.Length(max=64)))


class InstalledProductSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(max=512))
    id = fields.Str(validate=marshmallow_validate.Length(max=64))
    status = fields.Str(validate=marshmallow_validate.Length(max=256))


class NetworkInterfaceSchema(MarshmallowSchema):
    ipv4_addresses = fields.List(fields.Str())
    ipv6_addresses = fields.List(fields.Str())
    state = fields.Str(validate=marshmallow_validate.Length(max=25))
    mtu = fields.Int()
    mac_address = fields.Str(validate=marshmallow_validate.Length(max=59))
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=50))
    state = fields.Str(validate=marshmallow_validate.Length(max=25))
    type = fields.Str(validate=marshmallow_validate.Length(max=18))


class FactsSchema(MarshmallowSchema):
    namespace = fields.Str()
    facts = fields.Dict(validate=check_empty_keys)


class TagsSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    namespace = fields.Str(required=False, allow_none=True, validate=TAG_NAMESPACE_VALIDATION)
    key = fields.Str(required=True, allow_none=False, validate=TAG_KEY_VALIDATION)
    value = fields.Str(required=False, allow_none=True, validate=TAG_VALUE_VALIDATION)


class CanonicalFactsSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    canonical_facts_version = fields.Integer(
        required=False,
        load_default=MIN_CANONICAL_FACTS_VERSION,
        validate=marshmallow_validate.Range(min=MIN_CANONICAL_FACTS_VERSION, max=MAX_CANONICAL_FACTS_VERSION),
    )
    is_virtual = fields.Boolean(required=False)

    insights_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    subscription_manager_id = fields.Str(validate=verify_uuid_format, allow_none=True)
    satellite_id = fields.Str(validate=verify_satellite_id, allow_none=True)
    fqdn = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), allow_none=True)
    bios_uuid = fields.Str(validate=verify_uuid_format, allow_none=True)
    ip_addresses = fields.List(fields.Str(validate=verify_ip_address_format), allow_none=True)
    mac_addresses = fields.List(
        fields.Str(validate=verify_mac_address_format), validate=marshmallow_validate.Length(min=1), allow_none=True
    )
    provider_id = fields.Str(validate=marshmallow_validate.Length(min=1, max=500), allow_none=True)
    provider_type = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), allow_none=True)

    @validates_schema
    def validate_schema(self, data, **kwargs):
        schema_version = data.get("canonical_facts_version")

        if "mac_addresses" in data and data["mac_addresses"] is not None:
            mac_addresses = data["mac_addresses"]
            while ZERO_MAC_ADDRESS in mac_addresses:
                mac_addresses.remove(ZERO_MAC_ADDRESS)
            if not mac_addresses:
                del data["mac_addresses"]

        if schema_version > MIN_CANONICAL_FACTS_VERSION:
            if "is_virtual" not in data:
                raise MarshmallowValidationError(
                    f"is_virtual is required for canonical_facts_version > {MIN_CANONICAL_FACTS_VERSION}."
                )
            if "mac_addresses" not in data:
                raise MarshmallowValidationError(
                    f"mac_addresses is required for canonical_facts_version > {MIN_CANONICAL_FACTS_VERSION}."
                )
            if data["is_virtual"]:
                if "provider_id" not in data:
                    raise MarshmallowValidationError(
                        "provider_id and provider_type are required when is_virtual = True."
                    )
            else:
                if "provider_id" in data:
                    raise MarshmallowValidationError("provider_id is not allowed when is_virtual = False.")

        provider_type = data.get("provider_type")
        provider_id = data.get("provider_id")

        if (provider_type and not provider_id) or (provider_id and not provider_type):
            raise MarshmallowValidationError("provider_type and provider_id are both required.")

        if provider_type and provider_type.lower() not in ProviderType.__members__.values():
            raise MarshmallowValidationError(
                f'Unknown Provider Type: "{provider_type}".  '
                f"Valid provider types are: {', '.join([p.value for p in ProviderType])}."
            )

        if provider_id and provider_id.isspace():
            raise MarshmallowValidationError("Provider id can not be just blank, whitespaces or tabs")


class LimitedHostSchema(CanonicalFactsSchema):
    class Meta:
        unknown = EXCLUDE

    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    account = fields.Str(validate=marshmallow_validate.Length(min=0, max=10))
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=36))
    facts = fields.List(fields.Nested(FactsSchema))
    system_profile = fields.Dict()
    tags = fields.Raw()
    tags_alt = fields.Raw()
    groups = fields.List(fields.Dict())
    openshift_cluster_id = fields.Str(validate=verify_uuid_format, allow_none=True)

    def __init__(self, system_profile_schema=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = type(self)
        if not hasattr(cls, "system_profile_normalizer"):
            cls.system_profile_normalizer = SystemProfileNormalizer()
        if system_profile_schema:
            self.system_profile_normalizer = SystemProfileNormalizer(system_profile_schema=system_profile_schema)

    @validates("tags")
    def validate_tags(self, tags, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if isinstance(tags, list):
            return self._validate_tags_list(tags)
        elif isinstance(tags, dict):
            return self._validate_tags_dict(tags)
        else:
            raise MarshmallowValidationError("Tags must be either an object or an array, and cannot be null.")

    @staticmethod
    def _validate_tags_list(tags):
        TagsSchema(many=True).load(tags)
        return True

    @staticmethod
    def _validate_tags_dict(tags):
        for namespace, ns_tags in tags.items():
            TAG_NAMESPACE_VALIDATION(namespace)
            if ns_tags is None:
                continue
            if not isinstance(ns_tags, dict):
                raise MarshmallowValidationError("Tags in a namespace must be an object or null.")

            for key, values in ns_tags.items():
                TAG_KEY_VALIDATION(key)
                if values is None:
                    continue
                if not isinstance(values, list):
                    raise MarshmallowValidationError("Tag values must be an array or null.")

                for value in values:
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise MarshmallowValidationError("Tag value must be a string or null.")
                    TAG_VALUE_VALIDATION(value)

        return True

    @staticmethod
    def _normalize_system_profile(normalize, data):
        if "system_profile" not in data:
            return data

        system_profile = deepcopy(data["system_profile"])
        normalize(system_profile)
        return {**data, "system_profile": system_profile}

    @staticmethod
    def build_model(data, facts, tags, tags_alt=None):
        return LimitedHost(
            display_name=data.get("display_name"),
            ansible_host=data.get("ansible_host"),
            account=data.get("account"),
            org_id=data.get("org_id"),
            facts=facts,
            tags=tags,
            tags_alt=tags_alt if tags_alt else [],
            system_profile_facts=data.get("system_profile", {}),
            groups=data.get("groups", []),
            insights_id=data.get("insights_id"),
            subscription_manager_id=data.get("subscription_manager_id"),
            satellite_id=data.get("satellite_id"),
            fqdn=data.get("fqdn"),
            bios_uuid=data.get("bios_uuid"),
            ip_addresses=data.get("ip_addresses"),
            mac_addresses=data.get("mac_addresses"),
            provider_id=data.get("provider_id"),
            provider_type=data.get("provider_type"),
            openshift_cluster_id=data.get("openshift_cluster_id"),
        )

    # Configuration for workload migration
    WORKLOAD_MIGRATION_CONFIG = {
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

    @staticmethod
    def _get_nested_value(data, path):
        """
        Navigate to a nested field using dot notation and return its value.

        Args:
            data: Dictionary to navigate
            path: Dot-separated path (e.g., "third_party_services.crowdstrike")

        Returns:
            The value at the path, or None if not found
        """
        parts = path.split(".")
        current = data

        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]

        return current

    @staticmethod
    def _remove_nested_field(data, path):
        """
        Remove a nested field and clean up empty parent objects.

        Args:
            data: Dictionary to remove from
            path: Dot-separated path (e.g., "third_party_services.crowdstrike")
        """
        parts = path.split(".")

        if len(parts) == 1:
            # Simple top-level field
            data.pop(parts[0], None)
        else:
            # Navigate to parent of the field to remove
            current = data
            for part in parts[:-1]:
                if not isinstance(current, dict) or part not in current:
                    return  # Path doesn't exist, nothing to remove
                current = current[part]

            # Remove the final nested field
            if isinstance(current, dict):
                current.pop(parts[-1], None)
                # Clean up empty parent objects
                if not current and len(parts) > 1:
                    data.pop(parts[0], None)

    @staticmethod
    def _detect_legacy_fields_for_workload(system_profile, config):
        """
        Detect legacy fields for a single workload type.

        Args:
            system_profile: System profile dictionary
            config: Configuration for this workload type

        Returns:
            List of detected legacy field names
        """
        detected = []

        # Check flat fields (SAP only)
        if "flat_fields" in config:
            for flat_field in config["flat_fields"]:
                if flat_field in system_profile:
                    detected.append(flat_field)

        # Check nested field
        if "nested_field" in config:
            nested_value = LimitedHostSchema._get_nested_value(system_profile, config["nested_field"])
            if isinstance(nested_value, dict):
                detected.append(config["nested_field"])

        return detected

    @staticmethod
    def _migrate_workload(system_profile, workloads, workload_type, config):
        """
        Migrate legacy fields for a single workload type to workloads.* structure.

        Args:
            system_profile: System profile dictionary
            workloads: Workloads dictionary to populate
            workload_type: Type of workload (e.g., 'sap', 'ansible')
            config: Migration configuration for this workload type
        """
        # Skip if workloads.{type} already exists (new format takes precedence)
        if workload_type in workloads:
            return

        migrated_data = {}

        # Migrate flat fields (SAP only)
        if "flat_fields" in config:
            for legacy_key, new_key in config["flat_fields"].items():
                if legacy_key in system_profile:
                    migrated_data[new_key] = system_profile[legacy_key]

        # Migrate nested field
        if "nested_field" in config:
            nested_value = LimitedHostSchema._get_nested_value(system_profile, config["nested_field"])
            if isinstance(nested_value, dict):
                if "nested_mapping" in config:
                    # Use explicit mapping (SAP)
                    for legacy_key, new_key in config["nested_mapping"].items():
                        if legacy_key in nested_value:
                            migrated_data[new_key] = nested_value[legacy_key]
                else:
                    # Copy entire nested object (Ansible, MSSQL, etc.)
                    # Use deepcopy to avoid unintended mutations of nested structures
                    migrated_data.update(deepcopy(nested_value))

        # Only add to workloads if we migrated any data
        if migrated_data:
            workloads[workload_type] = migrated_data

    @staticmethod
    def _remove_legacy_fields_for_workload(system_profile, config):
        """
        Remove legacy fields for a single workload type from system profile.

        Args:
            system_profile: System profile dictionary
            config: Configuration for this workload type
        """
        # Remove flat fields (SAP only)
        if "flat_fields" in config:
            for flat_field in config["flat_fields"]:
                system_profile.pop(flat_field, None)

        # Remove nested field
        if "nested_field" in config:
            LimitedHostSchema._remove_nested_field(system_profile, config["nested_field"])

    @staticmethod
    def _migrate_and_remove_legacy_workloads_fields(data):
        """
        Migrate legacy workloads fields to the new workloads.* structure, then remove legacy fields.

        This ensures backward compatibility while maintaining data consistency:
        1. If workloads.* exists, it takes precedence (reporters have migrated)
        2. If only legacy fields exist, migrate them to workloads.* (reporters haven't migrated yet)
        3. Remove all legacy fields to prevent duplication in the database

        Legacy fields handled:
        - SAP: sap_system, sap_sids, sap_instance_number, sap_version, sap.*
        - Ansible: ansible.*
        - InterSystems: intersystems.*
        - MSSQL: mssql.*
        - CrowdStrike: third_party_services.crowdstrike.*
        """
        if "system_profile" not in data or data["system_profile"] is None:
            return data

        system_profile = data["system_profile"]
        system_profile.setdefault("workloads", {})
        workloads = system_profile["workloads"]

        # Capture original workloads present BEFORE migration (for accurate logging)
        original_workloads_present = [
            f"workloads.{wtype}" for wtype in LimitedHostSchema.WORKLOAD_MIGRATION_CONFIG if wtype in workloads
        ]

        legacy_fields_detected = []

        # Single loop: detect, migrate, and remove for each workload type
        for workload_type, config in LimitedHostSchema.WORKLOAD_MIGRATION_CONFIG.items():
            # Detect legacy fields for this workload type
            detected = LimitedHostSchema._detect_legacy_fields_for_workload(system_profile, config)
            legacy_fields_detected.extend(detected)

            # Migrate legacy fields to workloads.* for this workload type
            LimitedHostSchema._migrate_workload(system_profile, workloads, workload_type, config)

            # Remove legacy fields for this workload type
            LimitedHostSchema._remove_legacy_fields_for_workload(system_profile, config)

        # Log if we detected any legacy fields
        if legacy_fields_detected:
            workloads_str = ", ".join(original_workloads_present) if original_workloads_present else "none"
            logger.info(
                f"Legacy workloads fields detected: reporter={data.get('reporter', 'unknown')}, "
                f"org_id={data.get('org_id', 'unknown')}, "
                f"display_name={data.get('display_name', 'unknown')}, "
                f"legacy_fields=[{', '.join(legacy_fields_detected)}], "
                f"legacy_count={len(legacy_fields_detected)}, "
                f"workloads_present=[{workloads_str}], "
                f"sending_both_formats={bool(original_workloads_present)}"
            )

        # Clean up empty workloads
        if not workloads:
            system_profile.pop("workloads")

        return data

    @pre_load
    def migrate_and_remove_legacy_workloads_fields(self, data, **kwargs):
        return self._migrate_and_remove_legacy_workloads_fields(data)

    @pre_load
    def coerce_system_profile_types(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.coerce_types, data)

    @post_load
    def filter_system_profile_keys(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.filter_keys, data)

    @validates("system_profile")
    def system_profile_is_valid(self, system_profile, data_key):  # noqa: ARG002, required for marshmallow validator functions
        try:
            jsonschema_validate(
                system_profile, self.system_profile_normalizer.schema, format_checker=Draft4Validator.FORMAT_CHECKER
            )
        except JsonSchemaValidationError as error:
            raise MarshmallowValidationError(f"System profile does not conform to schema.\n{error}") from error

        for dd_i, disk_device in enumerate(system_profile.get("disk_devices", [])):
            if not check_empty_keys(disk_device.get("options")):
                raise MarshmallowValidationError(f"Empty key in /system_profile/disk_devices/{dd_i}/options.")


class HostSchema(LimitedHostSchema):
    class Meta:
        unknown = EXCLUDE

    stale_timestamp = fields.AwareDateTime(required=False)
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))

    @staticmethod
    def build_model(data, facts, tags, tags_alt=None):
        if tags_alt is None:
            tags_alt = []
        return Host(
            data.get("display_name"),
            data.get("ansible_host"),
            data.get("account"),
            data.get("org_id"),
            facts,
            tags,
            tags_alt,
            data.get("system_profile", {}),
            data.get("stale_timestamp"),
            data["reporter"],
            data.get("groups", []),
            insights_id=data.get("insights_id"),
            subscription_manager_id=data.get("subscription_manager_id"),
            satellite_id=data.get("satellite_id"),
            fqdn=data.get("fqdn"),
            bios_uuid=data.get("bios_uuid"),
            ip_addresses=data.get("ip_addresses"),
            mac_addresses=data.get("mac_addresses"),
            provider_id=data.get("provider_id"),
            provider_type=data.get("provider_type"),
            openshift_cluster_id=data.get("openshift_cluster_id"),
        )


class PatchHostSchema(MarshmallowSchema):
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class HostIdListSchema(MarshmallowSchema):
    host_ids = fields.List(fields.Str(validate=verify_uuid_format), required=False)

    @validates("host_ids")
    def validate_host_ids(self, host_ids, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if host_ids is not None and len(host_ids) != len(set(host_ids)):
            raise MarshmallowValidationError("Host IDs must be unique.")


class RequiredHostIdListSchema(HostIdListSchema):
    host_ids = fields.List(fields.Str(validate=verify_uuid_format), required=True)

    @validates("host_ids")
    def validate_host_ids(self, host_ids, data_key):  # noqa: ARG002, required for marshmallow validator functions
        if len(host_ids) == 0:
            raise MarshmallowValidationError("Body content must be an array with system UUIDs, not an empty array")
        # Call parent validation for duplicate checking
        super().validate_host_ids(host_ids, data_key)


class InputGroupSchema(HostIdListSchema):
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=255))

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data:
            in_data["name"] = in_data["name"].strip()

        return in_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class StalenessData(TypedDict, total=False):
    """Type definition for validated staleness data.

    This mirrors the StalenessSchema fields and represents the structure
    returned by StalenessSchema.load(). All fields are optional (total=False)
    to support partial updates via PATCH requests.
    """

    conventional_time_to_stale: int
    conventional_time_to_stale_warning: int
    conventional_time_to_delete: int


class StalenessSchema(MarshmallowSchema):
    conventional_time_to_stale = fields.Integer(
        validate=marshmallow_validate.Range(min=1, max=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
    )
    conventional_time_to_stale_warning = fields.Integer(validate=marshmallow_validate.Range(min=1, max=15552000))
    conventional_time_to_delete = fields.Integer(validate=marshmallow_validate.Range(min=1, max=63072000))

    @validates_schema
    def validate_staleness(self, data, **kwargs):
        staleness_fields = ["time_to_stale", "time_to_stale_warning", "time_to_delete"]
        for i in range(len(staleness_fields) - 1):
            for j in range(i + 1, len(staleness_fields)):
                if (
                    data[(field_1 := f"conventional_{staleness_fields[i]}")]
                    >= data[(field_2 := f"conventional_{staleness_fields[j]}")]
                ):
                    raise MarshmallowValidationError(f"{field_1} must be lower than {field_2}")

    def load(self, data: dict[str, Any], **kwargs: Any) -> StalenessData:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Load and validate staleness data, returning typed StalenessData.

        Overrides parent to provide concrete return type for better IDE support.
        TypedDict is a structural type - the dict returned by parent load() already
        has the correct structure, this just annotates it properly for type checkers.
        """
        return super().load(data, **kwargs)  # pyright: ignore[reportReturnType]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class OutboxEventMetadataSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    local_resource_id = fields.Raw(validate=verify_uuid_format, required=True)
    api_href = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    console_href = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    reporter_version = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), required=True)
    transaction_id = fields.UUID(required=True)


class OutboxEventCommonSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    workspace_id = fields.Raw(validate=verify_uuid_format_not_empty_dict, allow_none=False, required=True)


class OutboxEventReporterSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    satellite_id = fields.Str(validate=verify_satellite_id, allow_none=True)
    subscription_manager_id = fields.Str(validate=verify_uuid_format, allow_none=True)
    insights_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    ansible_host = fields.Str(validate=marshmallow_validate.Length(max=255), allow_none=True)

    @validates_schema
    def validate_at_least_one_field(self, data, **kwargs):
        """Ensure at least one field has a non-none value."""
        fields_to_check = ["satellite_id", "subscription_manager_id", "insights_id", "ansible_host"]
        if all(data.get(field) is None for field in fields_to_check):
            raise MarshmallowValidationError("At least one field must have a non-none value")


class OutboxEventRepresentationsSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    metadata = fields.Nested(OutboxEventMetadataSchema, required=True)
    common = fields.Nested(OutboxEventCommonSchema, required=True)
    reporter = fields.Nested(OutboxEventReporterSchema, required=True)


class OutboxCreateUpdatePayloadSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    type = fields.Str(validate=marshmallow_validate.OneOf(["host"]), required=True)
    reporter_type = fields.Str(validate=marshmallow_validate.OneOf(["hbi"]), required=True)
    reporter_instance_id = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), required=True)
    representations = fields.Nested(OutboxEventRepresentationsSchema, required=True)


class OutboxDeleteReporterSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    type = fields.Str(validate=marshmallow_validate.OneOf(["HBI"]), required=True)


class OutboxDeleteReferenceSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    resource_type = fields.Str(validate=marshmallow_validate.OneOf(["host"]), required=True)
    resource_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    reporter = fields.Nested(OutboxDeleteReporterSchema, required=True)


class OutboxDeletePayloadSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    reference = fields.Nested(OutboxDeleteReferenceSchema, required=True)


class OutboxSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Raw(validate=verify_uuid_format, dump_only=True)
    aggregatetype = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), load_default="hbi.hosts")
    aggregateid = fields.Raw(validate=verify_uuid_format, required=True)
    operation = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), required=True)
    version = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), required=True)
    payload = fields.Raw(required=True)

    @validates_schema
    def validate_payload_with_operation(self, data, **kwargs):
        operation = data.get("operation")
        payload = data.get("payload")

        if operation and payload:
            if operation in ["created", "updated"]:
                OutboxCreateUpdatePayloadSchema().load(payload)
            elif operation == "delete":
                OutboxDeletePayloadSchema().load(payload)
            else:
                # Allow other operation types but still validate payload structure if it matches known patterns
                with contextlib.suppress(MarshmallowValidationError):
                    OutboxCreateUpdatePayloadSchema().load(payload)
                with contextlib.suppress(MarshmallowValidationError):
                    OutboxDeletePayloadSchema().load(payload)
                # If payload doesn't match either schema, that's okay for unknown operations

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# Generate HostStaticSystemProfileSchema dynamically from x-dynamic markers
_normalizer = SystemProfileNormalizer()
HostStaticSystemProfileSchema = _normalizer.create_static_schema()

# Generate HostDynamicSystemProfileSchema dynamically from x-dynamic markers
HostDynamicSystemProfileSchema = _normalizer.create_dynamic_schema()


# Application-specific data schemas for host app data (Unified Inventory Views)
# Based on host_app_events.spec.yaml OpenAPI specification
class AdvisorDataSchema(MarshmallowSchema):
    """Schema for Advisor application data."""

    recommendations = fields.Int(allow_none=True)
    incidents = fields.Int(allow_none=True)


class VulnerabilityDataSchema(MarshmallowSchema):
    """Schema for Vulnerability application data."""

    total_cves = fields.Int(allow_none=True)
    critical_cves = fields.Int(allow_none=True)
    high_severity_cves = fields.Int(allow_none=True)
    cves_with_security_rules = fields.Int(allow_none=True)
    cves_with_known_exploits = fields.Int(allow_none=True)


class PatchDataSchema(MarshmallowSchema):
    """Schema for Patch application data."""

    # Advisory counts by type (applicable)
    advisories_rhsa_applicable = fields.Int(allow_none=True)
    advisories_rhba_applicable = fields.Int(allow_none=True)
    advisories_rhea_applicable = fields.Int(allow_none=True)
    advisories_other_applicable = fields.Int(allow_none=True)

    # Advisory counts by type (installable)
    advisories_rhsa_installable = fields.Int(allow_none=True)
    advisories_rhba_installable = fields.Int(allow_none=True)
    advisories_rhea_installable = fields.Int(allow_none=True)
    advisories_other_installable = fields.Int(allow_none=True)

    # Package counts
    packages_applicable = fields.Int(allow_none=True)
    packages_installable = fields.Int(allow_none=True)
    packages_installed = fields.Int(allow_none=True)

    # Template info
    template_name = fields.Str(allow_none=True, validate=marshmallow_validate.Length(max=255))
    template_uuid = fields.UUID(allow_none=True)


class RemediationsDataSchema(MarshmallowSchema):
    """Schema for Remediations application data."""

    remediations_plans = fields.Int(allow_none=True)


class ComplianceDataPolicySchema(MarshmallowSchema):
    """Schema for a compliance policy entry."""

    id = fields.Str(validate=verify_uuid_format, allow_none=False)
    name = fields.Str(allow_none=False, validate=marshmallow_validate.Length(max=255))


class ComplianceDataSchema(MarshmallowSchema):
    """Schema for Compliance application data."""

    policies = fields.List(fields.Nested(ComplianceDataPolicySchema), allow_none=True)
    last_scan = fields.DateTime(allow_none=True)


class MalwareDataSchema(MarshmallowSchema):
    """Schema for Malware application data."""

    last_status = fields.Str(allow_none=True, validate=marshmallow_validate.Length(max=50))
    last_matches = fields.Int(allow_none=True)
    total_matches = fields.Int(allow_none=True)
    last_scan = fields.DateTime(allow_none=True)
