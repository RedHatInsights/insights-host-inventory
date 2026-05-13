"""
Test for RHINENG-4809 fix: SP filtering uses "*" as wildcard even if it is formatted

This test verifies that URL-encoded asterisks (%2A) are treated as literal asterisks,
not as wildcards.
"""

from unittest.mock import patch

from api.filtering.db_custom_filters import (
    build_single_filter,
    _contains_url_encoded_chars,
    _should_use_literal_match,
)


def test_url_encoded_asterisk_detection():
    """Test that URL-encoded characters are properly detected."""
    # Test cases that should be detected as URL-encoded
    assert _contains_url_encoded_chars("abc%2A123") is True
    assert _contains_url_encoded_chars("test1%2Atest2%5Ctest3") is True
    assert _contains_url_encoded_chars("test%20space") is True
    assert _contains_url_encoded_chars("value%3D123") is True
    
    # Test cases that should NOT be detected as URL-encoded
    assert _contains_url_encoded_chars("abc*123") is False
    assert _contains_url_encoded_chars("normal_string") is False
    assert _contains_url_encoded_chars("test%") is False
    assert _contains_url_encoded_chars("test%2") is False
    assert _contains_url_encoded_chars("test%GG") is False
    assert _contains_url_encoded_chars("") is False


def test_literal_match_decision():
    """Test that literal match is correctly decided based on field type and URL encoding."""
    # For wildcard fields with URL-encoded chars, should use literal match
    assert _should_use_literal_match("abc%2A123", "wildcard") is True
    assert _should_use_literal_match("test%20space", "wildcard") is True
    
    # For wildcard fields without URL-encoded chars, should use wildcard match
    assert _should_use_literal_match("abc*123", "wildcard") is False
    assert _should_use_literal_match("normal_string", "wildcard") is False
    
    # For non-wildcard fields, should never trigger literal match logic
    assert _should_use_literal_match("abc%2A123", "string") is False
    assert _should_use_literal_match("abc*123", "string") is False


@patch('api.filtering.db_custom_filters.system_profile_spec')
def test_wildcard_vs_literal_filtering(mock_system_profile_spec):
    """Test that wildcard and literal filtering work correctly."""
    # Mock the system profile spec to return wildcard filter type
    mock_system_profile_spec.return_value = {
        "os_release": {
            "type": str,
            "filter": "wildcard",
            "format": None,
            "is_array": False,
        }
    }
    
    # Test case 1: Regular wildcard should use ILIKE
    filter_param_wildcard = {"os_release": "abc*123"}
    result_wildcard = build_single_filter(filter_param_wildcard)
    
    # Convert to SQL to check the operation
    sql_wildcard = str(result_wildcard.compile(compile_kwargs={'literal_binds': True}))
    
    # Should use ILIKE and replace * with %
    assert "ILIKE" in sql_wildcard.upper()
    assert "abc%123" in sql_wildcard
    
    # Test case 2: URL-encoded asterisk should use exact match
    filter_param_encoded = {"os_release": "abc%2A123"}
    result_encoded = build_single_filter(filter_param_encoded)
    
    # Convert to SQL to check the operation
    sql_encoded = str(result_encoded.compile(compile_kwargs={'literal_binds': True}))
    
    # Should use = (exact match) and preserve the URL-encoded value
    assert "=" in sql_encoded
    assert "ILIKE" not in sql_encoded.upper()
    # The value should contain the original URL-encoded pattern for detection
    assert "abc%2A123" in sql_encoded


@patch('api.filtering.db_custom_filters.system_profile_spec')
def test_backslash_escaping_case(mock_system_profile_spec):
    """Test the backslash escaping case mentioned in the RHINENG-4809 ticket."""
    # Mock the system profile spec
    mock_system_profile_spec.return_value = {
        "os_release": {
            "type": str,
            "filter": "wildcard",
            "format": None,
            "is_array": False,
        }
    }
    
    # Test the complex case with both asterisk and backslash URL-encoded
    filter_param = {"os_release": "test1%2Atest2%5Ctest3"}
    result = build_single_filter(filter_param)
    
    sql = str(result.compile(compile_kwargs={'literal_binds': True}))
    
    # Should use exact match, not wildcard
    assert "=" in sql
    assert "ILIKE" not in sql.upper()
    # Should preserve the URL-encoded value for detection
    assert "test1%2Atest2%5Ctest3" in sql


@patch('api.filtering.db_custom_filters.system_profile_spec')
def test_non_wildcard_field_unaffected(mock_system_profile_spec):
    """Test that non-wildcard fields are not affected by the fix."""
    # Mock the system profile spec for a non-wildcard field
    mock_system_profile_spec.return_value = {
        "arch": {
            "type": str,
            "filter": "string",
            "format": None,
            "is_array": False,
        }
    }
    
    # Test with URL-encoded value on non-wildcard field
    filter_param = {"arch": "x86%2A64"}
    result = build_single_filter(filter_param)
    
    sql = str(result.compile(compile_kwargs={'literal_binds': True}))
    
    # Should use exact match (normal behavior for string fields)
    assert "=" in sql
    assert "ILIKE" not in sql.upper()
    # Should contain the URL-encoded value
    assert "x86%2A64" in sql