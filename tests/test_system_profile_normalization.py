from unittest import TestCase

from marshmallow import Schema as MarshmallowSchema
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import fields as marshmallow_fields

from app.models.system_profile_normalizer import SystemProfileNormalizer
from app.models.system_profile_normalizer import _TruncatingList
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


class TruncatingListTestCase(TestCase):
    """Tests for `_TruncatingList` / `_create_array_field` maxItems enforcement.

    Covers the java_purls array which declares `maxItems: 2048` and per-item
    `maxLength: 512` in the system_profile spec. An unbounded array can push a
    host event past the ~1MB Kafka ceiling (where oversized events are silently
    dropped), so the normalizer truncates server-side instead of rejecting the
    host.
    """

    # java_purls declares maxItems; installed_packages does not (control field).
    MAX_ITEMS = 2048
    ITEM_MAX_LENGTH = 512

    def _make_schema(self):
        mock_schema = {
            "$defs": {
                "SystemProfile": {
                    "type": "object",
                    "properties": {
                        "java_purls": {
                            "type": "array",
                            "maxItems": self.MAX_ITEMS,
                            "items": {"type": "string", "maxLength": self.ITEM_MAX_LENGTH},
                        },
                        # No maxItems -> should stay a plain list, never truncated.
                        "installed_packages": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": self.ITEM_MAX_LENGTH},
                        },
                    },
                }
            }
        }
        normalizer = SystemProfileNormalizer(system_profile_schema=mock_schema)
        schema_class = normalizer._build_schema({"java_purls", "installed_packages"}, "TestSchema")
        return schema_class()

    @staticmethod
    def _purls(count):
        return [f"pkg:maven/org.example/lib{i}@1.0.{i}" for i in range(count)]

    def test_field_types(self):
        """maxItems -> _TruncatingList; no maxItems -> plain marshmallow List."""
        schema = self._make_schema()
        self.assertIsInstance(schema.fields["java_purls"], _TruncatingList)
        self.assertEqual(schema.fields["java_purls"].max_items, self.MAX_ITEMS)
        self.assertIsInstance(schema.fields["installed_packages"], marshmallow_fields.List)
        self.assertNotIsInstance(schema.fields["installed_packages"], _TruncatingList)

    def test_truncates_over_max_items(self):
        """An over-max java_purls array is truncated to exactly maxItems, order preserved."""
        schema = self._make_schema()
        purls = self._purls(self.MAX_ITEMS + 52)  # 2100
        result = schema.load({"java_purls": purls})
        self.assertEqual(len(result["java_purls"]), self.MAX_ITEMS)
        self.assertEqual(result["java_purls"], purls[: self.MAX_ITEMS])

    def test_exactly_max_items_kept(self):
        """Exactly maxItems items are kept unchanged (boundary)."""
        schema = self._make_schema()
        purls = self._purls(self.MAX_ITEMS)
        result = schema.load({"java_purls": purls})
        self.assertEqual(result["java_purls"], purls)

    def test_short_array_intact(self):
        """A small valid array passes through untouched."""
        schema = self._make_schema()
        purls = self._purls(10)
        result = schema.load({"java_purls": purls})
        self.assertEqual(result["java_purls"], purls)

    def test_item_maxlength_still_applies(self):
        """Per-item maxLength validation is still enforced by the truncating field."""
        schema = self._make_schema()
        with self.assertRaises(MarshmallowValidationError):
            schema.load({"java_purls": ["x" * (self.ITEM_MAX_LENGTH + 1)]})

    def test_none_allowed(self):
        """None is allowed (allow_none) and not treated as an over-limit value."""
        schema = self._make_schema()
        result = schema.load({"java_purls": None})
        self.assertIsNone(result["java_purls"])

    def test_other_array_without_max_items_not_truncated(self):
        """A sibling array without maxItems is never truncated."""
        schema = self._make_schema()
        packages = [f"pkg-{i}" for i in range(self.MAX_ITEMS + 1000)]
        result = schema.load({"installed_packages": packages})
        self.assertEqual(len(result["installed_packages"]), len(packages))
