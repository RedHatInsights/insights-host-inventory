"""
Utility functions for handling wildcard filtering with URL-encoded asterisks.

This module provides functionality to distinguish between:
1. Literal asterisks (*) that should be treated as wildcards
2. URL-encoded asterisks (%2A) that should be treated as literal asterisk characters
"""

import re
from urllib.parse import unquote

try:
    import flask
except ImportError:
    flask = None  # type: ignore[assignment]


def _extract_filter_value_from_raw_query(field_path: str, raw_query: str) -> str | None:
    """
    Extract the raw (non-URL-decoded) value for a specific filter field from the query string.

    Args:
        field_path: The filter field path, e.g., "filter[system_profile][os_release]"
        raw_query: The raw query string before URL decoding

    Returns:
        The raw value if found, None otherwise
    """
    # Escape special regex characters in the field path
    escaped_path = re.escape(field_path)

    # Pattern to match the field and capture its value
    # Handles both = and []= formats
    pattern = rf"{escaped_path}(?:\[\])?=([^&]*)"

    match = re.search(pattern, raw_query)
    if match:
        return match.group(1)

    return None


def _contains_encoded_asterisk(raw_value: str) -> bool:
    """
    Check if a raw query value contains URL-encoded asterisks (%2A or %2a).

    Args:
        raw_value: The raw (non-URL-decoded) value from the query string

    Returns:
        True if the value contains %2A or %2a, False otherwise
    """
    return "%2A" in raw_value or "%2a" in raw_value


def process_wildcard_value(field_path: str, decoded_value: str) -> str:
    """
    Process a filter value to handle URL-encoded wildcards correctly.

    This function distinguishes between:
    - Literal * characters (should be treated as wildcards)
    - URL-encoded %2A characters (should be treated as literal asterisks)

    Args:
        field_path: The filter field path, e.g., "filter[system_profile][os_release]"
        decoded_value: The URL-decoded value containing asterisks

    Returns:
        The processed value with URL-encoded asterisks marked as literals
    """
    # Try to access the raw query string
    try:
        if flask and hasattr(flask, "request") and flask.request:
            raw_query = flask.request.environ.get("QUERY_STRING", "")
            if raw_query and isinstance(raw_query, str):
                raw_value = _extract_filter_value_from_raw_query(field_path, raw_query)
                if raw_value and _contains_encoded_asterisk(raw_value):
                    # The value contains URL-encoded asterisks
                    # We need to replace them with a special marker that won't be treated as wildcards
                    return _replace_encoded_asterisks_with_marker(raw_value)
    except (RuntimeError, AttributeError):
        # No Flask request context available, fall back to treating all * as wildcards
        pass

    # Default behavior: treat all * as wildcards
    return decoded_value


def _replace_encoded_asterisks_with_marker(raw_value: str) -> str:
    """
    Replace URL-encoded asterisks with a special marker in the decoded value.

    This function analyzes the raw value to identify which asterisks in the decoded
    value came from URL encoding (%2A) and replaces them with a special marker.

    Args:
        raw_value: The raw query value before URL decoding

    Returns:
        The decoded value with URL-encoded asterisks replaced by markers
    """
    # Special marker for URL-encoded asterisks (using a character that's unlikely to appear in real data)
    ENCODED_ASTERISK_MARKER = "\x00ENCODED_ASTERISK\x00"

    # Create a version of the raw value with %2A/%2a replaced by the marker
    marked_raw = raw_value.replace("%2A", ENCODED_ASTERISK_MARKER).replace("%2a", ENCODED_ASTERISK_MARKER)

    # URL decode the marked version
    marked_decoded = unquote(marked_raw)

    return marked_decoded


def prepare_wildcard_value_for_sql(value: str) -> str:
    """
    Prepare a wildcard value for SQL ILIKE by replacing wildcards with % and handling literals.

    Args:
        value: The value potentially containing wildcards and encoded asterisk markers

    Returns:
        The value prepared for SQL ILIKE with proper wildcard handling
    """
    ENCODED_ASTERISK_MARKER = "\x00ENCODED_ASTERISK\x00"

    # First, replace literal asterisks (from URL encoding) with a temporary placeholder
    temp_placeholder = "\x00LITERAL_ASTERISK\x00"
    value = value.replace(ENCODED_ASTERISK_MARKER, temp_placeholder)

    # Replace wildcard asterisks with SQL wildcard %
    value = value.replace("*", "%")

    # Replace literal asterisks back to actual asterisk characters
    value = value.replace(temp_placeholder, "*")

    return value
