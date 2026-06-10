"""
Test cases for URL-encoded asterisk handling in wildcard filters.
This addresses RHINENG-4809: URL-encoded asterisks (%2A) should be treated as literal characters,
while unencoded asterisks (*) should continue to work as wildcards.
"""

import pytest

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_asterisk_in_wildcard_filter(db_create_host, api_get):
    """Test that URL-encoded asterisks (%2A) are treated as literal characters in wildcard fields."""
    # Create hosts with different insights_client_version values
    host_with_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test*value"  # Contains literal asterisk
            }
        }
    )

    host_with_normal_value = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test123value"  # No asterisk
            }
        }
    )

    # Test 1: URL-encoded asterisk (%2A) should match literal asterisk
    url_encoded_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test%2Avalue")
    response_status, response_data = api_get(url_encoded_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_with_literal_asterisk.id)

    # Test 2: Unencoded asterisk (*) should work as wildcard and match both
    wildcard_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test*value")
    response_status, response_data = api_get(wildcard_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 2  # Should match both hosts
    host_ids = {result["id"] for result in response_data["results"]}
    assert str(host_with_literal_asterisk.id) in host_ids
    assert str(host_with_normal_value.id) in host_ids


def test_mixed_literal_and_wildcard_asterisks(db_create_host, api_get):
    """Test handling of mixed literal and wildcard asterisks in the same filter."""
    # Create hosts with various patterns
    host1 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "prefix*middle*suffix"  # Two literal asterisks
            }
        }
    )

    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "prefix123middle456suffix"  # Pattern that would match wildcard
            }
        }
    )

    # URL-encoded asterisks should match literal asterisks only
    url_encoded_filter = build_hosts_url(
        query="?filter[system_profile][insights_client_version]=prefix%2Amiddle%2Asuffix"
    )
    response_status, response_data = api_get(url_encoded_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)

    # Wildcard pattern should match both
    wildcard_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=prefix*middle*suffix")
    response_status, response_data = api_get(wildcard_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 2


def test_url_encoded_asterisk_edge_cases(db_create_host, api_get):
    """Test edge cases for URL-encoded asterisk handling."""
    # Create hosts with edge case values
    host_start_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "*start"  # Asterisk at start
            }
        }
    )

    host_end_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "end*"  # Asterisk at end
            }
        }
    )

    host_multiple_asterisks = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "a*b*c*d"  # Multiple asterisks
            }
        }
    )

    # Test URL-encoded asterisk at start
    url_encoded_start = build_hosts_url(query="?filter[system_profile][insights_client_version]=%2Astart")
    response_status, response_data = api_get(url_encoded_start)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_start_asterisk.id)

    # Test URL-encoded asterisk at end
    url_encoded_end = build_hosts_url(query="?filter[system_profile][insights_client_version]=end%2A")
    response_status, response_data = api_get(url_encoded_end)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_end_asterisk.id)

    # Test multiple URL-encoded asterisks
    url_encoded_multiple = build_hosts_url(query="?filter[system_profile][insights_client_version]=a%2Ab%2Ac%2Ad")
    response_status, response_data = api_get(url_encoded_multiple)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_multiple_asterisks.id)


def test_url_encoded_asterisk_different_fields(db_create_host, api_get):
    """Test URL-encoded asterisk handling across different wildcard-enabled fields."""
    # Test with arch field
    host_arch_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "arch": "x86*64"  # Contains literal asterisk
            }
        }
    )

    # Test with bootc_status.booted.image field (nested field)
    host_bootc_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "bootc_status": {
                    "booted": {
                        "image": "quay.io/test*image:latest"  # Contains literal asterisk
                    }
                }
            }
        }
    )

    # Test arch field with URL-encoded asterisk
    arch_filter = build_hosts_url(query="?filter[system_profile][arch]=x86%2A64")
    response_status, response_data = api_get(arch_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_arch_asterisk.id)

    # Test bootc_status field with URL-encoded asterisk
    bootc_filter = build_hosts_url(
        query="?filter[system_profile][bootc_status][booted][image]=quay.io/test%2Aimage:latest"
    )
    response_status, response_data = api_get(bootc_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_bootc_asterisk.id)


