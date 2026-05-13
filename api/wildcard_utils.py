"""
Utilities for handling wildcard filtering with proper URL-encoded asterisk support.

This module provides functions to distinguish between literal asterisks (URL-encoded as %2A)
and wildcard asterisks (passed as literal * in URLs) for system profile filtering.
"""

import re
from urllib.parse import unquote

# Special placeholder for URL-encoded asterisks to preserve them through processing
LITERAL_ASTERISK_PLACEHOLDER = "__LITERAL_ASTERISK__"


def preserve_url_encoded_asterisks(query_string: str) -> str:
    """
    Replace URL-encoded asterisks (%2A) with a placeholder to preserve them as literals.
    
    This function processes the raw query string before URL decoding to distinguish
    between literal asterisks (originally %2A) and wildcard asterisks (originally *).
    
    Args:
        query_string: Raw query string from the HTTP request
        
    Returns:
        Modified query string with %2A replaced by placeholder
    """
    if not query_string:
        return query_string
    
    # Replace %2A (case insensitive) with our placeholder
    # This preserves the literal asterisk intent through URL decoding
    return re.sub(r'%2[aA]', LITERAL_ASTERISK_PLACEHOLDER, query_string)


def restore_literal_asterisks(value: str) -> str:
    """
    Restore literal asterisks from placeholders in filter values.
    
    Args:
        value: Filter value that may contain literal asterisk placeholders
        
    Returns:
        Value with placeholders replaced by literal asterisks
    """
    if not isinstance(value, str):
        return value
    
    return value.replace(LITERAL_ASTERISK_PLACEHOLDER, "*")


def apply_wildcard_filtering(value: str, is_wildcard_field: bool = False) -> str:
    """
    Apply wildcard filtering logic, converting wildcard asterisks to SQL LIKE patterns.
    
    This function:
    1. Preserves literal asterisks (from URL-encoded %2A) as-is
    2. Converts wildcard asterisks to SQL % patterns for LIKE queries
    
    Args:
        value: The filter value to process
        is_wildcard_field: Whether this field supports wildcard filtering
        
    Returns:
        Processed value with wildcards converted to SQL patterns
    """
    if not isinstance(value, str) or not is_wildcard_field:
        return value
    
    # First, restore any literal asterisks from placeholders
    # These should remain as literal "*" characters in the final query
    value_with_literals = restore_literal_asterisks(value)
    
    # Now convert any remaining "*" characters to SQL wildcard patterns
    # These are the ones that were originally "*" in the URL (not %2A)
    return value_with_literals.replace("*", "%")


def process_filter_value_for_wildcards(value: str, field_name: str, system_profile_spec: dict) -> str:
    """
    Process a filter value for wildcard handling based on the field specification.
    
    Args:
        value: The filter value to process
        field_name: Name of the field being filtered
        system_profile_spec: System profile specification dictionary
        
    Returns:
        Processed value with appropriate wildcard handling
    """
    if not isinstance(value, str):
        return value
    
    # Check if this field supports wildcards by looking up the spec
    is_wildcard_field = _field_supports_wildcards(field_name, system_profile_spec)
    
    return apply_wildcard_filtering(value, is_wildcard_field)


def _field_supports_wildcards(field_name: str, system_profile_spec: dict) -> bool:
    """
    Check if a field supports wildcard filtering based on the system profile spec.
    
    Args:
        field_name: Name of the field to check
        system_profile_spec: System profile specification dictionary
        
    Returns:
        True if the field supports wildcards (has x-wildcard: true)
    """
    if not system_profile_spec or not field_name:
        return False
    
    # Navigate through the spec to find the field
    field_spec = _get_field_spec(field_name, system_profile_spec)
    
    if field_spec and isinstance(field_spec, dict):
        return field_spec.get("x-wildcard", False)
    
    return False


def _get_field_spec(field_name: str, spec: dict, path: list = None) -> dict:
    """
    Recursively find a field specification in the system profile spec.
    
    Args:
        field_name: Name of the field to find
        spec: Current level of the specification
        path: Current path in the spec (for nested fields)
        
    Returns:
        Field specification dictionary or None if not found
    """
    if path is None:
        path = []
    
    # Direct field lookup
    if field_name in spec:
        return spec[field_name]
    
    # Look in properties if this is an object spec
    if "properties" in spec and field_name in spec["properties"]:
        return spec["properties"][field_name]
    
    # Look in children if this is a nested spec
    if "children" in spec and field_name in spec["children"]:
        return spec["children"][field_name]
    
    # Recursively search in nested objects
    for key, value in spec.items():
        if isinstance(value, dict):
            if key in ("properties", "children"):
                result = _get_field_spec(field_name, value, path + [key])
                if result:
                    return result
            elif "properties" in value:
                result = _get_field_spec(field_name, value["properties"], path + [key, "properties"])
                if result:
                    return result
            elif "children" in value:
                result = _get_field_spec(field_name, value["children"], path + [key, "children"])
                if result:
                    return result
    
    return None