"""
Utilities for handling URL-encoded wildcards in system profile filtering.

This module provides functions to detect URL-encoded wildcards (%2A) in the raw
query string and handle them appropriately in filtering operations.
"""

import re
from urllib.parse import unquote

from flask import g
from flask import has_request_context
from flask import request


def detect_url_encoded_wildcards() -> dict[str, set[str]]:
    """
    Detect URL-encoded wildcards in the raw query string.

    Returns a dictionary mapping filter paths to sets of values that contain
    URL-encoded wildcards (%2A or %2a). This allows the filtering logic to distinguish
    between literal asterisks (URL-encoded as %2A) and wildcard asterisks (unencoded).

    Results are cached per request to avoid repeated regex parsing.

    Returns:
        Dict mapping filter paths like "system_profile.os_release" to sets of
        values that were URL-encoded with %2A wildcards.
    """
    if not has_request_context():
        return {}

    # Check if we've already computed this for the current request
    if hasattr(g, "_url_encoded_wildcards_cache"):
        return g._url_encoded_wildcards_cache

    # Get the raw query string before URL decoding
    raw_query = request.environ.get("QUERY_STRING", "")
    if not raw_query:
        g._url_encoded_wildcards_cache = {}
        return {}

    encoded_wildcard_values = {}

    # Pattern to match filter[system_profile][field]=value or filter[system_profile][field][op]=value
    # Capture the field path and value directly
    filter_pattern = r"filter\[system_profile\]((?:\[[^\]]+\])+)=(.*?)(?:&|$)"

    for match in re.finditer(filter_pattern, raw_query):
        field_path_raw = match.group(1)
        value_part = match.group(2)

        # Check if the value contains URL-encoded asterisk (%2A or %2a - case insensitive)
        if re.search(r"%2[Aa]", value_part):
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

    # Cache the result for this request
    g._url_encoded_wildcards_cache = encoded_wildcard_values
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
