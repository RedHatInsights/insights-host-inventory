"""
Unit tests for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

These tests verify the URL parsing logic for preserving encoded asterisks
without requiring a database connection.
"""

from urllib.parse import unquote

from api.filtering.db_custom_filters import _handle_wildcard_replacement
from api.parsing import _preserve_encoded_wildcards
from api.parsing import get_encoded_asterisk_marker


def test_preserve_encoded_wildcards():
    """Test that URL-encoded asterisks are preserved with markers."""
    # Test uppercase encoding
    result = _preserve_encoded_wildcards("abc%2A123")
    assert "%2A" not in result
    assert get_encoded_asterisk_marker() in result

    # Test lowercase encoding
    result = _preserve_encoded_wildcards("abc%2a123")
    assert "%2a" not in result
    assert get_encoded_asterisk_marker() in result

    # Test mixed content
    result = _preserve_encoded_wildcards("prefix%2Amiddle*suffix%2aend")
    assert result.count(get_encoded_asterisk_marker()) == 2
    assert "*" in result  # Unencoded asterisk should remain


def test_wildcard_replacement_logic():
    """Test the wildcard replacement logic that distinguishes literal from wildcard asterisks."""
    marker = get_encoded_asterisk_marker()

    # Test case 1: Only wildcard asterisks (should be replaced with %)
    result = _handle_wildcard_replacement("abc*123")
    assert result == "abc%123"

    # Test case 2: Only literal asterisks (should remain as *)
    result = _handle_wildcard_replacement(f"abc{marker}123")
    assert result == "abc*123"

    # Test case 3: Mixed literal and wildcard asterisks
    result = _handle_wildcard_replacement(f"prefix{marker}literal*wildcard{marker}end")
    assert result == "prefix*literal%wildcard*end"

    # Test case 4: Multiple wildcards
    result = _handle_wildcard_replacement("*start*middle*end*")
    assert result == "%start%middle%end%"

    # Test case 5: Multiple literals
    result = _handle_wildcard_replacement(f"{marker}start{marker}middle{marker}end{marker}")
    assert result == "*start*middle*end*"


def test_round_trip_encoding():
    """Test the complete round-trip: preserve -> URL decode -> wildcard replacement."""
    original = "test%2Awildcard*literal%2Aend"

    # Step 1: Preserve encoded asterisks
    preserved = _preserve_encoded_wildcards(original)
    # After this step: "test<MARKER>wildcard*literal<MARKER>end"

    # Step 2: URL decoding (this would happen in the framework)
    # The markers remain in place, only other URL-encoded chars are decoded
    decoded = unquote(preserved)

    # Step 3: Apply wildcard replacement
    final = _handle_wildcard_replacement(decoded)

    # The result should have:
    # - Original %2A -> literal * (preserved)
    # - Original * -> wildcard % (replaced)
    expected = "test*wildcard%literal*end"
    assert final == expected


def test_edge_cases():
    """Test edge cases for the wildcard handling."""
    # Empty string
    assert _handle_wildcard_replacement("") == ""

    # No asterisks
    assert _handle_wildcard_replacement("no_asterisks") == "no_asterisks"

    # Only asterisks
    assert _handle_wildcard_replacement("***") == "%%%"

    # Only encoded asterisks
    marker = get_encoded_asterisk_marker()
    result = _handle_wildcard_replacement(f"{marker}{marker}{marker}")
    assert result == "***"


def test_backslash_handling():
    """Test that backslash encoding is also preserved (mentioned in the ticket)."""
    # Test backslash preservation
    result = _preserve_encoded_wildcards("test%5Cbackslash")
    assert "%5C" not in result

    result = _preserve_encoded_wildcards("test%5cbackslash")
    assert "%5c" not in result


def test_realistic_scenario():
    """Test a realistic scenario from the ticket description."""
    # Scenario: User wants to filter for hosts with os_release exactly "abc*123"
    # They URL-encode the asterisk to avoid wildcard behavior
    user_input = "abc%2A123"

    # Step 1: Our parsing preserves the encoded asterisk
    preserved = _preserve_encoded_wildcards(user_input)

    # Step 2: Framework does URL decoding
    decoded = unquote(preserved)

    # Step 3: Wildcard replacement preserves literal asterisks
    final = _handle_wildcard_replacement(decoded)

    # The final result should be the literal asterisk, not a wildcard
    assert final == "abc*123"

    # Compare with unencoded input (should become wildcard)
    unencoded_final = _handle_wildcard_replacement("abc*123")
    assert unencoded_final == "abc%123"

    # Verify they're different
    assert final != unencoded_final


def test_complex_mixed_scenario():
    """Test a complex scenario with multiple encoded and unencoded asterisks."""
    # Input: "start%2Aliteral*wildcard%2Amore*end"
    # Expected: literal asterisks from %2A, wildcards from unencoded *
    user_input = "start%2Aliteral*wildcard%2Amore*end"

    # Process through the pipeline
    preserved = _preserve_encoded_wildcards(user_input)
    decoded = unquote(preserved)
    final = _handle_wildcard_replacement(decoded)

    # Expected result: "start*literal%wildcard*more%end"
    # - start%2A -> start* (literal)
    # - literal* -> literal% (wildcard)
    # - %2Amore -> *more (literal)
    # - *end -> %end (wildcard)
    expected = "start*literal%wildcard*more%end"
    assert final == expected


def test_backslash_escaping_scenario():
    """Test the backslash escaping issue mentioned in the ticket."""
    # The ticket mentions: "test1*test2\test3" with URL encoding "test1%2Atest2%5Ctest3"
    user_input = "test1%2Atest2%5Ctest3"

    # Process through the pipeline
    preserved = _preserve_encoded_wildcards(user_input)
    decoded = unquote(preserved)

    # For this test, we're mainly concerned with the asterisk handling
    # The backslash handling would be separate logic
    final = _handle_wildcard_replacement(decoded)

    # The asterisk should be preserved as literal
    assert "*" in final
    assert "%" not in final  # No wildcards since the asterisk was encoded
