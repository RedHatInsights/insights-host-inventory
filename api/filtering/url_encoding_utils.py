"""
Utilities for handling URL-encoded wildcards in system profile filtering.

This module provides functions to detect URL-encoded wildcards (%2A) in the raw
query string and handle them appropriately in filtering operations.
"""

import re
from urllib.parse import unquote

import flask


def detect_url_encoded_wildcards() -> dict[str, set[str]]:
    """
    Detect URL-encoded wildcards in the raw query string.

    Returns a dictionary mapping filter paths to sets of values that contain
    URL-encoded wildcards (%2A). This allows the filtering logic to distinguish
    between literal asterisks (URL-encoded as %2A) and wildcard asterisks (unencoded).

    Returns:
        Dict mapping filter paths like "system_profile.os_release" to sets of
        values that were URL-encoded with %2A wildcards.
    """
    if not hasattr(flask, "request") or not flask.request:
        return {}

    # Get the raw query string before URL decoding
    raw_query = flask.request.environ.get("QUERY_STRING", "")
    if not raw_query:
        return {}

    encoded_wildcard_values = {}

    # Pattern to match filter[system_profile][field]=value or filter[system_profile][field][op]=value
    # This captures both simple and complex filter patterns
    filter_pattern = r"filter\[system_profile\](?:\[([^\]]+)\])+=(.*?)(?:&|$)"

    for match in re.finditer(filter_pattern, raw_query):
        full_match = match.group(0)
        value_part = match.group(2)

        # Check if the value contains URL-encoded asterisk (%2A)
        if "%2A" in value_part:
            # Extract the field path from the filter parameter
            field_path_match = re.search(r"filter\[system_profile\](.+?)=", full_match)
            if field_path_match:
                field_path_raw = field_path_match.group(1)
                # Parse the field path (e.g., [os_release] or [insights_client_version][eq])
                field_parts = re.findall(r"\[([^\]]+)\]", field_path_raw)
                if field_parts:
                    # Build the field path (e.g., "os_release" or "insights_client_version")
                    field_name = field_parts[0]
                    field_key = f"system_profile.{field_name}"

                    # Decode the value to get what the filter logic will see
                    decoded_value = unquote(value_part)

                    if field_key not in encoded_wildcard_values:
                        encoded_wildcard_values[field_key] = set()
                    encoded_wildcard_values[field_key].add(decoded_value)

    return encoded_wildcard_values


def should_treat_as_literal(field_name: str, value: str, encoded_wildcards: dict[str, set[str]]) -> bool:
    """
    Determine if a wildcard character in a filter value should be treated as literal.

    Args:
        field_name: The system profile field name (e.g., "os_release")
        value: The filter value that may contain wildcards
        encoded_wildcards: Dictionary from detect_url_encoded_wildcards()

    Returns:
        True if wildcards in the value should be treated as literal characters,
        False if they should be treated as wildcard patterns.
    """
    field_key = f"system_profile.{field_name}"
    return field_key in encoded_wildcards and value in encoded_wildcards[field_key]


def escape_literal_wildcards(value: str) -> str:
    """
    Escape wildcard characters to be treated literally in PostgreSQL ILIKE.

    Args:
        value: The value that should be matched literally

    Returns:
        The value with wildcard characters escaped for literal matching
    """
    # In PostgreSQL ILIKE, we need to escape special characters
    # * becomes \* and % becomes \% and \ becomes \\
    escaped = value.replace("\\", "\\\\")  # Escape backslashes first
    escaped = escaped.replace("%", "\\%")  # Escape existing % characters
    escaped = escaped.replace("*", "\\*")  # Escape asterisks to be literal
    return escaped
