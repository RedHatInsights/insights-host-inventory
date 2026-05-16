"""Utilities for handling URL-encoded characters in filter values."""

import re
from urllib.parse import unquote

from flask import request


def contains_url_encoded_asterisk(filter_path: str, value: str) -> bool:
    """
    Check if the original query string contained URL-encoded asterisks (%2A) for this filter.

    Args:
        filter_path: The filter path, e.g., "filter[system_profile][os_release]"
        value: The decoded value to check

    Returns:
        True if the original query contained %2A that decoded to * in this value
    """
    if "*" not in value:
        return False

    # Get the raw query string
    query_string = request.environ.get("QUERY_STRING", "")
    if not query_string:
        return False

    # Look for this specific filter parameter in the query string
    # Handle both bracket notation and equals notation
    # e.g., filter[system_profile][os_release]=abc%2A123
    # or filter%5Bsystem_profile%5D%5Bos_release%5D=abc%2A123

    # Create patterns to match this filter parameter
    patterns = []

    # Pattern 1: Direct bracket notation
    escaped_path = re.escape(filter_path)
    patterns.append(f"{escaped_path}=([^&]*)")

    # Pattern 2: URL-encoded bracket notation
    url_encoded_path = filter_path.replace("[", "%5B").replace("]", "%5D")
    escaped_encoded_path = re.escape(url_encoded_path)
    patterns.append(f"{escaped_encoded_path}=([^&]*)")

    for pattern in patterns:
        matches = re.findall(pattern, query_string, re.IGNORECASE)
        for match in matches:
            # Check if this encoded value contains %2A and decodes to our value
            if "%2A" in match.upper() or "%2a" in match:
                decoded_match = unquote(match)
                if decoded_match == value:
                    return True

    return False


def escape_ilike_special_chars(value: str) -> str:
    r"""
    Escape special characters in PostgreSQL ILIKE patterns for literal matching.

    In PostgreSQL ILIKE:
    - % matches any sequence of characters
    - _ matches any single character
    - \ is the escape character

    Args:
        value: The value to escape

    Returns:
        The value with ILIKE special characters escaped
    """
    # Escape backslashes first (they're the escape character)
    value = value.replace("\\", "\\\\")
    # Escape percent signs (wildcard)
    value = value.replace("%", "\\%")
    # Escape underscores (single character wildcard)
    value = value.replace("_", "\\_")
    return value
