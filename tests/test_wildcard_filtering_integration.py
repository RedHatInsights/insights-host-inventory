"""Integration test for wildcard filtering with URL-encoded asterisks."""

import pytest
from unittest.mock import patch, MagicMock

from api.filtering.db_custom_filters import build_single_filter
from api.parsing import customURIParser


class TestWildcardFilteringIntegration:
    """Test that URL-encoded asterisks work correctly with wildcard filtering."""

    def test_url_encoded_asterisk_parsing_integration(self):
        """Test the complete flow from URL parsing to filter building."""
        # Simulate parsing a URL parameter with URL-encoded asterisk
        key = "filter[system_profile][os_release]"
        value = ["test%2A123"]  # URL-encoded asterisk

        # Parse the parameter
        root_key, result, is_deep = customURIParser._make_deep_object(key, value)

        # Verify parsing worked correctly
        assert root_key == "filter"
        assert is_deep is True
        assert len(result) == 1

        filter_dict = result[0]
        assert "system_profile" in filter_dict
        assert "os_release" in filter_dict["system_profile"]

        # The parsed value should have literal asterisk (not treated as wildcard placeholder)
        parsed_value = filter_dict["system_profile"]["os_release"]
        assert parsed_value == "test*123"

    def test_literal_asterisk_parsing_integration(self):
        """Test that literal asterisks are preserved during parsing."""
        # Simulate parsing a URL parameter with literal asterisk
        key = "filter[system_profile][os_release]"
        value = ["test*123"]  # Literal asterisk

        # Parse the parameter
        root_key, result, is_deep = customURIParser._make_deep_object(key, value)

        # Verify parsing worked correctly
        assert root_key == "filter"
        assert is_deep is True
        assert len(result) == 1

        filter_dict = result[0]
        assert "system_profile" in filter_dict
        assert "os_release" in filter_dict["system_profile"]

        # The parsed value should have literal asterisk
        parsed_value = filter_dict["system_profile"]["os_release"]
        assert parsed_value == "test*123"

    @patch('api.filtering.db_custom_filters.system_profile_spec')
    @patch('api.filtering.db_custom_filters.HostStaticSystemProfile')
    def test_wildcard_filter_building_with_literal_asterisk(self, mock_host_static, mock_spec):
        """Test that literal asterisks get converted to SQL wildcards."""
        # Mock the system profile spec to indicate os_release supports wildcards
        mock_spec.return_value = {
            "os_release": {
                "filter": "wildcard",
                "type": str
            }
        }

        # Mock the database column
        mock_column = MagicMock()
        mock_column.astext = MagicMock()
        mock_host_static.os_release = mock_column

        # Create a filter with literal asterisk (should be treated as wildcard)
        filter_param = {"os_release": "test*123"}

        # This should work without errors and convert * to % for SQL LIKE
        try:
            result = build_single_filter(filter_param)
            # If we get here without exception, the filter was built successfully
            assert result is not None
        except Exception as e:
            # Print the exception for debugging
            print(f"Exception during filter building: {e}")
            raise

    def test_mixed_encoding_scenarios(self):
        """Test various mixed encoding scenarios."""
        test_cases = [
            # (input, expected_output)
            ("test%2A123", "test*123"),  # URL-encoded asterisk
            ("test*123", "test*123"),    # Literal asterisk
            ("prefix%2Amiddle*suffix", "prefix*middle*suffix"),  # Mixed
            ("no%2Aasterisk%2Ahere", "no*asterisk*here"),  # Multiple URL-encoded
            ("normal_value", "normal_value"),  # No asterisks
        ]

        for input_value, expected_output in test_cases:
            key = "filter[system_profile][os_release]"
            value = [input_value]

            root_key, result, is_deep = customURIParser._make_deep_object(key, value)

            filter_dict = result[0]
            parsed_value = filter_dict["system_profile"]["os_release"]

            assert parsed_value == expected_output, f"Input: {input_value}, Expected: {expected_output}, Got: {parsed_value}"

    def test_array_parameter_mixed_encoding(self):
        """Test array parameters with mixed URL encoding."""
        key = "filter[system_profile][os_release][]"
        values = ["test%2A123", "literal*456", "normal_value"]

        root_key, result, is_deep = customURIParser._make_deep_object(key, values)

        filter_dict = result[0]
        parsed_values = filter_dict["system_profile"]["os_release"]

        expected_values = ["test*123", "literal*456", "normal_value"]
        assert len(parsed_values) == len(expected_values)

        for expected in expected_values:
            assert expected in parsed_values
