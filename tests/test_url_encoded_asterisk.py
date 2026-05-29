"""Tests for URL-encoded asterisk handling in wildcard filtering (RHINENG-4809)."""

import pytest

from tests.helpers.api_utils import build_hosts_url


def test_escaped_asterisk_in_filter_value(db_create_host, api_get):
    """Test that escaped asterisks (\\*) are treated as literals."""
    host_data = {
        "system_profile_facts": {
            "insights_client_version": "test*value",  # Contains literal asterisk
            "arch": "x86_64",
        }
    }
    host_id = str(db_create_host(extra_data=host_data).id)

    # Test escaped asterisk - should match literal asterisk
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=test\\*value")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids


def test_wildcard_asterisk_functionality(db_create_host, api_get):
    """Test that unescaped asterisks (*) function as wildcards."""
    # Create hosts with different patterns
    host1_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.1-el8",  # Matches pattern
            "arch": "x86_64",
        }
    }
    host2_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.2-el8",  # Matches pattern
            "arch": "x86_64",
        }
    }
    host3_data = {
        "system_profile_facts": {
            "insights_client_version": "4.0.1-el8",  # Does not match pattern
            "arch": "x86_64",
        }
    }

    host1_id = str(db_create_host(extra_data=host1_data).id)
    host2_id = str(db_create_host(extra_data=host2_data).id)
    host3_id = str(db_create_host(extra_data=host3_data).id)

    # Test wildcard should match hosts 1 and 2 but not 3
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*-el8")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host1_id in response_ids
    assert host2_id in response_ids
    assert host3_id not in response_ids


def test_literal_vs_wildcard_asterisk_with_escaping(db_create_host, api_get):
    """Test the distinction between literal and wildcard asterisks using escaping."""
    # Create two hosts: one with literal asterisk, one without
    host_with_asterisk_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.*-el8",  # Literal asterisk
            "arch": "x86_64",
        }
    }
    host_without_asterisk_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.1-el8",  # No asterisk
            "arch": "x86_64",
        }
    }

    host_with_asterisk_id = str(db_create_host(extra_data=host_with_asterisk_data).id)
    host_without_asterisk_id = str(db_create_host(extra_data=host_without_asterisk_data).id)

    # Test 1: Escaped asterisk should match only the literal asterisk
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.\\*-el8")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_with_asterisk_id in response_ids
    assert host_without_asterisk_id not in response_ids

    # Test 2: Wildcard should match both hosts
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*-el8")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_with_asterisk_id in response_ids  # Matches "3.0.*-el8"
    assert host_without_asterisk_id in response_ids  # Matches "3.0.1-el8"


def test_multiple_escaped_asterisks(db_create_host, api_get):
    """Test multiple escaped asterisks in a single filter value."""
    host_data = {
        "system_profile_facts": {
            "insights_client_version": "*test*value*",  # Multiple literal asterisks
            "arch": "x86_64",
        }
    }
    host_id = str(db_create_host(extra_data=host_data).id)

    # Test multiple escaped asterisks
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\*test\\*value\\*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids


@pytest.mark.parametrize(
    "field_name,field_value,filter_value,should_match",
    [
        ("insights_client_version", "3.0.*", "3.0.\\*", True),
        ("os_release", "RHEL*8", "RHEL\\*8", True),
        ("bios_release_date", "2023-*-15", "2023-\\*-15", True),
    ],
)
def test_escaped_asterisk_across_wildcard_fields(db_create_host, api_get, field_name, field_value, filter_value, should_match):
    """Test escaped asterisk handling across different wildcard-enabled fields."""
    host_data = {
        "system_profile_facts": {
            field_name: field_value,
            "arch": "x86_64",
        }
    }
    host_id = str(db_create_host(extra_data=host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][{field_name}]={filter_value}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    if should_match:
        assert host_id in response_ids
    else:
        assert host_id not in response_ids


def test_edge_case_only_asterisks(db_create_host, api_get):
    """Test edge cases with values that are only asterisks."""
    host_data = {
        "system_profile_facts": {
            "insights_client_version": "***",  # Only literal asterisks
            "arch": "x86_64",
        }
    }
    host_id = str(db_create_host(extra_data=host_data).id)

    # Test escaped asterisks
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\*\\*\\*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids

    # Test wildcard asterisks
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=***")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids


def test_mixed_escaped_and_wildcard_asterisks(db_create_host, api_get):
    """Test mixing escaped and wildcard asterisks in the same filter."""
    # Create hosts with different patterns
    host1_data = {
        "system_profile_facts": {
            "insights_client_version": "*prefix-3.0.1-suffix*",  # Literal asterisks at start/end
            "arch": "x86_64",
        }
    }
    host2_data = {
        "system_profile_facts": {
            "insights_client_version": "xprefix-3.0.2-suffixy",  # No asterisks
            "arch": "x86_64",
        }
    }

    host1_id = str(db_create_host(extra_data=host1_data).id)
    host2_id = str(db_create_host(extra_data=host2_data).id)

    # Test mixed pattern: escaped asterisk at start, wildcard in middle, escaped at end
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\*prefix-3.0.*-suffix\\*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host1_id in response_ids  # Should match the literal asterisks and wildcard pattern
    assert host2_id not in response_ids  # Doesn't have literal asterisks at start/end


@pytest.mark.parametrize(
    "os_release_value,filter_pattern,should_match",
    [
        ("RHEL*8.5", "RHEL\\*8.5", True),  # Exact match with escaped asterisk
        ("RHEL*8.5", "RHEL*8.5", True),    # Wildcard matches literal asterisk
        ("RHEL*8.5", "RHEL*", True),       # Wildcard pattern matches
        ("RHEL8.5", "RHEL\\*8.5", False), # Escaped asterisk doesn't match without literal asterisk
        ("RHEL8.5", "RHEL*8.5", True),    # Wildcard matches
    ],
)
def test_os_release_asterisk_patterns(db_create_host, api_get, os_release_value, filter_pattern, should_match):
    """Test various asterisk patterns in os_release field."""
    host_data = {
        "system_profile_facts": {
            "os_release": os_release_value,
            "arch": "x86_64",
        }
    }
    host_id = str(db_create_host(extra_data=host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][os_release]={filter_pattern}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    if should_match:
        assert host_id in response_ids, f"Expected {filter_pattern} to match {os_release_value}"
    else:
        assert host_id not in response_ids, f"Expected {filter_pattern} to NOT match {os_release_value}"
