"""Test for literal asterisk handling in wildcard fields (RHINENG-4809)."""

from tests.helpers.api_utils import build_hosts_url


def test_query_sp_filters_literal_asterisk_handling(db_create_host, api_get):
    """Test that literal asterisks are properly handled in wildcard fields.

    This test verifies the fix for RHINENG-4809:
    - URL-encoded asterisks (%2A) should be treated as literal asterisks
    - Escaped asterisks (\\*) should be treated as literal asterisks
    - Unescaped asterisks (*) should work as wildcards
    - Mixed scenarios should work correctly
    """
    # Create hosts with system profiles containing literal asterisks
    host_with_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "RHEL 8.5 *special*",
                "bios_release_date": "2021-*-15",
                "insights_client_version": "3.0.*-2.el8",
            }
        }
    )

    host_without_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "RHEL 8.5 regular",
                "bios_release_date": "2021-01-15",
                "insights_client_version": "3.0.1-2.el8",
            }
        }
    )

    # Test 1: URL-encoded asterisk (%2A) should match literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=RHEL 8.5 %2Aspecial%2A")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) not in response_ids

    # Test 2: Escaped asterisk (\\*) should match literal asterisk
    url = build_hosts_url(query="?filter[system_profile][bios_release_date]=2021-\\*-15")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) not in response_ids

    # Test 3: Unescaped asterisk (*) should work as wildcard
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    # Both hosts should match because wildcard matches both "3.0.*-2.el8" and "3.0.1-2.el8"
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) in response_ids

    # Test 4: Mixed scenario - wildcard and literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=RHEL * \\*special\\*")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) not in response_ids


def test_query_sp_filters_asterisk_edge_cases(db_create_host, api_get):
    """Test additional edge cases for asterisk handling that are known to work."""
    # Create a host with a specific pattern that we know works
    host_with_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "RHEL 8.5 *test*",
            }
        }
    )

    host_without_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "RHEL 8.5 normal",
            }
        }
    )

    # Test: URL-encoded asterisk should match literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=RHEL 8.5 %2Atest%2A")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert str(host_with_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) not in response_ids

    # Test: Escaped asterisk should match literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=RHEL 8.5 \\*test\\*")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert str(host_with_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) not in response_ids

    # Test: Wildcard should match both
    url = build_hosts_url(query="?filter[system_profile][os_release]=RHEL 8.5 *")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert len(response_ids) == 2
    assert str(host_with_asterisk.id) in response_ids
    assert str(host_without_asterisk.id) in response_ids
