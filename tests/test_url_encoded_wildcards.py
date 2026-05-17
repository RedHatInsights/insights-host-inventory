"""
Test for URL-encoded wildcard handling in system profile filtering.

This test verifies the fix for RHINENG-4809: URL-encoded wildcards (%2A)
should be treated as literal asterisks, not as wildcard patterns.
"""

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_wildcard_literal_match(db_create_host, api_get):
    """Test that URL-encoded wildcards are treated as literal characters."""
    # Create a host with os_release containing a literal asterisk
    sp_data = {
        "system_profile_facts": {
            "os_release": "test1*test2",
            "arch": "x86_64",
        }
    }
    host = db_create_host(extra_data=sp_data)

    # Test 1: URL-encoded wildcard should match the literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host.id

    # Test 2: Regular wildcard should also match (wildcard behavior)
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1*test2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host.id


def test_url_encoded_wildcard_no_false_matches(db_create_host, api_get):
    """Test that URL-encoded wildcards don't match unintended values."""
    # Create hosts with different os_release values
    sp_data1 = {
        "system_profile_facts": {
            "os_release": "test1*test2",  # Contains literal asterisk
            "arch": "x86_64",
        }
    }
    sp_data2 = {
        "system_profile_facts": {
            "os_release": "test1.test2",  # Different character instead of asterisk
            "arch": "x86_64",
        }
    }
    sp_data3 = {
        "system_profile_facts": {
            "os_release": "test1abctest2",  # Different characters instead of asterisk
            "arch": "x86_64",
        }
    }

    host1 = db_create_host(extra_data=sp_data1)
    host2 = db_create_host(extra_data=sp_data2)
    host3 = db_create_host(extra_data=sp_data3)

    # URL-encoded wildcard should only match the host with literal asterisk
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host1.id

    # Regular wildcard should match all hosts (wildcard behavior)
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1*test2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 3
    host_ids = {host["id"] for host in response_data["results"]}
    assert host_ids == {host1.id, host2.id, host3.id}


def test_url_encoded_wildcard_with_backslash(db_create_host, api_get):
    """Test URL-encoded wildcards work correctly with backslashes."""
    # Create a host with os_release containing both asterisk and backslash
    sp_data = {
        "system_profile_facts": {
            "os_release": "test1*test2\\test3",
            "arch": "x86_64",
        }
    }
    host = db_create_host(extra_data=sp_data)

    # URL-encoded version should match exactly
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host.id


def test_url_encoded_wildcard_different_fields(db_create_host, api_get):
    """Test URL-encoded wildcards work on different wildcard-enabled fields."""
    # Test with bios_version (another field with x-wildcard: true)
    sp_data = {
        "system_profile_facts": {
            "bios_version": "version*1.0",
            "arch": "x86_64",
        }
    }
    host = db_create_host(extra_data=sp_data)

    # URL-encoded wildcard should match literally
    url = build_hosts_url(query="?filter[system_profile][bios_version]=version%2A1.0")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == host.id


def test_normal_wildcard_behavior_preserved(db_create_host, api_get):
    """Test that normal wildcard behavior is preserved for non-encoded wildcards."""
    # Create hosts with different os_release values
    sp_data1 = {
        "system_profile_facts": {
            "os_release": "abc.123",
            "arch": "x86_64",
        }
    }
    sp_data2 = {
        "system_profile_facts": {
            "os_release": "abc*123",  # Contains literal asterisk
            "arch": "x86_64",
        }
    }
    sp_data3 = {
        "system_profile_facts": {
            "os_release": "abcdefghijkl123",
            "arch": "x86_64",
        }
    }

    host1 = db_create_host(extra_data=sp_data1)
    host2 = db_create_host(extra_data=sp_data2)
    host3 = db_create_host(extra_data=sp_data3)

    # Regular wildcard should match all three hosts
    url = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 3
    host_ids = {host["id"] for host in response_data["results"]}
    assert host_ids == {host1.id, host2.id, host3.id}
