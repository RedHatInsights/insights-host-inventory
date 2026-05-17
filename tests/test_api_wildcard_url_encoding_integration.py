"""
Integration tests for wildcard URL encoding fix (RHINENG-4809).

These tests verify that the API correctly handles URL-encoded asterisks
in system profile filtering by making actual HTTP requests.
"""

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


class TestWildcardUrlEncodingIntegration:
    """Integration tests for wildcard URL encoding behavior."""

    def test_url_encoded_asterisk_literal_match(self, mq_create_or_update_host, api_get):
        """Test that URL-encoded asterisks (%2A) are treated as literal asterisks."""
        # Create a host with a literal asterisk in os_release
        host_data = minimal_host(system_profile={"os_release": "test1*test2"})  # Literal asterisk
        created_host = mq_create_or_update_host(host_data)

        # Test 1: URL-encoded asterisk should match the literal asterisk
        encoded_filter = "filter[system_profile][os_release]=test1%2Atest2"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

        # Test 2: Normal asterisk also matches because it's treated as a wildcard
        # The wildcard pattern "test1*test2" matches the literal value "test1*test2"
        normal_filter = "filter[system_profile][os_release]=test1*test2"
        url = build_hosts_url(query=f"?{normal_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1  # Wildcard pattern matches literal value

    def test_url_encoded_asterisk_no_wildcard_behavior(self, mq_create_or_update_host, api_get):
        """Test that URL-encoded asterisks don't exhibit wildcard behavior."""
        # Create hosts with different os_release values
        host1_data = minimal_host(system_profile={"os_release": "test1*test2"})  # Literal asterisk
        host2_data = minimal_host(
            system_profile={"os_release": "test1XYZtest2"}  # Different value that would match wildcard
        )
        host3_data = minimal_host(
            system_profile={"os_release": "test1ABCtest2"}  # Another value that would match wildcard
        )

        created_host1 = mq_create_or_update_host(host1_data)
        created_host2 = mq_create_or_update_host(host2_data)
        created_host3 = mq_create_or_update_host(host3_data)

        # URL-encoded asterisk should only match the exact literal value
        encoded_filter = "filter[system_profile][os_release]=test1%2Atest2"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host1.id

        # Normal asterisk should match all three (wildcard behavior)
        normal_filter = "filter[system_profile][os_release]=test1*test2"
        url = build_hosts_url(query=f"?{normal_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 3  # All three hosts match the wildcard pattern
        returned_ids = {result["id"] for result in response_data["results"]}
        expected_ids = {created_host1.id, created_host2.id, created_host3.id}
        assert returned_ids == expected_ids

    def test_backslash_handling_with_url_encoding(self, mq_create_or_update_host, api_get):
        """Test that backslashes work correctly with URL-encoded asterisks."""
        # Create a host with both asterisk and backslash
        host_data = minimal_host(
            system_profile={"os_release": "test1*test2\\test3"}  # Literal asterisk and backslash
        )
        created_host = mq_create_or_update_host(host_data)

        # URL-encode both the asterisk and backslash
        # %2A = *, %5C = \
        encoded_filter = "filter[system_profile][os_release]=test1%2Atest2%5Ctest3"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    def test_mixed_encoded_and_unencoded_asterisks(self, mq_create_or_update_host, api_get):
        """Test behavior when some asterisks are encoded and some are not."""
        # Create a host with multiple asterisks
        host_data = minimal_host(
            system_profile={"os_release": "test1*test2*test3"}  # Two literal asterisks
        )
        created_host = mq_create_or_update_host(host_data)

        # Mix encoded and unencoded asterisks - this should trigger exact matching
        # because at least one asterisk is encoded
        mixed_filter = "filter[system_profile][os_release]=test1%2Atest2*test3"
        url = build_hosts_url(query=f"?{mixed_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    def test_url_encoded_asterisk_different_wildcard_fields(self, mq_create_or_update_host, api_get):
        """Test URL-encoded asterisks work with different wildcard-enabled fields."""
        # Test with insights_client_version (another wildcard field)
        host_data = minimal_host(
            system_profile={"insights_client_version": "3.0*1-2.el4_2"}  # Literal asterisk
        )
        created_host = mq_create_or_update_host(host_data)

        # URL-encoded asterisk should match exactly
        encoded_filter = "filter[system_profile][insights_client_version]=3.0%2A1-2.el4_2"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id

    def test_url_encoded_asterisk_no_match(self, mq_create_or_update_host, api_get):
        """Test that URL-encoded asterisks don't match when value is different."""
        # Create a host with a specific os_release
        host_data = minimal_host(system_profile={"os_release": "test1XYZtest2"})  # No asterisk
        mq_create_or_update_host(host_data)

        # URL-encoded asterisk looking for literal asterisk should not match
        encoded_filter = "filter[system_profile][os_release]=test1%2Atest2"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 0

    def test_normal_wildcard_behavior_still_works(self, mq_create_or_update_host, api_get):
        """Test that normal wildcard behavior is preserved for non-encoded asterisks."""
        # Create hosts with different os_release values
        host1_data = minimal_host(system_profile={"os_release": "abc.123"})
        host2_data = minimal_host(system_profile={"os_release": "abc*123"})  # Literal asterisk
        host3_data = minimal_host(system_profile={"os_release": "abcdefghijkl123"})

        created_host1 = mq_create_or_update_host(host1_data)
        created_host2 = mq_create_or_update_host(host2_data)
        created_host3 = mq_create_or_update_host(host3_data)

        # Normal asterisk should match all three (wildcard behavior)
        wildcard_filter = "filter[system_profile][os_release]=abc*123"
        url = build_hosts_url(query=f"?{wildcard_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 3
        returned_ids = {result["id"] for result in response_data["results"]}
        expected_ids = {created_host1.id, created_host2.id, created_host3.id}
        assert returned_ids == expected_ids

    def test_url_encoded_brackets_with_asterisk(self, mq_create_or_update_host, api_get):
        """Test that URL-encoded brackets are handled correctly."""
        # Create a host with literal asterisk
        host_data = minimal_host(system_profile={"os_release": "test*value"})
        created_host = mq_create_or_update_host(host_data)

        # Use URL-encoded brackets and asterisk
        # %5B = [, %5D = ], %2A = *
        encoded_filter = "filter%5Bsystem_profile%5D%5Bos_release%5D=test%2Avalue"
        url = build_hosts_url(query=f"?{encoded_filter}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == created_host.id
