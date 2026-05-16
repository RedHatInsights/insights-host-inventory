"""
Test for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

This test verifies that the wildcard filtering logic correctly distinguishes between:
1. Literal asterisk characters (should use exact matching)
2. Wildcard patterns (should use pattern matching)
3. Values with problematic ILIKE characters (should use exact matching)
"""

from api.filtering.db_custom_filters import _should_use_exact_match_for_wildcard_field


class TestWildcardFix:
    """Test the wildcard filtering fix for RHINENG-4809."""

    def test_should_use_exact_match_for_wildcard_field(self):
        """Test the logic for determining when to use exact vs pattern matching."""

        # Test cases that should use exact matching (literal characters)
        exact_match_cases = [
            "abc*123",  # Asterisk in middle (literal)
            "test*value\\path",  # Contains asterisk and backslash
            "value_with_underscore",  # Contains underscore (ILIKE special char)
            "value%with%percent",  # Contains percent (ILIKE special char)
            "test\\backslash",  # Contains backslash (ILIKE escape char)
            "complex*value\\test_123%end",  # Multiple special characters
            "",  # Empty string
            "*literal",  # Asterisk at beginning
            "**multiple",  # Multiple asterisks
            "*",  # Single asterisk only
            "a*b*c",  # Multiple asterisks
        ]

        for value in exact_match_cases:
            assert _should_use_exact_match_for_wildcard_field(value), f"Should use exact match for: {value}"

        # Test cases that should use pattern matching (wildcard patterns)
        pattern_match_cases = [
            "abc*",  # Simple trailing wildcard
            "test*",  # Simple trailing wildcard
            "prefix*",  # Simple trailing wildcard
            "3.0.*",  # Version wildcard pattern
            "insights*",  # Simple trailing wildcard
        ]

        for value in pattern_match_cases:
            assert not _should_use_exact_match_for_wildcard_field(value), f"Should use pattern match for: {value}"

    def test_problematic_characters(self):
        """Test that values with problematic ILIKE characters use exact matching."""

        problematic_cases = [
            "test\\path",  # Backslash (escape character in ILIKE)
            "test%value",  # Percent (multi-char wildcard in ILIKE)
            "test_value",  # Underscore (single-char wildcard in ILIKE)
            "complex\\test%value_123",  # Multiple problematic chars
        ]

        for value in problematic_cases:
            assert _should_use_exact_match_for_wildcard_field(value), (
                f"Should use exact match for problematic chars: {value}"
            )

    def test_simple_values_without_special_chars(self):
        """Test that simple values without special characters use exact matching."""

        simple_cases = [
            "simple",
            "normalvalue",
            "123",
            "x86_64",  # This should use exact matching (not a wildcard field)
        ]

        for value in simple_cases:
            assert _should_use_exact_match_for_wildcard_field(value), (
                f"Should use exact match for simple value: {value}"
            )

    def test_edge_cases(self):
        """Test edge cases for wildcard detection."""

        # These should use exact matching
        exact_match_edge_cases = [
            "*abc",  # Starts with asterisk
            "a*b",  # Asterisk in middle
            "**",  # Multiple asterisks
            "***",  # Multiple asterisks
        ]

        for value in exact_match_edge_cases:
            assert _should_use_exact_match_for_wildcard_field(value), f"Should use exact match for edge case: {value}"

        # These should use pattern matching
        pattern_match_edge_cases = [
            "a*",  # Single char with trailing wildcard
            "123*",  # Numbers with trailing wildcard
            "version*",  # Word with trailing wildcard
        ]

        for value in pattern_match_edge_cases:
            assert not _should_use_exact_match_for_wildcard_field(value), (
                f"Should use pattern match for edge case: {value}"
            )
