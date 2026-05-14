from urllib.parse import quote

from tests.helpers.api_utils import build_hosts_url


class TestUrlEncodedWildcardFix:
    """Test that URL-encoded asterisks are treated as literal characters, not wildcards."""

    def test_url_encoded_asterisk_not_treated_as_wildcard(self, db_create_host, api_get):
        """Test that %2A in filter values is treated as literal '*', not as a wildcard."""
        # Create hosts with different os_release values
        host_with_literal_asterisk = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "test*123",  # Contains literal asterisk
                    "arch": "x86_64"
                }
            }
        )

        host_with_different_value = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "test456123",  # Would match "test*123" as wildcard
                    "arch": "x86_64"
                }
            }
        )

        host_with_another_value = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "testABC123",  # Would also match "test*123" as wildcard
                    "arch": "x86_64"
                }
            }
        )

        # Test 1: Using literal asterisk should work as wildcard and match multiple hosts
        url = build_hosts_url(query="?filter[system_profile][os_release]=test*123")
        response_status, response_data = api_get(url)
        assert response_status == 200
        # Should match all three hosts when * is treated as wildcard
        assert response_data["total"] == 3
        returned_ids = {host["id"] for host in response_data["results"]}
        expected_ids = {host_with_literal_asterisk.id, host_with_different_value.id, host_with_another_value.id}
        assert returned_ids == expected_ids

        # Test 2: Using URL-encoded asterisk should match only the host with literal asterisk
        url_encoded_asterisk = quote("test*123")  # This will encode * as %2A
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_asterisk}")
        response_status, response_data = api_get(url)
        assert response_status == 200
        # Should match only the host with literal asterisk
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_literal_asterisk.id

    def test_url_encoded_asterisk_with_insights_client_version(self, db_create_host, api_get):
        """Test URL-encoded asterisk behavior with insights_client_version field."""
        # Create hosts with different insights_client_version values
        host_with_asterisk = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "insights_client_version": "3.0*el4_2",  # Contains literal asterisk
                    "arch": "x86_64"
                }
            }
        )

        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "insights_client_version": "3.0.1-2.el4_2",  # Would match wildcard pattern
                    "arch": "x86_64"
                }
            }
        )

        # Test with literal asterisk (should work as wildcard)
        url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0*el4_2")
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert response_data["total"] == 2  # Both hosts should match

        # Test with URL-encoded asterisk (should match only literal asterisk)
        url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0%2Ael4_2")
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_asterisk.id

    def test_backslash_escaping_with_url_encoding(self, db_create_host, api_get):
        """Test that backslash escaping works correctly with URL-encoded values."""
        # Create a host with a value containing both asterisk and backslash
        host_with_complex_value = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "test1*test2\\test3",  # Contains both * and \
                    "arch": "x86_64"
                }
            }
        )

        # URL encode the entire value: test1*test2\test3 -> test1%2Atest2%5Ctest3
        url_encoded_value = quote("test1*test2\\test3")
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={url_encoded_value}")
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_complex_value.id

    def test_mixed_encoded_and_literal_asterisks(self, db_create_host, api_get):
        """Test behavior when a value contains both URL-encoded and literal asterisks."""
        # Create hosts with different patterns
        host_with_mixed = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "prefix*middle*suffix",  # Two literal asterisks
                    "arch": "x86_64"
                }
            }
        )

        db_create_host(
            extra_data={
                "system_profile_facts": {
                    "os_release": "prefixXmiddle*suffix",  # Would match first wildcard
                    "arch": "x86_64"
                }
            }
        )

        # Test with one asterisk URL-encoded: prefix%2Amiddle*suffix
        # This should be treated as literal * for first part, wildcard for second
        mixed_encoded = "prefix%2Amiddle*suffix"
        url = build_hosts_url(query=f"?filter[system_profile][os_release]={mixed_encoded}")
        response_status, response_data = api_get(url)
        assert response_status == 200
        # Should match only the host with exact literal asterisk in first position
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_mixed.id

    def test_non_wildcard_field_with_url_encoded_asterisk(self, db_create_host, api_get):
        """Test that URL-encoded asterisks work correctly in non-wildcard fields."""
        # arch field doesn't support wildcards, so * should always be literal
        host_with_asterisk_arch = db_create_host(
            extra_data={
                "system_profile_facts": {
                    "arch": "test*arch",  # Literal asterisk in non-wildcard field
                    "os_release": "7.4"
                }
            }
        )

        # Test with URL-encoded asterisk in non-wildcard field
        url = build_hosts_url(query="?filter[system_profile][arch]=test%2Aarch")
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_asterisk_arch.id

        # Test with literal asterisk in non-wildcard field (should also work)
        url = build_hosts_url(query="?filter[system_profile][arch]=test*arch")
        response_status, response_data = api_get(url)
        assert response_status == 200
        assert response_data["total"] == 1
        assert response_data["results"][0]["id"] == host_with_asterisk_arch.id
