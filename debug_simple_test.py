#!/usr/bin/env python3

# Test the URL parsing logic directly
from urllib.parse import unquote

# Placeholder for URL-encoded asterisks
_ENCODED_ASTERISK_PLACEHOLDER = "__ENCODED_ASTERISK_PLACEHOLDER__"

def test_url_parsing():
    # Simulate what happens in the parsing
    original_value = "app%2Aconfig.json"
    print(f"Original value: {original_value}")

    # Replace %2A with placeholder before unquoting
    value_with_placeholder = original_value.replace("%2A", _ENCODED_ASTERISK_PLACEHOLDER)
    print(f"With placeholder: {value_with_placeholder}")

    # URL decode
    decoded_value = unquote(value_with_placeholder)
    print(f"Decoded value: {decoded_value}")

    # Now simulate the filtering logic
    value = decoded_value
    print(f"\nFiltering logic:")
    print(f"Input value: {value}")

    # Convert unescaped asterisks to SQL wildcards
    value = value.replace("*", "%")
    print(f"After * -> %: {value}")

    # Restore literal asterisks from placeholders
    value = value.replace(_ENCODED_ASTERISK_PLACEHOLDER, "*")
    print(f"After placeholder -> *: {value}")

    print(f"\nFinal SQL value: {value}")

if __name__ == "__main__":
    test_url_parsing()
