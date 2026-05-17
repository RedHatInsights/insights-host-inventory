"""
Tests for wildcard URL encoding fix (RHINENG-4809).

This module tests that URL-encoded asterisks (%2A) are treated as literal asterisks
rather than wildcards in system profile filtering.
"""

from unittest.mock import patch

from api.filtering.db_custom_filters import _should_use_exact_match_for_wildcards


class TestWildcardUrlEncoding:
    """Test wildcard URL encoding behavior."""

    def test_should_use_exact_match_for_wildcards_with_encoded_asterisk(self):
        """Test that URL-encoded asterisks trigger exact matching."""
        field_name = "os_release"
        value = "abc*123"  # This is the decoded value
        raw_query = "filter[system_profile][os_release]=abc%2A123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_with_normal_asterisk(self):
        """Test that normal asterisks use wildcard matching."""
        field_name = "os_release"
        value = "abc*123"  # This is the decoded value
        raw_query = "filter[system_profile][os_release]=abc*123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is False

    def test_should_use_exact_match_for_wildcards_no_asterisk(self):
        """Test that values without asterisks return False."""
        field_name = "os_release"
        value = "abc123"  # No asterisk
        raw_query = "filter[system_profile][os_release]=abc123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is False

    def test_should_use_exact_match_for_wildcards_url_encoded_brackets(self):
        """Test that URL-encoded brackets are handled correctly."""
        field_name = "os_release"
        value = "abc*123"
        raw_query = "filter%5Bsystem_profile%5D%5Bos_release%5D=abc%2A123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_case_insensitive(self):
        """Test that %2a (lowercase) is also detected."""
        field_name = "os_release"
        value = "abc*123"
        raw_query = "filter[system_profile][os_release]=abc%2a123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_multiple_params(self):
        """Test detection works with multiple query parameters."""
        field_name = "os_release"
        value = "abc*123"
        raw_query = "page=1&filter[system_profile][os_release]=abc%2A123&per_page=10"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_different_field(self):
        """Test that encoded asterisks in other fields don't affect current field."""
        field_name = "arch"
        value = "x86*64"
        raw_query = "filter[system_profile][os_release]=abc%2A123&filter[system_profile][arch]=x86*64"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is False

    def test_should_use_exact_match_for_wildcards_no_request_context(self):
        """Test graceful handling when Flask request is not available."""
        field_name = "os_release"
        value = "abc*123"

        # Test without providing raw_query and mock Flask request to fail
        with patch("api.filtering.db_custom_filters._get_raw_query_string", return_value=None):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_multiple_asterisks(self):
        """Test handling of multiple asterisks in the value."""
        field_name = "os_release"
        value = "abc*def*123"
        raw_query = "filter[system_profile][os_release]=abc%2Adef%2A123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_mixed_asterisks(self):
        """Test handling when some asterisks are encoded and some are not."""
        field_name = "os_release"
        value = "abc*def*123"
        raw_query = "filter[system_profile][os_release]=abc%2Adef*123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_multiple_occurrences(self):
        """Test that all occurrences of a field are checked, not just the first."""
        field_name = "os_release"
        value = "abc*123"
        # First occurrence has no encoded asterisk, second occurrence does
        raw_query = "filter[system_profile][os_release]=xyz*456&filter[system_profile][os_release]=abc%2A123"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_first_occurrence_encoded(self):
        """Test that encoded asterisk in first occurrence is detected."""
        field_name = "os_release"
        value = "abc*123"
        # First occurrence has encoded asterisk, second doesn't
        raw_query = "filter[system_profile][os_release]=abc%2A123&filter[system_profile][os_release]=xyz*456"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is True

    def test_should_use_exact_match_for_wildcards_no_encoded_in_multiple(self):
        """Test that multiple occurrences without encoded asterisks return False."""
        field_name = "os_release"
        value = "abc*123"
        # Multiple occurrences, none with encoded asterisks
        raw_query = "filter[system_profile][os_release]=abc*123&filter[system_profile][os_release]=xyz*456"

        result = _should_use_exact_match_for_wildcards(field_name, value, raw_query)
        assert result is False
