from collections import namedtuple
from datetime import UTC
from enum import Enum
from os.path import join
from typing import Any

from connexion.utils import coerce_type
from jsonschema import RefResolver
from marshmallow import EXCLUDE
from marshmallow import Schema as MarshmallowSchema
from marshmallow import fields
from marshmallow import fields as marshmallow_fields
from marshmallow import validate as marshmallow_validate
from yaml import safe_load

from app.models.constants import SPECIFICATION_DIR
from app.models.constants import SYSTEM_PROFILE_SPECIFICATION_FILE
from app.validators import verify_uuid_format


class SystemProfileNormalizer:
    class Schema(namedtuple("Schema", ("type", "properties", "items"))):
        Types = Enum("Types", ("array", "object"))

        @classmethod
        def from_dict(cls, schema, resolver):
            if "$ref" in schema:
                _, schema = resolver.resolve(schema["$ref"])

            filtered = {key: schema.get(key) for key in cls._fields}
            return cls(**filtered)

        @property
        def schema_type(self):
            return self.Types.__members__.get(self.type)

    SOME_ARBITRARY_STRING = "property"

    def __init__(self, system_profile_schema=None):
        if system_profile_schema:
            system_profile_spec = system_profile_schema
        else:
            specification = join(SPECIFICATION_DIR, SYSTEM_PROFILE_SPECIFICATION_FILE)
            with open(specification) as file:
                system_profile_spec = safe_load(file)

        self.schema = {**system_profile_spec, "$ref": "#/$defs/SystemProfile"}
        self._resolver = RefResolver.from_schema(system_profile_spec)

    def filter_keys(self, payload, schema_dict=None):
        if schema_dict is None:
            schema_dict = self._system_profile_definition()

        schema_obj = self.Schema.from_dict(schema_dict, self._resolver)
        if schema_obj.schema_type == self.Schema.Types.object:
            self._object_filter(schema_obj, payload)
        elif schema_obj.schema_type == self.Schema.Types.array:
            self._array_filter(schema_obj, payload)

    def coerce_types(self, payload, schema_dict=None):
        if schema_dict is None:
            schema_dict = self._system_profile_definition()
        coerce_type(schema_dict, payload, self.SOME_ARBITRARY_STRING)

    def _system_profile_definition(self):
        return self.schema["$defs"]["SystemProfile"]

    def _object_filter(self, schema, payload):
        if not schema.properties or type(payload) is not dict:
            return

        for key in payload.keys() - schema.properties.keys():
            del payload[key]
        for key in payload:
            self.filter_keys(payload[key], schema.properties[key])

    def _array_filter(self, schema, payload):
        if not schema.items or type(payload) is not list:
            return

        for value in payload:
            self.filter_keys(value, schema.items)

    def get_dynamic_fields(self):
        """
        Extract field names that are marked with x-dynamic: true from the system profile schema.

        Returns:
            set: Field names that should be considered dynamic
        """
        # Get x-dynamic fields from schema
        schema_dynamic_fields = set()
        system_profile_def = self._system_profile_definition()
        self._extract_dynamic_fields(system_profile_def, schema_dynamic_fields, "")

        return schema_dynamic_fields

    def get_static_fields(self):
        """
        Extract field names that are NOT marked with x-dynamic: true from the system profile schema.
        Excludes legacy workloads fields that are in transition but not in any DB table.

        Returns:
            set: Field names that should be considered static
        """
        # Get all fields from schema
        all_fields = set()
        system_profile_def = self._system_profile_definition()
        self._extract_all_fields(system_profile_def, all_fields, "")

        # Get dynamic fields
        dynamic_fields = self.get_dynamic_fields()

        # Legacy workloads fields that are in transition (matches system_profile_transformer.py)
        # Note: rhel_ai and intersystems will be fixed in another branch
        excluded_workloads = {
            "ansible",
            "crowdstrike",
            "ibm_db2",
            "intersystems",
            "mssql",
            "oracle_db",
            "rhel_ai",
            "sap",
        }
        sap_fields = {"sap_system", "sap_sids", "sap_instance_number", "sap_version"}

        transitional_fields = excluded_workloads | sap_fields

        # Static fields = all fields - dynamic fields - transitional fields
        return all_fields - dynamic_fields - transitional_fields

    def _extract_dynamic_fields(self, schema_dict, dynamic_fields, field_path):
        """
        Extract top-level fields marked with x-dynamic: true.

        Args:
            schema_dict: Current schema definition
            dynamic_fields: Set to populate with dynamic field names
            field_path: Current field path for nested objects
        """
        if not isinstance(schema_dict, dict):
            return

        # Handle $ref resolution
        if "$ref" in schema_dict:
            _, resolved_schema = self._resolver.resolve(schema_dict["$ref"])
            schema_dict = resolved_schema

        # Only process top-level properties of SystemProfile
        if "properties" in schema_dict and not field_path:  # Only at top level
            for prop_name, prop_schema in schema_dict["properties"].items():
                if isinstance(prop_schema, dict):
                    # Handle $ref resolution for properties
                    if "$ref" in prop_schema:
                        _, resolved_prop = self._resolver.resolve(prop_schema["$ref"])
                        prop_schema = resolved_prop

                    # Check if this top-level field is marked as dynamic
                    if prop_schema.get("x-dynamic") is True:
                        dynamic_fields.add(prop_name)

    def _extract_all_fields(self, schema_dict, all_fields, field_path):
        """
        Extract all top-level field names from the system profile schema.

        Args:
            schema_dict: Current schema definition
            all_fields: Set to populate with all field names
            field_path: Current field path for nested objects
        """
        if not isinstance(schema_dict, dict):
            return

        # Handle $ref resolution
        if "$ref" in schema_dict:
            _, resolved_schema = self._resolver.resolve(schema_dict["$ref"])
            schema_dict = resolved_schema

        # Only process top-level properties of SystemProfile
        if "properties" in schema_dict and not field_path:  # Only at top level
            for prop_name, _prop_schema in schema_dict["properties"].items():
                # Add all top-level field names
                all_fields.add(prop_name)

    def _build_schema(self, field_names: set[str], class_name: str) -> type[MarshmallowSchema]:
        """
        Dynamically create a Marshmallow schema class from YAML field definitions.

        It build a schema class at runtime by converting YAML
        field specifications into Marshmallow field objects and assembling them
        into a new class using type().

        Args:
            field_names: Set of field names to include in the schema
            class_name: Name for the dynamically created schema class

        Returns:
            Dynamically generated Marshmallow schema class
        """
        schema_fields = {}
        root = self._system_profile_definition()

        for name in field_names:
            defn = self._get_field_definition(name, root)
            if defn:
                schema_fields[name] = self._create_marshmallow_field(defn)

        class Meta:
            unknown = EXCLUDE

        return type(class_name, (MarshmallowSchema,), {"Meta": Meta, **schema_fields})

    def create_dynamic_schema(self):
        return self._build_schema(self.get_dynamic_fields(), "HostDynamicSystemProfileSchema")

    def create_static_schema(self):
        return self._build_schema(self.get_static_fields(), "HostStaticSystemProfileSchema")

    def _get_field_definition(self, field_path: str, schema_dict: dict[str, Any]) -> dict[str, Any] | None:
        """
        Get the field definition for a given field path.

        Args:
            field_path: Field path (e.g., 'system_memory_bytes', 'operating_system.major')
            schema_dict: Schema definition dictionary

        Returns:
            Field definition dictionary or None if not found
        """
        parts = field_path.split(".")
        current = schema_dict

        for part in parts:
            if not isinstance(current, dict):
                return None

            # Handle $ref resolution
            if "$ref" in current:
                _, current = self._resolver.resolve(current["$ref"])

            if "properties" in current and part in current["properties"]:
                current = current["properties"][part]
            else:
                return None

        return current

    def _create_string_field(self, field_def: dict[str, Any]) -> fields.Field:
        """
        Create a Marshmallow string field from a YAML field definition.

        Args:
            field_def: YAML field definition dictionary

        Returns:
            Marshmallow string field instance
        """
        field_kwargs: dict[str, Any] = {"allow_none": True}
        validators = []

        # Handle special date-time format
        if field_def.get("format") == "date-time":
            return marshmallow_fields.AwareDateTime(allow_none=True, default_timezone=UTC)

        # Add length constraints
        if "maxLength" in field_def:
            validators.append(marshmallow_validate.Length(max=field_def["maxLength"]))
        if "minLength" in field_def:
            validators.append(marshmallow_validate.Length(min=field_def["minLength"]))

        # Add pattern validation for UUIDs
        if "pattern" in field_def:
            if field_def["pattern"].startswith("[0-9a-f]{8}-"):
                validators.append(verify_uuid_format)
            else:
                validators.append(marshmallow_validate.Regexp(field_def["pattern"]))

        # Handle enum validation with nullable support
        if "enum" in field_def:
            enum_choices = field_def["enum"]
            # If None is in enum, filter out None for validation
            # since allow_none=True already handles None values
            if None in enum_choices:
                enum_choices = [choice for choice in enum_choices if choice is not None]
            if enum_choices:  # Only add validator if there are non-None choices
                validators.append(marshmallow_validate.OneOf(enum_choices))

        if validators:
            field_kwargs["validate"] = validators

        return fields.Str(**field_kwargs)

    def _create_integer_field(self, field_def: dict[str, Any]) -> fields.Field:
        """
        Create a Marshmallow integer field from a YAML field definition.

        Args:
            field_def: YAML field definition dictionary

        Returns:
            Marshmallow integer field instance
        """
        field_kwargs: dict[str, Any] = {"allow_none": True}
        validators = []

        if "minimum" in field_def or "maximum" in field_def:
            validators.append(
                marshmallow_validate.Range(min=field_def.get("minimum", 0), max=field_def.get("maximum", 2147483647))
            )

        if validators:
            field_kwargs["validate"] = validators

        return fields.Int(**field_kwargs)

    def _create_array_field(self, field_def: dict[str, Any]) -> fields.Field:
        """
        Create a Marshmallow array field from a YAML field definition.

        Args:
            field_def: YAML field definition dictionary

        Returns:
            Marshmallow array field instance
        """
        field_kwargs: dict[str, Any] = {"allow_none": True}

        if "items" in field_def:
            # Handle special nested schema cases
            items_def = field_def["items"]
            if "$ref" in items_def:
                nested_field = self._create_nested_schema_field(items_def["$ref"], field_kwargs)
                if nested_field:
                    return nested_field

            # Default to generic field
            item_field = self._create_marshmallow_field(field_def["items"])
            return fields.List(item_field, **field_kwargs)
        else:
            return fields.List(fields.Str(), **field_kwargs)

    def _create_nested_schema_field(self, ref_path: str, field_kwargs: dict[str, Any]) -> fields.Field | None:
        """
        Create a nested schema field based on the reference path.

        Args:
            ref_path: Reference path to the schema definition
            field_kwargs: Field keyword arguments

        Returns:
            Marshmallow nested field instance or None if not a known schema
        """
        ref_name = ref_path.split("/")[-1]

        schema_map = {
            "NetworkInterface": "NetworkInterfaceSchema",
            "InstalledProduct": "InstalledProductSchema",
            "DiskDevice": "DiskDeviceSchema",
            "DnfModule": "DnfModuleSchema",
            "YumRepo": "YumRepoSchema",
        }

        if ref_name in schema_map:
            from app.models.schemas import DiskDeviceSchema
            from app.models.schemas import DnfModuleSchema
            from app.models.schemas import InstalledProductSchema
            from app.models.schemas import NetworkInterfaceSchema
            from app.models.schemas import YumRepoSchema

            schema_classes = {
                "NetworkInterfaceSchema": NetworkInterfaceSchema,
                "InstalledProductSchema": InstalledProductSchema,
                "DiskDeviceSchema": DiskDeviceSchema,
                "DnfModuleSchema": DnfModuleSchema,
                "YumRepoSchema": YumRepoSchema,
            }

            schema_class = schema_classes[schema_map[ref_name]]
            return fields.List(fields.Nested(schema_class), **field_kwargs)

        return None

    def _create_object_field(self, field_def: dict[str, Any]) -> fields.Field:
        """
        Create a Marshmallow object field from a YAML field definition.

        Args:
            field_def: YAML field definition dictionary

        Returns:
            Marshmallow object field instance
        """
        field_kwargs: dict[str, Any] = {"allow_none": True}

        # Handle special nested object schemas
        if "properties" in field_def:
            # Check for specific known object types
            properties = field_def["properties"]
            if all(key in properties for key in ["major", "minor", "name"]):
                # This looks like OperatingSystem schema
                from app.models.schemas import OperatingSystemSchema

                return fields.Nested(OperatingSystemSchema, **field_kwargs)
            elif all(key in properties for key in ["version", "environment_ids"]):
                # This looks like Rhsm schema
                from app.models.schemas import RhsmSchema

                return fields.Nested(RhsmSchema, **field_kwargs)

        return fields.Dict(**field_kwargs)

    def _create_marshmallow_field(self, field_def: dict[str, Any]) -> fields.Field:
        """
        Create a Marshmallow field from a YAML field definition.

        Args:
            field_def: YAML field definition dictionary

        Returns:
            Marshmallow field instance
        """
        # Handle $ref resolution
        if "$ref" in field_def:
            _, field_def = self._resolver.resolve(field_def["$ref"])

        field_type = field_def.get("type")

        if field_type == "string":
            return self._create_string_field(field_def)
        elif field_type == "integer":
            return self._create_integer_field(field_def)
        elif field_type == "boolean":
            return fields.Bool(allow_none=True)
        elif field_type == "array":
            return self._create_array_field(field_def)
        elif field_type == "object":
            return self._create_object_field(field_def)
        else:
            # Default to Raw field for unknown types
            return fields.Raw(allow_none=True)
