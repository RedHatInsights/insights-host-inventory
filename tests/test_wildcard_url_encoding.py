"""
Test for URL-encoded wildcard handling in system profile filters.

This test verifies the fix for RHINENG-4809, which ensures that URL-encoded
asterisks (%2A) are treated as literal characters rather than wildcards.
"""

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_wildcard_vs_literal_wildcard(db_create_host, api_get):
    """
    Test that URL-encoded asterisks (%2A) are treated as literals while
    unencoded asterisks (*) are treated as wildcards.
    """
    # Create hosts with different os_release values
    host1_data = {
        "system_profile_facts": {
            "os_release": "abc*123",  # Contains literal asterisk
            "arch": "x86_64",
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    host2_data = {
        "system_profile_facts": {
            "os_release": "abc.123",  # No asterisk
            "arch": "x86_64",
        }
    }
    host2 = db_create_host(extra_data=host2_data)

    host3_data = {
        "system_profile_facts": {
            "os_release": "abcdefghijkl123",  # Matches wildcard pattern
            "arch": "x86_64",
        }
    }
    host3 = db_create_host(extra_data=host3_data)

    # Test 1: URL-encoded asterisk (%2A) should match only the literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)

    # Test 2: Unencoded asterisk (*) should match multiple hosts (wildcard behavior)
    url_wildcard = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    assert len(response_data["results"]) == 3  # Should match all three hosts
    result_ids = {result["id"] for result in response_data["results"]}
    expected_ids = {str(host1.id), str(host2.id), str(host3.id)}
    assert result_ids == expected_ids


def test_url_encoded_wildcard_with_backslash(db_create_host, api_get):
    """
    Test the specific case mentioned in the ticket where backslashes
    cause issues with URL-encoded wildcards.
    """
    # Create a host with the exact value from the ticket
    host_data = {
        "system_profile_facts": {
            "os_release": "test1*test2\\test3",  # Contains both asterisk and backslash
            "arch": "x86_64",
        }
    }
    host = db_create_host(extra_data=host_data)

    # Test URL-encoded version should match the literal value
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host.id)


def test_mixed_encoding_scenarios(db_create_host, api_get):
    """
    Test various encoding scenarios to ensure robust handling.
    """
    # Create hosts with different patterns
    host1_data = {
        "system_profile_facts": {
            "os_release": "version*1.0",
            "arch": "x86_64",
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    # Test case-insensitive URL encoding (%2a vs %2A)
    url_lowercase = build_hosts_url(query="?filter[system_profile][os_release]=version%2a1.0")
    response_status, response_data = api_get(url_lowercase)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)

    # Test uppercase URL encoding
    url_uppercase = build_hosts_url(query="?filter[system_profile][os_release]=version%2A1.0")
    response_status, response_data = api_get(url_uppercase)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_non_wildcard_field_not_affected(db_create_host, api_get):
    """
    Test that non-wildcard fields are not affected by this change.
    The arch field does not have x-wildcard: true, so asterisks should
    always be treated as literals regardless of encoding.
    """
    # Create a host with asterisk in arch field
    host_data = {
        "system_profile_facts": {
            "arch": "x86*64",
            "os_release": "7.4",
        }
    }
    host = db_create_host(extra_data=host_data)

    # Both encoded and unencoded should work the same (exact match)
    url_encoded = build_hosts_url(query="?filter[system_profile][arch]=x86%2A64")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host.id)

    url_unencoded = build_hosts_url(query="?filter[system_profile][arch]=x86*64")
    response_status, response_data = api_get(url_unencoded)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host.id)


def test_insights_client_version_wildcard_behavior(db_create_host, api_get):
    """
    Test wildcard behavior with insights_client_version field which has x-wildcard: true.
    """
    # Create hosts with different insights_client_version values
    host1_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.1*2.el4_2",  # Contains literal asterisk
            "arch": "x86_64",
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    host2_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.1-2.el4_2",  # No asterisk
            "arch": "x86_64",
        }
    }
    host2 = db_create_host(extra_data=host2_data)

    host3_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.1.something.2.el4_2",  # Matches wildcard
            "arch": "x86_64",
        }
    }
    host3 = db_create_host(extra_data=host3_data)

    # Test URL-encoded asterisk should match only literal
    url_encoded = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.1%2A2.el4_2")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)

    # Test unencoded asterisk should match multiple (wildcard)
    url_wildcard = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.1*2.el4_2")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    assert len(response_data["results"]) == 3
    result_ids = {result["id"] for result in response_data["results"]}
    expected_ids = {str(host1.id), str(host2.id), str(host3.id)}
    assert result_ids == expected_ids
