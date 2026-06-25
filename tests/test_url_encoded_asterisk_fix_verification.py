#!/usr/bin/env python
"""
Tests to verify the URL-encoded asterisk fix (RHINENG-4809) is working correctly.

Based on testing, the fix works correctly for system profile filtering,
where URL-encoded asterisks are treated as literal characters.
"""

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_asterisk_system_profile_literal_match(db_create_host, api_get):
    """
    Test that URL-encoded asterisks in system profile filters match only literal asterisks.

    This verifies the fix for RHINENG-4809 is working correctly for system profile filtering.
    """
    # Create hosts with different arch values
    sp_data_literal = {
        "system_profile_facts": {
            "arch": "x86*64",  # Has literal asterisk
            "host_type": "edge",
        }
    }
    sp_data_no_asterisk = {
        "system_profile_facts": {
            "arch": "x86_64",  # No asterisk
            "host_type": "edge",
        }
    }
    sp_data_different = {
        "system_profile_facts": {
            "arch": "x86X64",  # Different pattern
            "host_type": "edge",
        }
    }

    host_literal = db_create_host(extra_data=sp_data_literal)
    db_create_host(extra_data=sp_data_no_asterisk)
    db_create_host(extra_data=sp_data_different)

    # URL-encoded asterisk should match only the host with literal asterisk
    url = build_hosts_url(query="?filter[system_profile][arch]=x86%2A64")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host_literal.id)


def test_url_encoded_asterisk_system_profile_case_insensitive(db_create_host, api_get):
    """
    Test that both %2A and %2a work correctly for system profile filtering.
    """
    sp_data = {"system_profile_facts": {"arch": "test*arch", "host_type": "edge"}}
    host = db_create_host(extra_data=sp_data)

    # Test both uppercase and lowercase URL encoding
    for encoded_asterisk in ["%2A", "%2a"]:
        url = build_hosts_url(query=f"?filter[system_profile][arch]=test{encoded_asterisk}arch")
        response_status, response_data = api_get(url)

        assert response_status == 200
        assert response_data["count"] == 1
        assert response_data["results"][0]["id"] == str(host.id)


def test_url_encoded_asterisk_system_profile_multiple_asterisks(db_create_host, api_get):
    """
    Test URL-encoded asterisks work correctly with multiple asterisks in system profile.
    """
    sp_data = {"system_profile_facts": {"arch": "test*value*end", "host_type": "edge"}}
    host = db_create_host(extra_data=sp_data)

    # Multiple URL-encoded asterisks should match literal asterisks
    url = build_hosts_url(query="?filter[system_profile][arch]=test%2Avalue%2Aend")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host.id)


def test_url_encoded_asterisk_system_profile_no_match_when_no_literal(db_create_host, api_get):
    """
    Test that URL-encoded asterisks don't match when no literal asterisk is present.
    """
    sp_data = {
        "system_profile_facts": {
            "arch": "x86_64",  # No asterisk
            "host_type": "edge",
        }
    }
    db_create_host(extra_data=sp_data)

    # URL-encoded asterisk should not match when no literal asterisk
    url = build_hosts_url(query="?filter[system_profile][arch]=x86%2A64")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 0


def test_url_encoded_asterisk_system_profile_different_fields(db_create_host, api_get):
    """
    Test URL-encoded asterisks work correctly in different system profile fields.
    """
    sp_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.*",  # Literal asterisk
            "host_type": "edge",
        }
    }
    host = db_create_host(extra_data=sp_data)

    # URL-encoded asterisk in insights_client_version field
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host.id)


def test_unencoded_asterisk_system_profile_still_works_as_literal(db_create_host, api_get):
    """
    Test that unencoded asterisks in system profile filters also work as literal matches.

    This documents that system profile filtering treats asterisks as literals, not wildcards.
    """
    sp_data_literal = {
        "system_profile_facts": {
            "arch": "x86*64",  # Has literal asterisk
            "host_type": "edge",
        }
    }
    sp_data_no_asterisk = {
        "system_profile_facts": {
            "arch": "x86_64",  # No asterisk
            "host_type": "edge",
        }
    }

    host_literal = db_create_host(extra_data=sp_data_literal)
    db_create_host(extra_data=sp_data_no_asterisk)

    # Unencoded asterisk should also match only literal asterisk
    url = build_hosts_url(query="?filter[system_profile][arch]=x86*64")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host_literal.id)


def test_url_encoded_asterisk_mixed_with_other_special_chars(db_create_host, api_get):
    """
    Test URL-encoded asterisks work correctly when mixed with other special characters.
    """
    sp_data = {
        "system_profile_facts": {
            "arch": "test*arch@#$",  # Asterisk with other special chars
            "host_type": "edge",
        }
    }
    host = db_create_host(extra_data=sp_data)

    # URL-encoded asterisk with other characters (some may also need encoding)
    url = build_hosts_url(query="?filter[system_profile][arch]=test%2Aarch@%23$")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host.id)


def test_url_encoded_asterisk_edge_cases(db_create_host, api_get):
    """
    Test edge cases for URL-encoded asterisks in system profile filtering.
    """
    # Test with asterisk at start
    sp_data_start = {"system_profile_facts": {"arch": "*start", "host_type": "edge"}}
    host_start = db_create_host(extra_data=sp_data_start)

    url = build_hosts_url(query="?filter[system_profile][arch]=%2Astart")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host_start.id)

    # Test with asterisk at end
    sp_data_end = {"system_profile_facts": {"arch": "end*", "host_type": "edge"}}
    host_end = db_create_host(extra_data=sp_data_end)

    url = build_hosts_url(query="?filter[system_profile][arch]=end%2A")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host_end.id)

    # Test with only asterisk
    sp_data_only = {"system_profile_facts": {"arch": "*", "host_type": "edge"}}
    host_only = db_create_host(extra_data=sp_data_only)

    url = build_hosts_url(query="?filter[system_profile][arch]=%2A")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(host_only.id)
