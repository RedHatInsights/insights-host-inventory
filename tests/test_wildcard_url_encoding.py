"""
Tests for URL-encoded wildcard handling in system profile filters.

This module tests the fix for RHINENG-4809, which ensures that URL-encoded
asterisks (%2A) are treated as literal characters rather than wildcards.
"""

from tests.helpers.api_utils import build_hosts_url


class TestWildcardUrlEncoding:
    """Test cases for URL-encoded wildcard handling."""

    def test_url_encoded_asterisk_treated_as_literal(self, db_create_host, api_get):
        """Test that %2A (URL-encoded *) is treated as a literal asterisk character."""
        # Create a host with a literal asterisk in os_release
        host_with_literal_asterisk = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1*test2"}})

        # Create a host that would match a wildcard pattern but not the literal
        host_with_wildcard_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1abctest2"}})

        # Create a host that doesn't match either pattern
        host_no_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "different_value"}})

        # Test with URL-encoded asterisk - should match only the literal asterisk
        url = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with literal asterisk
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_with_wildcard_match.id) not in response_ids
        assert str(host_no_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_unencoded_asterisk_treated_as_wildcard(self, db_create_host, api_get):
        """Test that unencoded * is treated as a wildcard character."""
        # Create a host with a literal asterisk in os_release
        host_with_literal_asterisk = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1*test2"}})

        # Create a host that would match a wildcard pattern
        host_with_wildcard_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1abctest2"}})

        # Create a host that doesn't match the pattern
        host_no_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "different_value"}})

        # Test with unencoded asterisk - should match both literal and wildcard patterns
        url = build_hosts_url(query="?filter[system_profile][os_release]=test1*test2")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match both hosts (literal asterisk and wildcard match)
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_with_wildcard_match.id) in response_ids
        assert str(host_no_match.id) not in response_ids
        assert len(response_ids) == 2

    def test_insights_client_version_url_encoded_asterisk(self, db_create_host, api_get):
        """Test URL-encoded asterisk handling for insights_client_version field."""
        # Create a host with a literal asterisk in insights_client_version
        host_with_literal_asterisk = db_create_host(
            extra_data={"system_profile_facts": {"insights_client_version": "3.0.1*2.el4_2"}}
        )

        # Create a host that would match a wildcard pattern
        host_with_wildcard_match = db_create_host(
            extra_data={"system_profile_facts": {"insights_client_version": "3.0.1-2.el4_2"}}
        )

        # Test with URL-encoded asterisk - should match only the literal asterisk
        url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.1%2A2.el4_2")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with literal asterisk
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_with_wildcard_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_bios_release_date_url_encoded_asterisk(self, db_create_host, api_get):
        """Test URL-encoded asterisk handling for bios_release_date field."""
        # Create a host with a literal asterisk in bios_release_date
        host_with_literal_asterisk = db_create_host(
            extra_data={"system_profile_facts": {"bios_release_date": "2023*01*15"}}
        )

        # Create a host that would match a wildcard pattern
        host_with_wildcard_match = db_create_host(
            extra_data={"system_profile_facts": {"bios_release_date": "2023-01-15"}}
        )

        # Test with URL-encoded asterisk - should match only the literal asterisk
        url = build_hosts_url(query="?filter[system_profile][bios_release_date]=2023%2A01%2A15")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with literal asterisk
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_with_wildcard_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_mixed_encoded_and_unencoded_asterisks(self, db_create_host, api_get):
        """Test handling of mixed encoded and unencoded asterisks in the same value."""
        # Create a host with mixed asterisks
        host_with_mixed = db_create_host(extra_data={"system_profile_facts": {"os_release": "test*literal*value"}})

        # Create a host that would match if both were wildcards
        host_wildcard_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "testXliteralYvalue"}})

        # Test with one encoded and one unencoded asterisk
        # This should be treated as literal since at least one asterisk was encoded
        url = build_hosts_url(query="?filter[system_profile][os_release]=test%2Aliteral*value")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with the exact literal pattern
        assert str(host_with_mixed.id) in response_ids
        assert str(host_wildcard_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_workloads_field_url_encoded_asterisk(self, db_create_host, api_get):
        """Test URL-encoded asterisk handling for workloads fields."""
        # Create a host with a literal asterisk in mssql version
        host_with_literal_asterisk = db_create_host(
            extra_data={"system_profile_facts": {"workloads": {"mssql": {"version": "15.2*0"}}}}
        )

        # Create a host that would match a wildcard pattern
        host_with_wildcard_match = db_create_host(
            extra_data={"system_profile_facts": {"workloads": {"mssql": {"version": "15.2.0"}}}}
        )

        # Test with URL-encoded asterisk - should match only the literal asterisk
        url = build_hosts_url(query="?filter[system_profile][workloads][mssql][version]=15.2%2A0")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with literal asterisk
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_with_wildcard_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_backslash_escaping_with_url_encoded_asterisk(self, db_create_host, api_get):
        """Test the example from the ticket: backslash escaping with URL-encoded asterisk."""
        # Create a host with the exact value from the ticket
        host_with_special_chars = db_create_host(
            extra_data={"system_profile_facts": {"os_release": "test1*test2\\test3"}}
        )

        # Create a host that shouldn't match
        host_no_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1Xtest2Ytest3"}})

        # Test with URL-encoded asterisk and backslash
        # This should match the exact literal value
        url = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with the exact literal pattern
        assert str(host_with_special_chars.id) in response_ids
        assert str(host_no_match.id) not in response_ids
        assert len(response_ids) == 1

    def test_no_asterisk_in_value(self, db_create_host, api_get):
        """Test that values without asterisks work normally regardless of encoding."""
        # Create a host with a normal value
        host_normal = db_create_host(extra_data={"system_profile_facts": {"os_release": "normal_value"}})

        # Test with normal value - should work the same way
        url = build_hosts_url(query="?filter[system_profile][os_release]=normal_value")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        assert str(host_normal.id) in response_ids
        assert len(response_ids) == 1

    def test_case_insensitive_url_encoded_detection(self, db_create_host, api_get):
        """Test that %2a (lowercase) is also detected as URL-encoded asterisk."""
        # Create a host with a literal asterisk
        host_with_literal_asterisk = db_create_host(extra_data={"system_profile_facts": {"os_release": "test*value"}})

        # Create a host that would match wildcard
        host_wildcard_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "testXvalue"}})

        # Test with lowercase URL-encoded asterisk
        url = build_hosts_url(query="?filter[system_profile][os_release]=test%2avalue")
        response_status, response_data = api_get(url)

        assert response_status == 200
        response_ids = [result["id"] for result in response_data["results"]]

        # Should match only the host with literal asterisk
        assert str(host_with_literal_asterisk.id) in response_ids
        assert str(host_wildcard_match.id) not in response_ids
        assert len(response_ids) == 1
