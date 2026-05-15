"""
Test for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

This test verifies the fix for the issue where URL-encoded wildcards (%2A) were
incorrectly being treated as SQL wildcards instead of literal asterisk characters.

The fix ensures that:
1. %2A (URL-encoded asterisk) is treated as a literal asterisk
2. * (actual asterisk) is treated as a wildcard
3. Other URL-encoded characters are handled correctly
"""

from api.filtering.db_custom_filters import _process_wildcard_value


class TestRHINENG4809Fix:
    """Test class for RHINENG-4809 fix verification."""

    def test_issue_example_os_release(self):
        """Test the exact example from the issue description."""
        # The issue states that "filter[system_profile][os_release]=abc%2A123"
        # should only match hosts with os_release == "abc*123"
        # but was incorrectly matching hosts like "abc.123", "abcdefghijkl123"

        # Test URL-encoded asterisk - should become literal asterisk
        result = _process_wildcard_value("abc%2A123")
        assert result == "abc*123"

        # Test actual asterisk - should become SQL wildcard
        result = _process_wildcard_value("abc*123")
        assert result == "abc%123"

    def test_issue_example_backslash_escaping(self):
        """Test the backslash escaping example from the issue."""
        # The issue mentions: "test1*test2\\test3" should be findable with "test1%2Atest2%5Ctest3"
        result = _process_wildcard_value("test1%2Atest2%5Ctest3")
        assert result == "test1*test2\\test3"

    def test_wildcard_fields_behavior(self):
        """Test behavior with fields that support wildcards (x-wildcard: true)."""
        # Fields like os_release, insights_client_version, bios_release_date support wildcards

        # Test os_release patterns
        assert _process_wildcard_value("7.4") == "7.4"  # No wildcards
        assert _process_wildcard_value("7.*") == "7.%"  # Wildcard
        assert _process_wildcard_value("7.%2A") == "7.*"  # URL-encoded literal asterisk

        # Test insights_client_version patterns
        assert _process_wildcard_value("3.0.1-2.el4_2") == "3.0.1-2.el4_2"  # Exact match
        assert _process_wildcard_value("3.0.*") == "3.0.%"  # Wildcard
        assert _process_wildcard_value("3.0.%2A") == "3.0.*"  # URL-encoded literal asterisk

        # Test bios_release_date patterns
        assert _process_wildcard_value("2023-01-15") == "2023-01-15"  # Exact match
        assert _process_wildcard_value("2023*01*15") == "2023%01%15"  # Wildcards
        assert _process_wildcard_value("2023%2A01%2A15") == "2023*01*15"  # URL-encoded literal asterisks

    def test_mixed_scenarios(self):
        """Test complex scenarios with mixed wildcards and URL encoding."""
        # Mix of wildcards and URL-encoded asterisks
        assert _process_wildcard_value("*%2A*") == "%*%"

        # Multiple URL-encoded asterisks
        assert _process_wildcard_value("%2A%2A%2A") == "***"

        # URL-encoded asterisk with other encoded characters
        assert _process_wildcard_value("test%2Avalue%26more") == "test*value&more"

        # Wildcard with other encoded characters
        assert _process_wildcard_value("test*value%26more") == "test%value&more"

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty string
        assert _process_wildcard_value("") == ""

        # Only wildcards
        assert _process_wildcard_value("***") == "%%%"

        # Only URL-encoded asterisks
        assert _process_wildcard_value("%2A%2A%2A") == "***"

        # No special characters
        assert _process_wildcard_value("simple_string") == "simple_string"

        # URL-encoded characters without asterisks
        assert _process_wildcard_value("test%20value%26more") == "test value&more"

    def test_backwards_compatibility(self):
        """Test that existing wildcard behavior is preserved."""
        # These patterns should work the same as before the fix

        # Simple wildcards
        assert _process_wildcard_value("*") == "%"
        assert _process_wildcard_value("test*") == "test%"
        assert _process_wildcard_value("*test") == "%test"
        assert _process_wildcard_value("*test*") == "%test%"

        # Multiple wildcards
        assert _process_wildcard_value("a*b*c") == "a%b%c"

        # No wildcards
        assert _process_wildcard_value("exact_match") == "exact_match"

    def test_url_decoding_without_asterisks(self):
        """Test that URL decoding works correctly for non-asterisk characters."""
        # Common URL-encoded characters
        assert _process_wildcard_value("test%20space") == "test space"
        assert _process_wildcard_value("test%26ampersand") == "test&ampersand"
        assert _process_wildcard_value("test%5Cbackslash") == "test\\backslash"
        assert _process_wildcard_value("test%2Bplus") == "test+plus"

        # Multiple encoded characters
        assert _process_wildcard_value("test%20%26%5C") == "test &\\"

    def test_real_world_scenarios(self):
        """Test scenarios that might occur in real-world usage."""
        # Version strings with literal asterisks
        assert _process_wildcard_value("1.0.%2A-release") == "1.0.*-release"

        # File paths with literal asterisks
        assert _process_wildcard_value("/path/to/file%2A.txt") == "/path/to/file*.txt"

        # Configuration values with literal asterisks
        assert _process_wildcard_value("config%2Avalue%2Atest") == "config*value*test"

        # Search patterns with wildcards
        assert _process_wildcard_value("search*pattern") == "search%pattern"

        # Mixed patterns
        assert _process_wildcard_value("prefix%2Aliteral*wildcard%2Asuffix") == "prefix*literal%wildcard*suffix"
