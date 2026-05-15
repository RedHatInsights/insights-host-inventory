"""
Unit tests for URL encoding utilities.

These tests verify that URL-encoded wildcards are correctly detected and handled.
"""

from unittest.mock import Mock
from unittest.mock import patch

from api.filtering.url_encoding_utils import detect_url_encoded_wildcards
from api.filtering.url_encoding_utils import escape_literal_wildcards
from api.filtering.url_encoding_utils import should_treat_as_literal


class TestDetectUrlEncodedWildcards:
    """Test the detect_url_encoded_wildcards function."""

    def test_no_flask_request(self):
        """Test when Flask request is not available."""
        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = None
            result = detect_url_encoded_wildcards()
            assert result == {}

    def test_no_query_string(self):
        """Test when there's no query string."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": ""}

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
            result = detect_url_encoded_wildcards()
            assert result == {}

    def test_simple_encoded_wildcard(self):
        """Test detection of simple URL-encoded wildcard."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=abc%2A123"}

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
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

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
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

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
            result = detect_url_encoded_wildcards()

            # Only the URL-encoded one should be detected
            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_complex_filter_with_operators(self):
        """Test detection with complex filter operators."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release][eq]=abc%2A123"}

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"abc*123"}}
            assert result == expected

    def test_backslash_encoding(self):
        """Test detection of URL-encoded backslashes."""
        mock_request = Mock()
        mock_request.environ = {"QUERY_STRING": "filter[system_profile][os_release]=test1%2Atest2%5Ctest3"}

        with patch("api.filtering.url_encoding_utils.flask") as mock_flask:
            mock_flask.request = mock_request
            result = detect_url_encoded_wildcards()

            expected = {"system_profile.os_release": {"test1*test2\\test3"}}
            assert result == expected


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


class TestEscapeLiteralWildcards:
    """Test the escape_literal_wildcards function."""

    def test_escape_asterisk(self):
        """Test escaping asterisk characters."""
        result = escape_literal_wildcards("abc*123")
        assert result == "abc\\*123"

    def test_escape_percent(self):
        """Test escaping percent characters."""
        result = escape_literal_wildcards("abc%123")
        assert result == "abc\\%123"

    def test_escape_backslash(self):
        """Test escaping backslash characters."""
        result = escape_literal_wildcards("abc\\123")
        assert result == "abc\\\\123"

    def test_escape_multiple_characters(self):
        """Test escaping multiple special characters."""
        result = escape_literal_wildcards("test1*test2\\test3%test4")
        assert result == "test1\\*test2\\\\test3\\%test4"

    def test_no_special_characters(self):
        """Test with no special characters to escape."""
        result = escape_literal_wildcards("normal_string")
        assert result == "normal_string"

    def test_empty_string(self):
        """Test with empty string."""
        result = escape_literal_wildcards("")
        assert result == ""
