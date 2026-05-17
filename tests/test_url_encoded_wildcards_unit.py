"""
Unit tests for URL-encoded wildcard detection logic.

This test verifies the fix for RHINENG-4809: URL-encoded wildcards (%2A)
should be treated as literal asterisks, not as wildcard patterns.
"""

from api.filtering.db_custom_filters import _was_wildcard_url_encoded


class TestUrlEncodedWildcardDetection:
    """Test the URL-encoded wildcard detection logic."""

    def test_was_wildcard_url_encoded_with_encoded_asterisk(self):
        """Test detection when asterisk was originally URL-encoded."""
        query_string = "filter[system_profile][os_release]=abc%2A123"
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is True

    def test_was_wildcard_url_encoded_with_lowercase_encoded_asterisk(self):
        """Test detection with lowercase URL-encoded asterisk."""
        query_string = "filter[system_profile][os_release]=abc%2a123"
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is True

    def test_was_wildcard_url_encoded_with_regular_asterisk(self):
        """Test detection when asterisk was not URL-encoded."""
        query_string = "filter[system_profile][os_release]=abc*123"
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is False

    def test_was_wildcard_url_encoded_no_asterisk_in_value(self):
        """Test when value contains no asterisks."""
        query_string = "filter[system_profile][os_release]=abc123"
        result = _was_wildcard_url_encoded("abc123", "os_release", query_string)
        assert result is False

    def test_was_wildcard_url_encoded_no_query_string(self):
        """Test when there's no query string."""
        query_string = ""
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is False

    def test_was_wildcard_url_encoded_complex_value(self):
        """Test with complex value containing multiple special characters."""
        query_string = "filter[system_profile][os_release]=test1%2Atest2%5Ctest3"
        result = _was_wildcard_url_encoded("test1*test2\\test3", "os_release", query_string)
        assert result is True

    def test_was_wildcard_url_encoded_different_field(self):
        """Test with different field name."""
        query_string = "filter[system_profile][bios_version]=version%2A1.0"
        result = _was_wildcard_url_encoded("version*1.0", "bios_version", query_string)
        assert result is True

    def test_was_wildcard_url_encoded_mixed_encoded_and_regular(self):
        """Test query string with both encoded and regular asterisks."""
        query_string = "filter[system_profile][os_release]=abc%2A123&filter[system_profile][bios_version]=def*456"

        # The os_release field should be detected as encoded
        result1 = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result1 is True

        # The bios_version field should be detected as not encoded (regular asterisk)
        result2 = _was_wildcard_url_encoded("def*456", "bios_version", query_string)
        assert result2 is False

    def test_was_wildcard_url_encoded_field_specific_detection(self):
        """Test that detection is field-specific and doesn't use global heuristics."""
        # Query string contains %2A for one field but not another
        query_string = "filter[system_profile][other_field]=abc%2A123"
        result = _was_wildcard_url_encoded("def*456", "os_release", query_string)
        assert result is False  # Should not match due to field-specific logic

    def test_was_wildcard_url_encoded_no_encoded_wildcards_in_query(self):
        """Test when query string has no URL-encoded wildcards."""
        query_string = "filter[system_profile][os_release]=abc123&filter[system_profile][bios_version]=def456"
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is False

    def test_was_wildcard_url_encoded_direct_field_pattern(self):
        """Test detection with direct field pattern (no system_profile prefix)."""
        query_string = "filter[os_release]=abc%2A123"
        result = _was_wildcard_url_encoded("abc*123", "os_release", query_string)
        assert result is True
