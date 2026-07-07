from copy import deepcopy
from functools import lru_cache

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema.validators import Draft4Validator
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
from app.models.schemas.common import BaseSchemaWithExclude
from app.models.system_profile_normalizer import SystemProfileNormalizer
from app.validators import check_empty_keys
from app.validators import verify_ip_address_format
from app.validators import verify_mac_address_format
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format


@lru_cache(maxsize=1)
def _get_schemas_package():
    """Lazy import of the schemas package (tests patch names on `app.models.schemas`)."""
    import app.models.schemas as pkg

    return pkg


class FactsSchema(MarshmallowSchema):
    namespace = fields.Str()
    facts = fields.Dict(validate=check_empty_keys)


class TagsSchema(BaseSchemaWithExclude):
    namespace = fields.Str(required=False, allow_none=True, validate=TAG_NAMESPACE_VALIDATION)
    key = fields.Str(required=True, allow_none=False, validate=TAG_KEY_VALIDATION)
    value = fields.Str(required=False, allow_none=True, validate=TAG_VALUE_VALIDATION)


class CanonicalFactsSchema(BaseSchemaWithExclude):
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
        _p = _get_schemas_package()

        return _p.LimitedHost(
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

    @pre_load
    def coerce_system_profile_types(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.coerce_types, data)

    @post_load
    def filter_system_profile_keys(self, data, **kwargs):
        return self._normalize_system_profile(self.system_profile_normalizer.filter_keys, data)

    @validates("system_profile")
    def system_profile_is_valid(self, system_profile, data_key):  # noqa: ARG002, required for marshmallow validator functions
        _p = _get_schemas_package()

        try:
            _p.jsonschema_validate(
                system_profile, self.system_profile_normalizer.schema, format_checker=Draft4Validator.FORMAT_CHECKER
            )
        except JsonSchemaValidationError as error:
            raise MarshmallowValidationError(f"System profile does not conform to schema.\n{error}") from error

        for dd_i, disk_device in enumerate(system_profile.get("disk_devices", [])):
            if not check_empty_keys(disk_device.get("options")):
                raise MarshmallowValidationError(f"Empty key in /system_profile/disk_devices/{dd_i}/options.")


class HostSchema(LimitedHostSchema):
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))

    @staticmethod
    def build_model(data, facts, tags, tags_alt=None):
        _p = _get_schemas_package()
        if tags_alt is None:
            tags_alt = []
        host = _p.Host(
            display_name=data.get("display_name"),
            ansible_host=data.get("ansible_host"),
            account=data.get("account"),
            org_id=data.get("org_id"),
            facts=facts,
            tags=tags,
            tags_alt=tags_alt,
            system_profile_facts=data.get("system_profile", {}),
            reporter=data["reporter"],
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

        return host


class PatchHostSchema(MarshmallowSchema):
    ansible_host = fields.Str(validate=marshmallow_validate.Length(min=0, max=255))
    display_name = fields.Str(validate=marshmallow_validate.Length(min=1, max=200))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
