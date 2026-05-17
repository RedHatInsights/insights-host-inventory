"""
Tests for wildcard URL encoding fix (RHINENG-4809).

This module tests that URL-encoded asterisks (%2A) are treated as literal asterisks
rather than wildcards in system profile filtering.
"""

from unittest.mock import Mock
from unittest.mock import patch

from api.filtering.db_custom_filters import _should_use_exact_match_for_wildcards


class TestWildcardUrlEncoding:
    """Test wildcard URL encoding behavior."""

    def test_should_use_exact_match_for_wildcards_with_encoded_asterisk(self):
        """Test that URL-encoded asterisks trigger exact matching."""
        field_name = "os_release"
        value = "abc*123"  # This is the decoded value

        # Mock Flask request with URL-encoded asterisk
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc%2A123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True

    def test_should_use_exact_match_for_wildcards_with_normal_asterisk(self):
        """Test that normal asterisks use wildcard matching."""
        field_name = "os_release"
        value = "abc*123"  # This is the decoded value

        # Mock Flask request with normal asterisk (not URL-encoded)
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc*123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_no_asterisk(self):
        """Test that values without asterisks return False."""
        field_name = "os_release"
        value = "abc123"  # No asterisk

        # Mock Flask request
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_url_encoded_brackets(self):
        """Test that URL-encoded brackets are handled correctly."""
        field_name = "os_release"
        value = "abc*123"

        # Mock Flask request with URL-encoded brackets and asterisk
        mock_request = Mock()
        mock_request.query_string = b"filter%5Bsystem_profile%5D%5Bos_release%5D=abc%2A123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True

    def test_should_use_exact_match_for_wildcards_case_insensitive(self):
        """Test that %2a (lowercase) is also detected."""
        field_name = "os_release"
        value = "abc*123"

        # Mock Flask request with lowercase %2a
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc%2a123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True

    def test_should_use_exact_match_for_wildcards_multiple_params(self):
        """Test detection works with multiple query parameters."""
        field_name = "os_release"
        value = "abc*123"

        # Mock Flask request with multiple parameters
        mock_request = Mock()
        mock_request.query_string = b"page=1&filter[system_profile][os_release]=abc%2A123&per_page=10"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True

    def test_should_use_exact_match_for_wildcards_different_field(self):
        """Test that encoded asterisks in other fields don't affect current field."""
        field_name = "arch"
        value = "x86*64"

        # Mock Flask request with encoded asterisk in different field
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc%2A123&filter[system_profile][arch]=x86*64"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_no_request_context(self):
        """Test graceful handling when Flask request is not available."""
        field_name = "os_release"
        value = "abc*123"

        # Test without any Flask context - should return False gracefully
        # We'll patch the function to simulate the exception that would occur
        with patch("api.filtering.db_custom_filters.flask") as mock_flask:
            mock_flask.request.query_string.decode.side_effect = RuntimeError("No request context")
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_unicode_decode_error(self):
        """Test graceful handling of Unicode decode errors."""
        field_name = "os_release"
        value = "abc*123"

        # Mock Flask request with invalid UTF-8
        mock_request = Mock()
        mock_request.query_string = b"\xff\xfe"  # Invalid UTF-8

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is False

    def test_should_use_exact_match_for_wildcards_multiple_asterisks(self):
        """Test handling of multiple asterisks in the value."""
        field_name = "os_release"
        value = "abc*def*123"

        # Mock Flask request with multiple encoded asterisks
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc%2Adef%2A123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True

    def test_should_use_exact_match_for_wildcards_mixed_asterisks(self):
        """Test handling when some asterisks are encoded and some are not."""
        field_name = "os_release"
        value = "abc*def*123"

        # Mock Flask request with mixed encoded/unencoded asterisks
        # This should trigger exact matching because at least one asterisk was encoded
        mock_request = Mock()
        mock_request.query_string = b"filter[system_profile][os_release]=abc%2Adef*123"

        with patch("flask.request", mock_request):
            result = _should_use_exact_match_for_wildcards(field_name, value)
            assert result is True
