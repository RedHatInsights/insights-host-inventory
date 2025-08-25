import contextlib
from copy import deepcopy
from datetime import UTC

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
                from app.models import logger

                logger.warning(f"Zero MAC address reported by: {data.get('reporter', 'Not Available')}")
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
    def build_model(data, canonical_facts, facts, tags, tags_alt=None):
        return LimitedHost(
            canonical_facts=canonical_facts,
            display_name=data.get("display_name"),
            ansible_host=data.get("ansible_host"),
            account=data.get("account"),
            org_id=data.get("org_id"),
            facts=facts,
            tags=tags,
            tags_alt=tags_alt if tags_alt else [],
            system_profile_facts=data.get("system_profile", {}),
            groups=data.get("groups", []),
            insights_id=canonical_facts.get("insights_id"),
            subscription_manager_id=canonical_facts.get("subscription_manager_id"),
            satellite_id=canonical_facts.get("satellite_id"),
            fqdn=canonical_facts.get("fqdn"),
            bios_uuid=canonical_facts.get("bios_uuid"),
            ip_addresses=canonical_facts.get("ip_addresses"),
            mac_addresses=canonical_facts.get("mac_addresses"),
            provider_id=canonical_facts.get("provider_id"),
            provider_type=canonical_facts.get("provider_type"),
        )

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

    stale_timestamp = fields.AwareDateTime(required=True)
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))

    @staticmethod
    def build_model(data, canonical_facts, facts, tags, tags_alt=None):
        if tags_alt is None:
            tags_alt = []
        return Host(
            canonical_facts,
            data.get("display_name"),
            data.get("ansible_host"),
            data.get("account"),
            data.get("org_id"),
            facts,
            tags,
            tags_alt,
            data.get("system_profile", {}),
            data["stale_timestamp"],
            data["reporter"],
            data.get("groups", []),
            insights_id=canonical_facts.get("insights_id"),
            subscription_manager_id=canonical_facts.get("subscription_manager_id"),
            satellite_id=canonical_facts.get("satellite_id"),
            fqdn=canonical_facts.get("fqdn"),
            bios_uuid=canonical_facts.get("bios_uuid"),
            ip_addresses=canonical_facts.get("ip_addresses"),
            mac_addresses=canonical_facts.get("mac_addresses"),
            provider_id=canonical_facts.get("provider_id"),
            provider_type=canonical_facts.get("provider_type"),
        )


class PatchHostSchema(MarshmallowSchema):
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class InputGroupSchema(MarshmallowSchema):
    name = fields.Str(validate=marshmallow_validate.Length(min=1, max=255))
    host_ids = fields.List(fields.Str(validate=verify_uuid_format))

    @pre_load
    def strip_whitespace_from_name(self, in_data, **kwargs):
        if "name" in in_data:
            in_data["name"] = in_data["name"].strip()

        return in_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class StalenessSchema(MarshmallowSchema):
    conventional_time_to_stale = fields.Integer(validate=marshmallow_validate.Range(min=1, max=604800))
    conventional_time_to_stale_warning = fields.Integer(validate=marshmallow_validate.Range(min=1, max=15552000))
    conventional_time_to_delete = fields.Integer(validate=marshmallow_validate.Range(min=1, max=63072000))
    immutable_time_to_stale = fields.Integer(validate=marshmallow_validate.Range(min=1, max=604800))
    immutable_time_to_stale_warning = fields.Integer(validate=marshmallow_validate.Range(min=1, max=15552000))
    immutable_time_to_delete = fields.Integer(validate=marshmallow_validate.Range(min=1, max=63072000))

    @validates_schema
    def validate_staleness(self, data, **kwargs):
        staleness_fields = ["time_to_stale", "time_to_stale_warning", "time_to_delete"]
        for host_type in (
            "conventional",
            "immutable",
        ):
            for i in range(len(staleness_fields) - 1):
                for j in range(i + 1, len(staleness_fields)):
                    if (
                        data[(field_1 := f"{host_type}_{staleness_fields[i]}")]
                        >= data[(field_2 := f"{host_type}_{staleness_fields[j]}")]
                    ):
                        raise MarshmallowValidationError(f"{field_1} must be lower than {field_2}")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class OutboxEventMetadataSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    localResourceId = fields.Raw(validate=verify_uuid_format, required=True)
    apiHref = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    consoleHref = fields.Str(validate=marshmallow_validate.Length(min=1, max=2048), required=True)
    reporterVersion = fields.Str(validate=marshmallow_validate.Length(min=1, max=50), required=True)


class OutboxEventCommonSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    workspace_id = fields.Raw(validate=verify_uuid_format, allow_none=True)


class OutboxEventReporterSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    satellite_id = fields.Str(validate=verify_satellite_id, allow_none=True)
    subscription_manager_id = fields.Str(validate=verify_uuid_format, allow_none=True)
    insights_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    ansible_host = fields.Str(validate=marshmallow_validate.Length(max=255), allow_none=True)


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
    reporterType = fields.Str(validate=marshmallow_validate.OneOf(["hbi"]), required=True)
    reporterInstanceId = fields.Str(validate=marshmallow_validate.Length(min=1, max=255), required=True)
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
            elif operation == "deleted":
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


class HostStaticSystemProfileSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    arch = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    basearch = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    bios_release_date = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    bios_vendor = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    bios_version = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    bootc_status = fields.Dict(allow_none=True)
    cloud_provider = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    conversions = fields.Dict(allow_none=True)
    cores_per_socket = fields.Int(validate=marshmallow_validate.Range(min=0, max=2147483647), allow_none=True)
    cpu_model = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    disk_devices = fields.List(fields.Nested(DiskDeviceSchema), allow_none=True)
    dnf_modules = fields.List(fields.Nested(DnfModuleSchema), allow_none=True)
    enabled_services = fields.List(fields.Str(validate=marshmallow_validate.Length(max=512)), allow_none=True)
    gpg_pubkeys = fields.List(fields.Str(validate=marshmallow_validate.Length(max=512)), allow_none=True)
    greenboot_fallback_detected = fields.Bool(allow_none=True)
    greenboot_status = fields.Str(validate=marshmallow_validate.Length(max=5), allow_none=True)
    host_type = fields.Str(validate=marshmallow_validate.Length(max=4), allow_none=True)
    image_builder = fields.Dict(allow_none=True)
    infrastructure_type = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    infrastructure_vendor = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    insights_client_version = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    installed_packages_delta = fields.List(fields.Str(validate=marshmallow_validate.Length(max=512)), allow_none=True)
    installed_services = fields.List(fields.Str(validate=marshmallow_validate.Length(max=512)), allow_none=True)
    intersystems = fields.Dict(allow_none=True)
    is_marketplace = fields.Bool(allow_none=True)
    katello_agent_running = fields.Bool(allow_none=True)
    number_of_cpus = fields.Int(validate=marshmallow_validate.Range(min=0, max=2147483647), allow_none=True)
    number_of_sockets = fields.Int(validate=marshmallow_validate.Range(min=0, max=2147483647), allow_none=True)
    operating_system = fields.Nested(OperatingSystemSchema, allow_none=True)
    os_kernel_version = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    os_release = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    owner_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    public_dns = fields.List(fields.Str(validate=marshmallow_validate.Length(max=100)), allow_none=True)
    public_ipv4_addresses = fields.List(fields.Str(validate=marshmallow_validate.Length(max=15)), allow_none=True)
    releasever = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    rhc_client_id = fields.Raw(validate=verify_uuid_format, allow_none=True)
    rhc_config_state = fields.Raw(validate=verify_uuid_format, allow_none=True)
    rhel_ai = fields.Dict(allow_none=True)
    rhsm = fields.Nested(RhsmSchema, allow_none=True)
    rpm_ostree_deployments = fields.List(fields.Dict(), allow_none=True)
    satellite_managed = fields.Bool(allow_none=True)
    selinux_config_file = fields.Str(validate=marshmallow_validate.Length(max=128), allow_none=True)
    selinux_current_mode = fields.Str(validate=marshmallow_validate.Length(max=10), allow_none=True)
    subscription_auto_attach = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    subscription_status = fields.Str(validate=marshmallow_validate.Length(max=100), allow_none=True)
    system_purpose = fields.Dict(allow_none=True)
    system_update_method = fields.Str(validate=marshmallow_validate.Length(max=10), allow_none=True)
    third_party_services = fields.Dict(allow_none=True)
    threads_per_core = fields.Int(validate=marshmallow_validate.Range(min=0, max=2147483647), allow_none=True)
    tuned_profile = fields.Str(validate=marshmallow_validate.Length(max=256), allow_none=True)
    virtual_host_uuid = fields.Raw(validate=verify_uuid_format, allow_none=True)
    yum_repos = fields.List(fields.Nested(YumRepoSchema), allow_none=True)


class HostDynamicSystemProfileSchema(MarshmallowSchema):
    class Meta:
        unknown = EXCLUDE

    captured_date = fields.AwareDateTime(allow_none=True, default_timezone=UTC)
    running_processes = fields.List(fields.Str(), allow_none=True)
    last_boot_time = fields.AwareDateTime(allow_none=True, default_timezone=UTC)
    installed_packages = fields.List(fields.Str(), allow_none=True)
    network_interfaces = fields.List(fields.Nested(NetworkInterfaceSchema), allow_none=True)
    installed_products = fields.List(fields.Nested(InstalledProductSchema), allow_none=True)
    cpu_flags = fields.List(fields.Str(), allow_none=True)
    insights_egg_version = fields.Str(validate=marshmallow_validate.Length(max=50), allow_none=True)
    kernel_modules = fields.List(fields.Str(), allow_none=True)
    system_memory_bytes = fields.Int(allow_none=True)
    systemd = fields.Dict(allow_none=True)
    workloads = fields.Dict(allow_none=True)
