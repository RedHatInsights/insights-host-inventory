from unittest import TestCase

from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError

from app.models.system_profile_normalizer import SystemProfileNormalizer
from app.models.system_profile_transformer import split_system_profile_data
from tests.helpers.test_utils import get_sample_dynamic_profile_data
from tests.helpers.test_utils import get_sample_profile_data
from tests.helpers.test_utils import get_sample_static_profile_data


class TestSystemProfileTransformer:
    """Test the system profile transformation utilities."""

    def test_split_system_profile_data_empty(self):
        """Test splitting empty system profile data."""
        static, dynamic = split_system_profile_data({})
        assert static == {}
        assert dynamic == {}

    def test_split_system_profile_data_static_only(self):
        """Test splitting system profile data with only static fields."""
        input_data = get_sample_static_profile_data()

        static, dynamic = split_system_profile_data(input_data)

        assert static == input_data
        assert dynamic == {}

    def test_split_system_profile_data_dynamic_only(self):
        """Test splitting system profile data with only dynamic fields."""
        input_data = get_sample_dynamic_profile_data()

        static, dynamic = split_system_profile_data(input_data)

        assert static == {}
        assert dynamic == input_data

    def test_split_system_profile_data_mixed(self):
        """Test splitting system profile data with mixed fields."""
        input_static, input_dynamic = get_sample_profile_data()

        static, dynamic = split_system_profile_data(input_static | input_dynamic)

        expected_static = input_static
        expected_dynamic = input_dynamic

        assert static == expected_static
        assert dynamic == expected_dynamic


class ModelsSystemProfileNormalizerBuildSchemaTestCase(TestCase):
    def test_build_schema_creates_valid_marshmallow_schema(self):
        """Test that _build_schema creates a working Marshmallow schema from mock YAML spec."""
        # Mock system profile schema definition
        mock_schema = {
            "$defs": {
                "SystemProfile": {
                    "type": "object",
                    "properties": {
                        "cpu_count": {"type": "integer", "minimum": 1, "maximum": 1024},
                        "memory_gb": {"type": "integer", "minimum": 1},
                        "hostname": {"type": "string", "maxLength": 255},
                        "is_virtual": {"type": "boolean"},
                    },
                }
            }
        }

        # Create normalizer with mock schema
        normalizer = SystemProfileNormalizer(system_profile_schema=mock_schema)

        # Test field names to include in schema
        field_names = {"cpu_count", "hostname", "is_virtual"}

        # Build the schema
        schema_class = normalizer._build_schema(field_names, "TestSchema")

        # Verify the schema class was created correctly
        self.assertEqual(schema_class.__name__, "TestSchema")
        self.assertTrue(issubclass(schema_class, MarshmallowSchema))

        # Create an instance of the schema
        schema_instance = schema_class()

        # Test valid data validation
        valid_data = {"cpu_count": 4, "hostname": "test-server", "is_virtual": True}
        result = schema_instance.load(valid_data)
        self.assertEqual(result, valid_data)

        # Test validation with None values (should be allowed)
        none_data = {"cpu_count": None, "hostname": None, "is_virtual": None}
        result = schema_instance.load(none_data)
        self.assertEqual(result, none_data)

        # Test that unknown fields are excluded (EXCLUDE behavior)
        data_with_unknown = {"cpu_count": 8, "hostname": "server", "unknown_field": "should_be_excluded"}
        result = schema_instance.load(data_with_unknown)
        expected = {"cpu_count": 8, "hostname": "server"}
        self.assertEqual(result, expected)

        # Test validation errors for invalid data
        with self.assertRaises(MarshmallowValidationError):
            schema_instance.load({"cpu_count": -1})  # Below minimum

        with self.assertRaises(MarshmallowValidationError):
            schema_instance.load({"cpu_count": 2000})  # Above maximum

        with self.assertRaises(MarshmallowValidationError):
            schema_instance.load({"hostname": "x" * 300})  # Too long

        with self.assertRaises(MarshmallowValidationError):
            schema_instance.load({"is_virtual": "not-a-boolean"})
