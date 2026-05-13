"""
Test for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

This test verifies that URL-encoded asterisks (%2A) are treated as literal characters
and not as wildcards in system profile filtering.
"""

import pytest
from urllib.parse import quote

from api.parsing import customURIParser, LITERAL_ASTERISK_PLACEHOLDER
from api.filtering.db_custom_filters import _handle_wildcard_value
from tests.helpers.api_utils import assert_response_status, build_hosts_url


class TestWildcardUrlEncodingFix:
    """Test wildcard filtering with URL-encoded asterisks."""

    def test_literal_asterisk_placeholder_handling(self):
        """Test that _handle_wildcard_value correctly handles literal asterisks."""
        # Test case 1: Literal asterisk (from URL-encoded %2A)
        literal_value = f"abc{LITERAL_ASTERISK_PLACEHOLDER}123"
        result = _handle_wildcard_value(literal_value, "wildcard")
        assert result == "abc*123", "Literal asterisk should be preserved"

        # Test case 2: Wildcard asterisk
        wildcard_value = "abc*123"
        result = _handle_wildcard_value(wildcard_value, "wildcard")
        assert result == "abc%123", "Wildcard asterisk should be converted to %"

        # Test case 3: Mixed literal and wildcard
        mixed_value = f"abc{LITERAL_ASTERISK_PLACEHOLDER}def*ghi"
        result = _handle_wildcard_value(mixed_value, "wildcard")
        assert result == "abc*def%ghi", "Mixed literal and wildcard should be handled correctly"

        # Test case 4: Non-wildcard field should not be modified
        non_wildcard_value = f"abc{LITERAL_ASTERISK_PLACEHOLDER}123"
        result = _handle_wildcard_value(non_wildcard_value, "string")
        assert result == non_wildcard_value, "Non-wildcard field should not be modified"

    def test_url_parsing_preserves_literal_asterisks(self):
        """Test that URL parsing correctly preserves literal asterisks."""
        parser = customURIParser()
        
        # Mock the param definitions (simplified for testing)
        parser.param_defns = {}
        parser.param_schemas = {}
        
        # Test URL-encoded asterisk
        params = {
            'test_param': ['abc%2A123']
        }
        
        resolved = parser.resolve_params(params, 'query')
        
        # The resolved value should have literal asterisk preserved
        assert 'test_param' in resolved
        actual = resolved['test_param']
        
        # Should contain either the placeholder or the restored literal asterisk
        assert '*' in actual, "Literal asterisk should be preserved after URL parsing"

    def test_wildcard_filtering_with_url_encoded_asterisk(self, api_get, db_create_host):
        """Test that URL-encoded asterisks are treated as literal characters in filtering."""
        # Create test hosts with different os_release values
        host_literal = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "test1*test2"}}
        )
        host_wildcard_match = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "test1xtest2"}}
        )
        host_no_match = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "different"}}
        )

        # Test 1: URL-encoded asterisk should match only the literal asterisk
        url_encoded_filter = quote("test1*test2").replace("*", "%2A")
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_filter}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        
        # Should only match the host with literal asterisk
        result_ids = [r["id"] for r in response_data["results"]]
        assert str(host_literal.id) in result_ids, "Should match host with literal asterisk"
        assert str(host_wildcard_match.id) not in result_ids, "Should not match host via wildcard"
        assert str(host_no_match.id) not in result_ids, "Should not match unrelated host"

        # Test 2: Regular asterisk should work as wildcard
        url = build_hosts_url(query="?filter[system_profile][os_release]=test1*test2")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        
        # Should match both hosts (literal and wildcard match)
        result_ids = [r["id"] for r in response_data["results"]]
        assert str(host_literal.id) in result_ids, "Should match host with literal asterisk"
        assert str(host_wildcard_match.id) in result_ids, "Should match host via wildcard"
        assert str(host_no_match.id) not in result_ids, "Should not match unrelated host"

    def test_backslash_escaping_with_url_encoded_asterisk(self, api_get, db_create_host):
        """Test the specific case mentioned in the ticket with backslash and asterisk."""
        # Create a host with the exact value from the ticket
        host_with_backslash = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "test1*test2\\test3"}}
        )

        # URL-encode the filter value: test1*test2\test3 -> test1%2Atest2%5Ctest3
        filter_value = "test1*test2\\test3"
        url_encoded_filter = quote(filter_value)
        
        # Replace the asterisk with %2A to test literal asterisk
        url_encoded_filter = url_encoded_filter.replace("*", "%2A")
        
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_filter}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        
        # Should match the host with the exact literal value
        result_ids = [r["id"] for r in response_data["results"]]
        assert str(host_with_backslash.id) in result_ids, "Should match host with literal asterisk and backslash"

    def test_multiple_url_encoded_asterisks(self, api_get, db_create_host):
        """Test filtering with multiple URL-encoded asterisks."""
        # Create hosts with different patterns
        host_multiple_literal = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "a*b*c"}}
        )
        host_wildcard_match1 = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "axbxc"}}
        )
        host_wildcard_match2 = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "a1b2c"}}
        )

        # URL-encode both asterisks as literal
        url_encoded_filter = "a%2Ab%2Ac"
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_filter}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        
        # Should only match the host with literal asterisks
        result_ids = [r["id"] for r in response_data["results"]]
        assert str(host_multiple_literal.id) in result_ids, "Should match host with literal asterisks"
        assert str(host_wildcard_match1.id) not in result_ids, "Should not match via wildcard"
        assert str(host_wildcard_match2.id) not in result_ids, "Should not match via wildcard"

    def test_mixed_literal_and_wildcard_asterisks(self, api_get, db_create_host):
        """Test filtering with mixed literal and wildcard asterisks."""
        # Create hosts for testing mixed patterns
        host_mixed = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "prefix*literal_suffix"}}
        )
        host_wildcard_match = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "prefixxliteral_suffix"}}
        )

        # Use one literal asterisk (%2A) and one wildcard (*)
        # This should match: prefix + anything + literal* + literal_suffix
        url_encoded_filter = "prefix*%2Aliteral_suffix"
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_filter}")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        
        # Should match the host where the pattern fits
        result_ids = [r["id"] for r in response_data["results"]]
        assert str(host_mixed.id) in result_ids, "Should match host with mixed pattern"