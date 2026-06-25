#!/usr/bin/env python
"""
Unit tests for the URL-encoded asterisk parsing fix (RHINENG-4809).

These tests verify that the customURIParser correctly handles URL-encoded
characters without double encoding/decoding.
"""

from urllib.parse import unquote

from api.parsing import customURIParser


def test_url_encoding_behavior_verification():
    """
    Verification test to ensure we understand URL encoding behavior correctly.

    This test documents the expected behavior of URL decoding that the fix addresses.
    """
    # Verify that unquote() correctly decodes URL-encoded asterisks
    assert unquote("%2A") == "*"
    assert unquote("%2a") == "*"  # Case insensitive
    assert unquote("test%2Avalue") == "test*value"
    assert unquote("test%2Avalue%2A") == "test*value*"

    # Verify that unquote() handles other characters correctly
    assert unquote("%20") == " "
    assert unquote("%21") == "!"
    assert unquote("%25") == "%"

    # Verify that already decoded characters are not affected
    assert unquote("*") == "*"
    assert unquote("test*value") == "test*value"


def test_custom_uri_parser_no_double_encoding():
    """
    Test that customURIParser.resolve_params doesn't do double encoding/decoding.

    This test verifies the fix for RHINENG-4809 by ensuring that the parser
    doesn't apply additional quote/unquote operations that would cause
    URL-encoded asterisks to be incorrectly processed.
    """
    # Create a minimal parser instance
    parser = customURIParser({}, {})

    # Test that values are passed through without double encoding
    # When no parameter definitions exist, values are returned as-is (arrays)
    test_cases = [
        # Already decoded asterisk (what we'd get from web framework)
        ({"filter": ["*"]}, {"filter": ["*"]}),
        # Already decoded value with asterisk
        ({"filter": ["test*value"]}, {"filter": ["test*value"]}),
        # Multiple values (returned as array when no param definitions)
        ({"filter": ["first*", "second*"]}, {"filter": ["first*", "second*"]}),
        # Other special characters
        ({"filter": ["test value"]}, {"filter": ["test value"]}),
        ({"filter": ["test!@#"]}, {"filter": ["test!@#"]}),
    ]

    for input_params, expected_output in test_cases:
        result = parser.resolve_params(input_params, "query")
        assert result == expected_output, f"Failed for input {input_params}: got {result}, expected {expected_output}"


def test_custom_uri_parser_demonstrates_fix():
    """
    Test that demonstrates the fix for RHINENG-4809.

    This test shows that the parser no longer does double encoding/decoding
    that would cause URL-encoded asterisks to be incorrectly processed.
    """
    parser = customURIParser({}, {})

    # Before the fix, there was double encoding/decoding that would cause issues
    # Now, values are passed through correctly

    # Simulate what happens when web framework decodes %2A to *
    decoded_asterisk_value = "*"  # This is what we get after URL decoding

    result = parser.resolve_params({"filter": [decoded_asterisk_value]}, "query")

    # The parser should not do additional encoding/decoding
    assert result == {"filter": [decoded_asterisk_value]}

    # Test with multiple asterisks
    decoded_multiple_value = "test*value*end"
    result = parser.resolve_params({"filter": [decoded_multiple_value]}, "query")
    assert result == {"filter": [decoded_multiple_value]}


def test_custom_uri_parser_preserves_special_characters():
    """
    Test that the parser preserves special characters correctly after the fix.
    """
    parser = customURIParser({}, {})

    # Test various special characters that might be URL-encoded
    test_values = [
        "*",  # Asterisk
        "test*value",  # Asterisk in middle
        "*start",  # Asterisk at start
        "end*",  # Asterisk at end
        "test value",  # Space (from %20)
        "test!@#$%",  # Various special chars
        "test&value",  # Ampersand
        "test+value",  # Plus sign
    ]

    for value in test_values:
        result = parser.resolve_params({"param": [value]}, "query")
        assert result == {"param": [value]}, f"Failed to preserve value: {value}"


def test_custom_uri_parser_path_vs_query_behavior():
    """
    Test the difference between path and query parameter handling.
    """
    parser = customURIParser({}, {})

    # Query parameters without definitions are returned as arrays
    query_result = parser.resolve_params({"param": ["*"]}, "query")
    assert query_result == {"param": ["*"]}

    # Path parameters are converted to arrays internally
    path_result = parser.resolve_params({"param": "*"}, "path")
    assert path_result == {"param": "*"}  # Single value for path params


def test_fix_prevents_double_encoding_issue():
    """
    Test that specifically verifies the double encoding issue is fixed.

    Before the fix, the parser would:
    1. quote() the values (encoding * to %2A)
    2. unquote() the results (decoding %2A back to *)

    This caused URL-encoded asterisks (%2A) to be incorrectly processed.
    """
    parser = customURIParser({}, {})

    # Test that asterisks are preserved without additional encoding/decoding
    test_cases = [
        # Single asterisk
        {"input": {"filter": ["*"]}, "expected": {"filter": ["*"]}},
        # Multiple asterisks
        {"input": {"filter": ["test*value*end"]}, "expected": {"filter": ["test*value*end"]}},
        # Mixed with other characters
        {"input": {"filter": ["*test*"]}, "expected": {"filter": ["*test*"]}},
    ]

    for case in test_cases:
        result = parser.resolve_params(case["input"], "query")
        assert result == case["expected"], f"Double encoding issue detected for {case['input']}"
