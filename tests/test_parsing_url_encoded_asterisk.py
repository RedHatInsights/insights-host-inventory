"""Unit tests for URL-encoded asterisk handling in parsing logic."""

import pytest
from urllib.parse import quote

from api.parsing import customURIParser


class TestUrlEncodedAsteriskParsing:
    """Test URL-encoded asterisk preservation in parsing logic."""

    def test_preserve_url_encoded_asterisks(self):
        """Test that URL-encoded asterisks are properly preserved."""
        # Test case 1: URL-encoded asterisk
        value = "test%2A123"
        processed, had_encoded = customURIParser._preserve_url_encoded_asterisks(value)
        assert had_encoded is True
        assert "%2A" not in processed
        assert "__URL_ENCODED_ASTERISK__" in processed

        # Test case 2: Literal asterisk
        value = "test*123"
        processed, had_encoded = customURIParser._preserve_url_encoded_asterisks(value)
        assert had_encoded is False
        assert processed == value

        # Test case 3: Mixed case
        value = "prefix%2Amiddle*suffix"
        processed, had_encoded = customURIParser._preserve_url_encoded_asterisks(value)
        assert had_encoded is True
        assert "%2A" not in processed
        assert "*" in processed  # Literal asterisk should remain

        # Test case 4: Lowercase encoding
        value = "test%2a123"
        processed, had_encoded = customURIParser._preserve_url_encoded_asterisks(value)
        assert had_encoded is True
        assert "%2a" not in processed

    def test_restore_url_encoded_asterisks(self):
        """Test that placeholders are properly restored to literal asterisks."""
        # Test case 1: Restore placeholder
        value = "test__URL_ENCODED_ASTERISK__123"
        restored = customURIParser._restore_url_encoded_asterisks(value, True)
        assert restored == "test*123"

        # Test case 2: No restoration needed
        value = "test*123"
        restored = customURIParser._restore_url_encoded_asterisks(value, False)
        assert restored == "test*123"

        # Test case 3: Mixed placeholders and literals
        value = "prefix__URL_ENCODED_ASTERISK__middle*suffix"
        restored = customURIParser._restore_url_encoded_asterisks(value, True)
        assert restored == "prefix*middle*suffix"

    def test_make_deep_object_with_url_encoded_asterisk(self):
        """Test that _make_deep_object properly handles URL-encoded asterisks."""
        # Test single value with URL-encoded asterisk
        key = "filter[system_profile][os_release]"
        value = ["test%2A123"]

        root_key, result, is_deep = customURIParser._make_deep_object(key, value)

        assert root_key == "filter"
        assert is_deep is True
        assert len(result) == 1

        # The result should have the URL-encoded asterisk converted to literal asterisk
        filter_dict = result[0]
        assert "system_profile" in filter_dict
        assert "os_release" in filter_dict["system_profile"]
        assert filter_dict["system_profile"]["os_release"] == "test*123"

    def test_make_deep_object_with_literal_asterisk(self):
        """Test that _make_deep_object preserves literal asterisks."""
        # Test single value with literal asterisk
        key = "filter[system_profile][os_release]"
        value = ["test*123"]

        root_key, result, is_deep = customURIParser._make_deep_object(key, value)

        assert root_key == "filter"
        assert is_deep is True
        assert len(result) == 1

        # The result should preserve the literal asterisk
        filter_dict = result[0]
        assert "system_profile" in filter_dict
        assert "os_release" in filter_dict["system_profile"]
        assert filter_dict["system_profile"]["os_release"] == "test*123"

    def test_make_deep_object_array_values(self):
        """Test that _make_deep_object handles arrays with URL-encoded asterisks."""
        # Test array values with mixed encoding
        key = "filter[system_profile][os_release][]"
        values = ["test%2A123", "literal*456"]

        root_key, result, is_deep = customURIParser._make_deep_object(key, values)

        assert root_key == "filter"
        assert is_deep is True
        assert len(result) == 1

        # The result should have both values properly processed
        filter_dict = result[0]
        assert "system_profile" in filter_dict
        assert "os_release" in filter_dict["system_profile"]

        result_values = filter_dict["system_profile"]["os_release"]
        assert len(result_values) == 2
        assert "test*123" in result_values  # URL-encoded converted to literal
        assert "literal*456" in result_values  # Literal preserved

    def test_complex_url_encoded_scenarios(self):
        """Test complex scenarios with multiple special characters."""
        # Test with both asterisk and backslash
        test_value = "test1%2Atest2%5Ctest3"
        processed, had_encoded = customURIParser._preserve_url_encoded_asterisks(test_value)

        # Only asterisks should be preserved, backslashes handled by normal URL decoding
        assert had_encoded is True
        assert "__URL_ENCODED_ASTERISK__" in processed
        assert "%5C" in processed  # Backslash encoding should remain for normal URL decoding

        # After URL decoding and restoration
        from urllib.parse import unquote
        decoded = unquote(processed)
        restored = customURIParser._restore_url_encoded_asterisks(decoded, had_encoded)

        # Should have literal asterisk and backslash
        assert "*" in restored
        assert "\\" in restored