def test_backward_compatibility_wildcard_functionality(db_create_host, api_get):
    """Test that existing wildcard functionality still works correctly."""
    # Create hosts with various patterns to test wildcard matching
    host1 = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "3.0.1-2.el8_2"}})

    host2 = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "3.0.5-1.el8_4"}})

    host3 = db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "2.9.1-1.el7_9"}})

    # Test prefix wildcard
    prefix_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*")
    response_status, response_data = api_get(prefix_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    host_ids = {result["id"] for result in response_data["results"]}
    assert str(host1.id) in host_ids
    assert str(host2.id) in host_ids
    assert str(host3.id) not in host_ids

    # Test suffix wildcard
    suffix_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=*el8_2")
    response_status, response_data = api_get(suffix_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host1.id)

    # Test middle wildcard
    middle_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*el8_4")
    response_status, response_data = api_get(middle_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host2.id)


def test_case_sensitivity_with_url_encoded_asterisks(db_create_host, api_get):
    """Test case sensitivity behavior with URL-encoded asterisks."""
    # Create hosts with different case patterns
    host_upper = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "TEST*VALUE"  # Uppercase with asterisk
            }
        }
    )

    host_lower = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test*value"  # Lowercase with asterisk
            }
        }
    )

    # Test URL-encoded asterisk with lowercase pattern (should match both due to ILIKE case insensitivity)
    url_encoded_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test%2Avalue")
    response_status, response_data = api_get(url_encoded_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 2  # ILIKE is case insensitive, so both should match
    host_ids = {result["id"] for result in response_data["results"]}
    assert str(host_lower.id) in host_ids
    assert str(host_upper.id) in host_ids


def test_url_encoded_asterisk_with_other_special_characters(db_create_host, api_get):
    """Test URL-encoded asterisk handling when combined with other special characters."""
    # Create hosts with complex patterns including other special characters
    host_complex = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test*value@domain.com"  # Asterisk with other special chars
            }
        }
    )

    host_percent = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test%*value"  # Percent sign with asterisk
            }
        }
    )

    # Test URL-encoded asterisk with other special characters
    complex_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test%2Avalue@domain.com")
    response_status, response_data = api_get(complex_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_complex.id)

    # Test URL-encoded asterisk with percent sign
    percent_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test%25%2Avalue")
    response_status, response_data = api_get(percent_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_percent.id)


def test_multiple_filters_with_url_encoded_asterisks(db_create_host, api_get):
    """Test multiple filters where some use URL-encoded asterisks and others use regular wildcards."""
    # Create hosts with different combinations
    host_match = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test*version",  # Literal asterisk
                "arch": "x86_64",  # Regular value
            }
        }
    )

    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test123version",  # No asterisk
                "arch": "arm64",  # Different arch
            }
        }
    )

    # Use URL-encoded asterisk for one filter and exact match for another
    multi_filter = build_hosts_url(
        query="?filter[system_profile][insights_client_version]=test%2Aversion&filter[system_profile][arch]=x86_64"
    )
    response_status, response_data = api_get(multi_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_match.id)


@pytest.mark.parametrize("encoded_asterisk", ["%2A", "%2a"])  # Test both upper and lowercase encoding
def test_url_encoded_asterisk_case_variations(db_create_host, api_get, encoded_asterisk):
    """Test that both %2A and %2a are handled correctly."""
    host_with_asterisk = db_create_host(
        extra_data={"system_profile_facts": {"insights_client_version": "version*1.0"}}
    )

    # Test both uppercase and lowercase URL encoding
    filter_url = build_hosts_url(
        query=f"?filter[system_profile][insights_client_version]=version{encoded_asterisk}1.0"
    )
    response_status, response_data = api_get(filter_url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_with_asterisk.id)


def test_url_encoded_asterisk_no_false_positives(db_create_host, api_get):
    """Test that URL-encoded asterisks don't match hosts without literal asterisks."""
    # Create hosts without asterisks
    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "testvalue"  # No asterisk
            }
        }
    )

    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "test123value"  # Different pattern
            }
        }
    )

    # URL-encoded asterisk should not match hosts without literal asterisks
    url_encoded_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=test%2Avalue")
    response_status, response_data = api_get(url_encoded_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 0  # Should not match any hosts


def test_url_encoded_asterisk_vs_wildcard_behavior_comparison(db_create_host, api_get):
    """Test direct comparison between URL-encoded asterisk and wildcard behavior."""
    # Create test hosts
    host_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "app*server"  # Contains literal asterisk
            }
        }
    )

    host_wildcard_match = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "app123server"  # Would match wildcard pattern
            }
        }
    )

    host_different = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "web456client"  # Different pattern entirely
            }
        }
    )

    # Test URL-encoded asterisk (should only match literal asterisk)
    url_encoded_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=app%2Aserver")
    response_status, response_data = api_get(url_encoded_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(host_literal_asterisk.id)

    # Test wildcard pattern (should match both literal asterisk and wildcard pattern)
    wildcard_filter = build_hosts_url(query="?filter[system_profile][insights_client_version]=app*server")
    response_status, response_data = api_get(wildcard_filter)

    assert response_status == 200
    assert len(response_data["results"]) == 2
    host_ids = {result["id"] for result in response_data["results"]}
    assert str(host_literal_asterisk.id) in host_ids
    assert str(host_wildcard_match.id) in host_ids
    assert str(host_different.id) not in host_ids
