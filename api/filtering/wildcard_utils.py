"""
Utilities for handling wildcard characters in filter values.

This module provides functions to distinguish between literal asterisk characters
that were URL-encoded (%2A) and actual wildcard asterisk characters (*) in filter values.
"""

import re

import flask


def _get_raw_query_string() -> str:
    """Get the raw query string from the current Flask request."""
    try:
        # Try to get the raw query string from Flask request
        if flask.has_request_context():
            return flask.request.environ.get("QUERY_STRING", "")
    except RuntimeError:
        # No request context available
        pass
    return ""


def _extract_filter_values_from_query_string(query_string: str) -> dict[str, str]:
    """
    Extract filter parameter values from the raw query string.

    Returns a mapping of filter parameter paths to their raw (URL-encoded) values.
    For example, if the query string contains:
    "filter[system_profile][os_release]=abc%2A123"

    This returns:
    {"filter[system_profile][os_release]": "abc%2A123"}
    """
    filter_values = {}

    # Pattern to match filter parameters and their values
    # Matches: filter[...][...]=value or filter[...]=value
    pattern = r"(filter(?:\[[^\]]*\])+)=([^&]*)"

    for match in re.finditer(pattern, query_string):
        param_path = match.group(1)
        raw_value = match.group(2)
        filter_values[param_path] = raw_value

    return filter_values


def _was_asterisk_url_encoded(field_path: str, decoded_value: str) -> bool:
    """
    Check if any asterisk characters in the decoded value were originally URL-encoded as %2A.

    Args:
        field_path: The filter parameter path (e.g., "filter[system_profile][os_release]")
        decoded_value: The URL-decoded value that may contain asterisk characters

    Returns:
        True if any asterisk in the value was originally URL-encoded, False otherwise
    """
    if "*" not in decoded_value:
        return False

    query_string = _get_raw_query_string()
    if not query_string:
        return False

    filter_values = _extract_filter_values_from_query_string(query_string)

    # Find the raw value for this field path
    raw_value = None
    for param_path, value in filter_values.items():
        # Match the field path - we need to handle different bracket notations
        if field_path in param_path or _normalize_field_path(field_path) == _normalize_field_path(param_path):
            raw_value = value
            break

    if raw_value is None:
        return False

    # Check if the raw value contains %2A (URL-encoded asterisk)
    return "%2A" in raw_value.upper()


def _normalize_field_path(field_path: str) -> str:
    """
    Normalize a field path for comparison.

    This handles cases where the field path might be represented differently
    in the filter parameter structure vs. the raw query string.
    """
    # Remove any leading/trailing whitespace and convert to lowercase
    normalized = field_path.strip().lower()

    # Handle different bracket notations
    # Convert nested dict access to bracket notation
    # e.g., system_profile.os_release -> [system_profile][os_release]
    if "." in normalized and "[" not in normalized:
        parts = normalized.split(".")
        normalized = "[" + "][".join(parts) + "]"

    return normalized


def should_treat_as_literal_asterisk(field_path: str, value: str) -> bool:
    """
    Determine if asterisk characters in a filter value should be treated as literal
    characters rather than wildcards.

    Args:
        field_path: The filter parameter path (e.g., "system_profile.os_release")
        value: The filter value that may contain asterisk characters

    Returns:
        True if asterisks should be treated as literal characters, False if they
        should be treated as wildcards
    """
    # Convert field path to the format used in query parameters
    if "." in field_path:
        # Convert dot notation to bracket notation for matching
        parts = field_path.split(".")
        bracket_path = f"filter[{parts[0]}][{parts[1]}]" if len(parts) >= 2 else f"filter[{parts[0]}]"
    else:
        bracket_path = f"filter[{field_path}]"

    return _was_asterisk_url_encoded(bracket_path, value)


def process_wildcard_value(field_path: str, value: str) -> str:
    """
    Process a filter value for wildcard handling.

    If the asterisk characters were originally URL-encoded (%2A), they are treated
    as literal characters. Otherwise, they are converted to SQL wildcards (%).

    Args:
        field_path: The filter parameter path (e.g., "system_profile.os_release")
        value: The filter value that may contain asterisk characters

    Returns:
        The processed value with appropriate wildcard handling
    """
    if "*" not in value:
        return value

    if should_treat_as_literal_asterisk(field_path, value):
        # Asterisks were URL-encoded, treat them as literal characters
        # No replacement needed - keep the asterisks as-is for literal matching
        return value
    else:
        # Asterisks were not URL-encoded, treat them as wildcards
        return value.replace("*", "%")
