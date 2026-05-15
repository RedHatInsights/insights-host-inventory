"""
Utilities for handling URL-encoded wildcards in filter parameters.

This module provides functions to detect when wildcard characters were originally
URL-encoded and should be treated as literal characters rather than wildcards.
"""

import flask


def was_wildcard_url_encoded(field_path: str, value: str) -> bool:
    """
    Check if a wildcard character (*) in the filter value was originally URL-encoded.

    This function examines the raw query string to determine if asterisk characters
    in the filter value were originally encoded as %2A in the URL. If they were,
    they should be treated as literal characters, not as wildcards.

    Args:
        field_path: The filter field path (e.g., "filter[system_profile][os_release]")
        value: The decoded filter value that may contain asterisk characters

    Returns:
        True if any asterisk in the value was originally URL-encoded as %2A
    """
    if "*" not in value:
        return False

    # Get the raw query string from the Flask request
    try:
        raw_query_string = flask.request.environ.get("QUERY_STRING", "")
        if not raw_query_string:
            return False
    except RuntimeError:
        # No request context available (e.g., during testing)
        return False

    # Look for the field in the raw query string
    # We need to handle both the field name and value being URL-encoded
    field_patterns = [
        f"{field_path}=",
        # Also check URL-encoded versions of the field path
        f"{field_path.replace('[', '%5B').replace(']', '%5D')}=",
    ]

    for pattern in field_patterns:
        if pattern in raw_query_string:
            # Find the start of the value after the field pattern
            start_idx = raw_query_string.find(pattern) + len(pattern)

            # Find the end of the value (next & or end of string)
            end_idx = raw_query_string.find("&", start_idx)
            if end_idx == -1:
                end_idx = len(raw_query_string)

            raw_value = raw_query_string[start_idx:end_idx]

            # Check if the raw value contains %2A (URL-encoded asterisk)
            if "%2A" in raw_value.upper():
                return True

    return False


def handle_url_encoded_wildcards(field_path: str, value: str, field_filter: str) -> tuple[str, bool]:
    """
    Handle URL-encoded wildcards in filter values.

    If wildcards were URL-encoded, return the value with literal asterisks and
    indicate that exact matching should be used instead of wildcard matching.

    Args:
        field_path: The filter field path (e.g., "filter[system_profile][os_release]")
        value: The decoded filter value
        field_filter: The field filter type (e.g., "wildcard", "string")

    Returns:
        Tuple of (processed_value, use_exact_match)
        - processed_value: The value to use for filtering
        - use_exact_match: True if exact matching should be used instead of wildcard
    """
    # Only apply this logic to wildcard fields
    if field_filter != "wildcard":
        return value, False

    # Check if wildcards were URL-encoded
    if was_wildcard_url_encoded(field_path, value):
        # Use exact matching for URL-encoded wildcards
        return value, True

    # Normal wildcard processing
    return value, False
