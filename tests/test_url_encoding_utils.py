"""
Unit tests for URL encoding utilities.

These tests verify that URL-encoded wildcards are correctly detected and handled.
"""

from unittest.mock import Mock
from unittest.mock import patch

from api.filtering.url_encoding_utils import detect_url_encoded_wildcards
from api.filtering.url_encoding_utils import should_treat_as_literal


class TestDetectUrlEncodedWildcards:
    """Test the detect_url_encoded_wildcards function."""

    def test_no_request_context(self):
        """Test when Flask request context is not available."""
        with patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context:
            mock_has_context.return_value = False
            result = detect_url_encoded_wildcards()
            assert result == {}

    def test_no_query_string(self):
        """Test when there's no query string."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": ""}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()
            assert result == {}
            assert mock_g._url_encoded_wildcards_cache == {}

    def test_simple_encoded_wildcard(self):
        """Test detection of simple URL-encoded wildcard."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc%2A123"}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_lowercase_encoded_wildcard(self):
        """Test detection of lowercase URL-encoded wildcard (%2a)."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc%2a123"}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_multiple_encoded_wildcards(self):
        """Test detection of multiple URL-encoded wildcards."""
        mock_request = Mock()
        query_string = (
            "filter[system_profile][os_release]=abc%2A123&"
            "filter[system_profile][insights_client_version]=3.0.%2A-2.el4_2"
        )
        mock_request.environ = {"QUERY_STRING": query_string}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            expected = {
                "system_profile.os_release": {"abc*123"},
                "system_profile.insights_client_version": {"3.0.*-2.el4_2"},
            }
            assert result == expected

    def test_mixed_encoded_unencoded(self):
        """Test mix of encoded and unencoded wildcards."""
        mock_request = Mock()
        query_string = (
            "filter[system_profile][os_release]=abc%2A123&"
            "filter[system_profile][insights_client_version]=3.0.*-2.el4_2"
        )
        mock_request.environ = {"QUERY_STRING": query_string}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            # Only the URL-encoded one should be detected
            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_complex_filter_with_operators(self):
        """Test detection with complex filter operators."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release][eq]=abc%2A123"}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_backslash_encoding(self):
        """Test detection of URL-encoded backslashes."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=test1%2Atest2%5Ctest3"}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache

            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"test1*test2\\test3"}}
            assert result == expected

    def test_caching_behavior(self):
        """Test that results are cached per request."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc%2A123"}
        mock_g = Mock()

        with (
            patch("api.filtering.url_encoding_utils.has_request_context") as mock_has_context,
            patch("api.filtering.url_encoding_utils.request", mock_request),
            patch("api.filtering.url_encoding_utils.g", mock_g),
        ):
            mock_has_context.return_value = True

            # First call - no cache
            mock_g._url_encoded_wildcards_cache = None
            del mock_g._url_encoded_wildcards_cache  # Simulate not having the cache
            detect_url_encoded_wildcards()

            # Second call - should use cache
            cached_result = {"cached": "value"}
            mock_g._url_encoded_wildcards_cache = cached_result
            result2 = detect_url_encoded_wildcards()

            assert result2 == cached_result
            assert result2 is cached_result  # Should be the exact same object


class TestShouldTreatAsLiteral:
    """Test the should_treat_as_literal function."""

    def test_literal_match(self):
        """Test when value should be treated as literal."""
        encoded_wildcards = {"system_profile.os_release": {"abc*123"}}

        result = should_treat_as_literal("os_release", "abc*123", encoded_wildcards)
        assert result is True

    def test_wildcard_match(self):
        """Test when value should be treated as wildcard."""
        encoded_wildcards = {"system_profile.os_release": {"abc*123"}}

        result = should_treat_as_literal("os_release", "def*456", encoded_wildcards)
        assert result is False

    def test_no_encoded_wildcards(self):
        """Test when no encoded wildcards are present."""
        encoded_wildcards = {}

        result = should_treat_as_literal("os_release", "abc*123", encoded_wildcards)
        assert result is False

    def test_different_field(self):
        """Test with different field name."""
        encoded_wildcards = {"system_profile.insights_client_version": {"3.0.*-2.el4_2"}}

        result = should_treat_as_literal("os_release", "abc*123", encoded_wildcards)
        assert result is False
