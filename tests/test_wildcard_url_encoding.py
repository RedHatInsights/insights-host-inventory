"""
Tests for URL-encoded asterisk handling in wildcard filtering (RHINENG-4809).

This module tests that URL-encoded "*" (%2A) is treated as literal "*" character,
not as a wildcard, while regular "*" continues to work as wildcard.
"""

import pytest
from tests.helpers.test_utils import minimal_host, USER_IDENTITY
from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_asterisk_literal_vs_wildcard(mq_create_or_update_host, api_get):
    """Test that URL-encoded * (%2A) is treated as literal, while * is treated as wildcard."""
    
    # Create hosts with different os_release values
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "abc*123"}),
        identity=USER_IDENTITY
    )
    host2 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "abc.123"}),
        identity=USER_IDENTITY
    )
    host3 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "abcdefghijkl123"}),
        identity=USER_IDENTITY
    )
    
    # Test 1: Wildcard "*" should match multiple hosts
    url_wildcard = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_wildcard)
    assert response_status == 200
    # Should match all three hosts: "abc*123", "abc.123", "abcdefghijkl123"
    assert len(response_data["results"]) == 3
    
    # Test 2: URL-encoded "*" (%2A) should only match literal "*"
    url_literal = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_literal)
    assert response_status == 200
    # Should only match the host with literal "*": "abc*123"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_backslash_escaping_with_url_encoding(mq_create_or_update_host, api_get):
    """Test that backslash escaping works correctly with URL-encoded values."""
    
    # Create host with backslash and asterisk
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "test1*test2\\test3"}),
        identity=USER_IDENTITY
    )
    
    # Test URL-encoded version: test1%2Atest2%5Ctest3
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)
    assert response_status == 200
    # Should match the host with literal "*" and "\"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_insights_client_version_wildcard_vs_literal(mq_create_or_update_host, api_get):
    """Test wildcard vs literal asterisk handling for insights_client_version field."""
    
    # Create hosts with different insights_client_version values
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"insights_client_version": "3.0*2.el4_2"}),
        identity=USER_IDENTITY
    )
    host2 = mq_create_or_update_host(
        minimal_host(system_profile={"insights_client_version": "3.0.1-2.el4_2"}),
        identity=USER_IDENTITY
    )
    host3 = mq_create_or_update_host(
        minimal_host(system_profile={"insights_client_version": "3.0.2-2.el4_2"}),
        identity=USER_IDENTITY
    )
    
    # Test 1: Wildcard "*" should match multiple hosts
    url_wildcard = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0*2.el4_2")
    response_status, response_data = api_get(url_wildcard)
    assert response_status == 200
    # Should match all three hosts
    assert len(response_data["results"]) == 3
    
    # Test 2: URL-encoded "*" (%2A) should only match literal "*"
    url_literal = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0%2A2.el4_2")
    response_status, response_data = api_get(url_literal)
    assert response_status == 200
    # Should only match the host with literal "*"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_bios_release_date_wildcard_vs_literal(mq_create_or_update_host, api_get):
    """Test wildcard vs literal asterisk handling for bios_release_date field."""
    
    # Create hosts with different bios_release_date values
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"bios_release_date": "2020*01*15"}),
        identity=USER_IDENTITY
    )
    host2 = mq_create_or_update_host(
        minimal_host(system_profile={"bios_release_date": "2020-01-15"}),
        identity=USER_IDENTITY
    )
    host3 = mq_create_or_update_host(
        minimal_host(system_profile={"bios_release_date": "2020/01/15"}),
        identity=USER_IDENTITY
    )
    
    # Test 1: Wildcard "*" should match multiple hosts
    url_wildcard = build_hosts_url(query="?filter[system_profile][bios_release_date]=2020*01*15")
    response_status, response_data = api_get(url_wildcard)
    assert response_status == 200
    # Should match all three hosts
    assert len(response_data["results"]) == 3
    
    # Test 2: URL-encoded "*" (%2A) should only match literal "*"
    url_literal = build_hosts_url(query="?filter[system_profile][bios_release_date]=2020%2A01%2A15")
    response_status, response_data = api_get(url_literal)
    assert response_status == 200
    # Should only match the host with literal "*"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_non_wildcard_field_asterisk_handling(mq_create_or_update_host, api_get):
    """Test that non-wildcard fields handle asterisks correctly (should be literal)."""
    
    # Create hosts with asterisks in non-wildcard fields (e.g., arch)
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"arch": "x86*64"}),
        identity=USER_IDENTITY
    )
    host2 = mq_create_or_update_host(
        minimal_host(system_profile={"arch": "x86_64"}),
        identity=USER_IDENTITY
    )
    
    # Test 1: Regular "*" in non-wildcard field should be treated as literal
    url_asterisk = build_hosts_url(query="?filter[system_profile][arch]=x86*64")
    response_status, response_data = api_get(url_asterisk)
    assert response_status == 200
    # Should only match the host with literal "*"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)
    
    # Test 2: URL-encoded "*" (%2A) should also be treated as literal
    url_encoded = build_hosts_url(query="?filter[system_profile][arch]=x86%2A64")
    response_status, response_data = api_get(url_encoded)
    assert response_status == 200
    # Should only match the host with literal "*"
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)


def test_mixed_wildcard_and_literal_asterisks(mq_create_or_update_host, api_get):
    """Test filtering with both wildcard and literal asterisks in the same query."""
    
    # Create hosts with complex patterns
    host1 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "test*version*1.0"}),
        identity=USER_IDENTITY
    )
    host2 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "test.version.1.0"}),
        identity=USER_IDENTITY
    )
    host3 = mq_create_or_update_host(
        minimal_host(system_profile={"os_release": "test_version_1.0"}),
        identity=USER_IDENTITY
    )
    
    # Test: Mix of wildcard (*) and literal (%2A) asterisks
    # This should match hosts where the first * is wildcard and second is literal
    url_mixed = build_hosts_url(query="?filter[system_profile][os_release]=test*version%2A1.0")
    response_status, response_data = api_get(url_mixed)
    assert response_status == 200
    # Should only match the host with the exact pattern
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)