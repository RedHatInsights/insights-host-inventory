"""
Test for the wildcard filtering logic in db_custom_filters.py

This test verifies that the _has_url_encoded_wildcard function and build_single_filter
work correctly with URL-encoded wildcards.
"""

from flask import Flask

from api.filtering.db_custom_filters import _has_url_encoded_wildcard
from api.filtering.db_custom_filters import build_single_filter


def test_has_url_encoded_wildcard_detection():
    """Test the _has_url_encoded_wildcard function with Flask request context."""

    app = Flask(__name__)

    # Test case 1: URL-encoded asterisk should be detected
    with app.test_request_context("/?filter[system_profile][os_release]=abc%2A123"):
        result = _has_url_encoded_wildcard("os_release", "abc*123")
        assert result is True, "Should detect URL-encoded asterisk"

    # Test case 2: Unencoded asterisk should not be detected as URL-encoded
    with app.test_request_context("/?filter[system_profile][os_release]=abc*123"):
        result = _has_url_encoded_wildcard("os_release", "abc*123")
        assert result is False, "Should not detect unencoded asterisk as URL-encoded"

    # Test case 3: No asterisk in value
    with app.test_request_context("/?filter[system_profile][os_release]=abc123"):
        result = _has_url_encoded_wildcard("os_release", "abc123")
        assert result is False, "Should return False when no asterisk in value"

    # Test case 4: Lowercase URL-encoded asterisk
    with app.test_request_context("/?filter[system_profile][os_release]=abc%2a123"):
        result = _has_url_encoded_wildcard("os_release", "abc*123")
        assert result is True, "Should detect lowercase URL-encoded asterisk"


def test_has_url_encoded_wildcard_no_request_context():
    """Test _has_url_encoded_wildcard when there's no Flask request context."""

    # Should return False when no request context
    result = _has_url_encoded_wildcard("os_release", "abc*123")
    assert result is False, "Should return False when no request context"


def test_build_single_filter_with_url_encoded_wildcard():
    """Test build_single_filter with URL-encoded wildcards."""

    app = Flask(__name__)

    # Mock the system profile spec
    mock_spec = {
        "os_release": {
            "type": str,
            "filter": "wildcard",
            "format": None,
            "is_array": False,
        }
    }

    # Set up the Flask app config
    app.config["SYSTEM_PROFILE_SPEC"] = mock_spec

    # Test case 1: URL-encoded asterisk should use exact match (=)
    with app.app_context():
        with app.test_request_context("/?filter[system_profile][os_release]=abc%2A123"):
            filter_param = {"os_release": "abc*123"}
            result = build_single_filter(filter_param)

            # The result should be an exact match, not a LIKE/ILIKE
            compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
            assert "=" in compiled and "LIKE" not in compiled, f"Should use exact match, got: {compiled}"
            assert "abc*123" in compiled, "Should preserve literal asterisk"

    # Test case 2: Unencoded asterisk should use LIKE/ILIKE with % replacement
    with app.app_context():
        with app.test_request_context("/?filter[system_profile][os_release]=abc*123"):
            filter_param = {"os_release": "abc*123"}
            result = build_single_filter(filter_param)

            # The result should be a LIKE/ILIKE with % replacement
            compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
            assert "LIKE" in compiled or "ILIKE" in compiled, f"Should use LIKE/ILIKE for wildcard, got: {compiled}"
            assert "abc%123" in compiled, "Should replace * with % for wildcard"


def test_build_single_filter_insights_client_version():
    """Test build_single_filter with insights_client_version field."""

    app = Flask(__name__)

    # Mock the system profile spec
    mock_spec = {
        "insights_client_version": {
            "type": str,
            "filter": "wildcard",
            "format": None,
            "is_array": False,
        }
    }

    app.config["SYSTEM_PROFILE_SPEC"] = mock_spec

    # Test URL-encoded asterisk with insights_client_version
    with app.app_context():
        with app.test_request_context("/?filter[system_profile][insights_client_version]=3.0%2A2.el4_2"):
            filter_param = {"insights_client_version": "3.0*2.el4_2"}
            result = build_single_filter(filter_param)

            # Should use exact match for URL-encoded asterisk
            compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
            assert "=" in compiled and "LIKE" not in compiled, f"Should use exact match, got: {compiled}"
            assert "3.0*2.el4_2" in compiled, "Should preserve literal asterisk"


def test_build_single_filter_non_wildcard_field():
    """Test that non-wildcard fields are not affected by the URL encoding logic."""

    app = Flask(__name__)

    # Mock the system profile spec with a non-wildcard field
    mock_spec = {
        "arch": {
            "type": str,
            "filter": "string",  # Not "wildcard"
            "format": None,
            "is_array": False,
        }
    }

    app.config["SYSTEM_PROFILE_SPEC"] = mock_spec

    # Even with URL-encoded asterisk, non-wildcard fields should use exact match
    with app.app_context():
        with app.test_request_context("/?filter[system_profile][arch]=x86%2A64"):
            filter_param = {"arch": "x86*64"}
            result = build_single_filter(filter_param)

            # Should use exact match for non-wildcard fields regardless of URL encoding
            compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
            assert "=" in compiled, f"Should use exact match for non-wildcard field, got: {compiled}"
            assert "x86*64" in compiled, "Should preserve asterisk as literal"


def test_backslash_escape_issue():
    """Test the backslash escape issue mentioned in the ticket."""

    app = Flask(__name__)

    # Test that URL-encoded backslashes are handled correctly
    with app.test_request_context("/?filter[system_profile][os_release]=test1%2Atest2%5Ctest3"):
        # The value after URL decoding would be "test1*test2\test3"
        result = _has_url_encoded_wildcard("os_release", "test1*test2\\test3")
        assert result is True, "Should detect URL-encoded asterisk even with backslashes"
