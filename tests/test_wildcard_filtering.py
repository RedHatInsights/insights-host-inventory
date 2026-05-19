"""
Tests for wildcard filtering with URL-encoded asterisks (RHINENG-4809).

This module tests the fix for the issue where URL-encoded wildcards (%2A)
were being treated as actual wildcards when they should be treated as literal asterisk characters.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

from api.filtering.wildcard_utils import _contains_encoded_asterisk
from api.filtering.wildcard_utils import _extract_filter_value_from_raw_query
from api.filtering.wildcard_utils import _replace_encoded_asterisks_with_marker
from api.filtering.wildcard_utils import prepare_wildcard_value_for_sql
from api.filtering.wildcard_utils import process_wildcard_value


class TestWildcardUtils:
    """Test the wildcard utility functions."""

    def test_extract_filter_value_from_raw_query(self):
        """Test extracting filter values from raw query strings."""
        raw_query = "filter[system_profile][os_release]=abc%2A123&other=value"
        field_path = "filter[system_profile][os_release]"

        result = _extract_filter_value_from_raw_query(field_path, raw_query)
        assert result == "abc%2A123"

    def test_extract_filter_value_with_array_notation(self):
        """Test extracting filter values with array notation []."""
        raw_query = "filter[system_profile][os_release][]=abc%2A123"
        field_path = "filter[system_profile][os_release]"

        result = _extract_filter_value_from_raw_query(field_path, raw_query)
        assert result == "abc%2A123"

    def test_extract_filter_value_not_found(self):
        """Test extracting filter values when field is not found."""
        raw_query = "filter[system_profile][other_field]=value"
        field_path = "filter[system_profile][os_release]"

        result = _extract_filter_value_from_raw_query(field_path, raw_query)
        assert result is None

    def test_contains_encoded_asterisk_uppercase(self):
        """Test detecting URL-encoded asterisks (uppercase)."""
        assert _contains_encoded_asterisk("abc%2A123") is True
        assert _contains_encoded_asterisk("abc*123") is False
        assert _contains_encoded_asterisk("abc%2Adef%2A") is True

    def test_contains_encoded_asterisk_lowercase(self):
        """Test detecting URL-encoded asterisks (lowercase)."""
        assert _contains_encoded_asterisk("abc%2a123") is True
        assert _contains_encoded_asterisk("abc%2adef%2a") is True

    def test_contains_encoded_asterisk_mixed(self):
        """Test detecting URL-encoded asterisks (mixed case)."""
        assert _contains_encoded_asterisk("abc%2Adef%2a") is True

    def test_replace_encoded_asterisks_with_marker(self):
        """Test replacing URL-encoded asterisks with markers."""
        raw_value = "abc%2A123%2adef"

        result = _replace_encoded_asterisks_with_marker(raw_value)

        # The result should have markers where the encoded asterisks were
        assert "\x00ENCODED_ASTERISK\x00" in result
        assert result.count("\x00ENCODED_ASTERISK\x00") == 2

    def test_prepare_wildcard_value_for_sql_with_wildcards(self):
        """Test preparing values with both wildcards and literal asterisks for SQL."""
        # Value with both wildcard * and encoded asterisk marker
        value = "abc*def\x00ENCODED_ASTERISK\x00ghi"

        result = prepare_wildcard_value_for_sql(value)

        # Wildcard * should become %, encoded asterisk should become literal *
        assert result == "abc%def*ghi"

    def test_prepare_wildcard_value_for_sql_only_wildcards(self):
        """Test preparing values with only wildcards for SQL."""
        value = "abc*def*ghi"

        result = prepare_wildcard_value_for_sql(value)

        # All * should become %
        assert result == "abc%def%ghi"

    def test_prepare_wildcard_value_for_sql_only_literals(self):
        """Test preparing values with only literal asterisks for SQL."""
        value = "abc\x00ENCODED_ASTERISK\x00def\x00ENCODED_ASTERISK\x00ghi"

        result = prepare_wildcard_value_for_sql(value)

        # All encoded asterisks should become literal *
        assert result == "abc*def*ghi"

    def test_process_wildcard_value_with_encoded_asterisk(self):
        """Test processing wildcard values when URL-encoded asterisks are present."""
        # Mock Flask module and request
        mock_flask = MagicMock()
        mock_request = MagicMock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc%2A123"}
        mock_flask.request = mock_request

        with patch("api.filtering.wildcard_utils.flask", mock_flask):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "abc*123"

            result = process_wildcard_value(field_path, decoded_value)

            # The result should contain the encoded asterisk marker
            assert "\x00ENCODED_ASTERISK\x00" in result

    def test_process_wildcard_value_with_regular_wildcard(self):
        """Test processing wildcard values when regular wildcards are present."""
        # Mock Flask module and request
        mock_flask = MagicMock()
        mock_request = MagicMock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc*123"}
        mock_flask.request = mock_request

        with patch("api.filtering.wildcard_utils.flask", mock_flask):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "abc*123"

            result = process_wildcard_value(field_path, decoded_value)

            # The result should be unchanged (no encoded asterisk marker)
            assert result == "abc*123"
            assert "\x00ENCODED_ASTERISK\x00" not in result

    def test_process_wildcard_value_no_flask_context(self):
        """Test processing wildcard values when no Flask context is available."""
        # Mock Flask to raise RuntimeError when accessing request
        mock_flask = MagicMock()
        mock_flask.request = MagicMock(side_effect=RuntimeError("Working outside of request context"))

        with patch("api.filtering.wildcard_utils.flask", mock_flask):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "abc*123"

            # This should not raise an exception and should return the original value
            result = process_wildcard_value(field_path, decoded_value)
            assert result == "abc*123"

    def test_process_wildcard_value_no_flask_module(self):
        """Test processing wildcard values when Flask module is not available."""
        with patch("api.filtering.wildcard_utils.flask", None):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "abc*123"

            # This should not raise an exception and should return the original value
            result = process_wildcard_value(field_path, decoded_value)
            assert result == "abc*123"


class TestWildcardFilteringIntegration:
    """Integration tests for wildcard filtering."""

    def test_wildcard_vs_literal_asterisk_distinction(self):
        """Test that we can distinguish between wildcards and literal asterisks."""
        # Test case 1: Regular wildcard (should become %)
        wildcard_value = "abc*123"
        result1 = prepare_wildcard_value_for_sql(wildcard_value)
        assert result1 == "abc%123"

        # Test case 2: URL-encoded asterisk (should become literal *)
        encoded_marker = "abc\x00ENCODED_ASTERISK\x00123"
        result2 = prepare_wildcard_value_for_sql(encoded_marker)
        assert result2 == "abc*123"

        # Test case 3: Mixed wildcards and literals
        mixed_value = "abc*def\x00ENCODED_ASTERISK\x00ghi*jkl"
        result3 = prepare_wildcard_value_for_sql(mixed_value)
        assert result3 == "abc%def*ghi%jkl"

    def test_end_to_end_wildcard_processing(self):
        """Test the complete wildcard processing pipeline."""
        # Mock Flask module and request
        mock_flask = MagicMock()
        mock_request = MagicMock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=test%2Avalue"}
        mock_flask.request = mock_request

        with patch("api.filtering.wildcard_utils.flask", mock_flask):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "test*value"  # This is what we get after URL decoding

            # Step 1: Process the value to detect encoded asterisks
            processed_value = process_wildcard_value(field_path, decoded_value)

            # Step 2: Prepare for SQL
            sql_value = prepare_wildcard_value_for_sql(processed_value)

            # The final result should treat the asterisk as literal
            assert sql_value == "test*value"

    def test_end_to_end_regular_wildcard_processing(self):
        """Test the complete wildcard processing pipeline with regular wildcards."""
        # Mock Flask module and request
        mock_flask = MagicMock()
        mock_request = MagicMock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=test*value"}
        mock_flask.request = mock_request

        with patch("api.filtering.wildcard_utils.flask", mock_flask):
            field_path = "filter[system_profile][os_release]"
            decoded_value = "test*value"

            # Step 1: Process the value
            processed_value = process_wildcard_value(field_path, decoded_value)

            # Step 2: Prepare for SQL
            sql_value = prepare_wildcard_value_for_sql(processed_value)

            # The final result should treat the asterisk as a wildcard
            assert sql_value == "test%value"
