"""
Tests for URL-encoded wildcard character handling in wildcard-enabled fields.

This test file covers the fix for RHINENG-4809, which addresses the issue where
URL-encoded asterisks (%2A) should match literal asterisks (*) in wildcard fields,
while regular asterisks (*) should continue to work as wildcards.

Note: Some tests are marked as expected failures (xfail) because the fix is
currently incomplete due to URL decoding happening in the connexion framework
before the custom filter logic can distinguish between originally URL-encoded
and regular asterisks.
"""

import pytest

from tests.helpers.api_utils import build_hosts_url


def test_regular_wildcard_functionality_baseline(db_create_host, api_get):
    """Baseline test: Verify regular wildcard functionality works correctly."""
    # Create hosts that should match wildcard patterns
    host_match_1 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2",
                "os_release": "8.5.1",
                "bios_release_date": "2023-01-15",
            }
        }
    )

    host_match_2 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.5-2.el4_2",
                "os_release": "8.5.2",
                "bios_release_date": "2023-12-15",
            }
        }
    )

    # Create host that should not match wildcard patterns
    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "4.0.1-2.el4_2",  # Different major version
                "os_release": "9.1.1",  # Different major version
                "bios_release_date": "2022-01-15",  # Different year
            }
        }
    )

    # Test regular wildcard patterns work correctly
    test_cases = [
        ("[insights_client_version]=3.0.*", [host_match_1.id, host_match_2.id]),
        ("[os_release]=8.5.*", [host_match_1.id, host_match_2.id]),
        ("[bios_release_date]=2023-*-15", [host_match_1.id, host_match_2.id]),
    ]

    for filter_param, expected_host_ids in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile]{filter_param}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        actual_host_ids = {host["id"] for host in response_data["results"]}
        expected_host_ids_set = {str(host_id) for host_id in expected_host_ids}

        assert actual_host_ids == expected_host_ids_set, (
            f"Wildcard filter {filter_param} should work normally. "
            f"Expected: {expected_host_ids_set}, Got: {actual_host_ids}"
        )


@pytest.mark.xfail(
    reason="URL-encoded asterisk fix is incomplete - connexion framework decodes URLs before custom filter logic"
)
def test_url_encoded_asterisk_should_match_literal_asterisk(db_create_host, api_get):
    """Test that URL-encoded asterisk (%2A) should match literal asterisk in wildcard fields.

    This test documents the expected behavior once the fix is complete.
    Currently fails because URL decoding happens before the filter logic can
    distinguish between originally URL-encoded and regular asterisks.
    """
    # Create host with literal asterisk in wildcard field
    host_with_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.*-2.el4_2",  # Contains literal asterisk
            }
        }
    )

    # Create host that would match wildcard but not literal asterisk
    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2",  # Would match 3.0.* wildcard
            }
        }
    )

    # Test URL-encoded asterisk should match only literal asterisk
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A-2.el4_2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    actual_host_ids = {host["id"] for host in response_data["results"]}
    expected_host_ids = {str(host_with_literal_asterisk.id)}

    assert actual_host_ids == expected_host_ids, (
        f"URL-encoded asterisk should match only literal asterisk. "
        f"Expected: {expected_host_ids}, Got: {actual_host_ids}"
    )


def test_current_url_encoded_asterisk_behavior(db_create_host, api_get):
    """Test current behavior: URL-encoded asterisk (%2A) acts as wildcard.

    This test documents the current (incorrect) behavior where %2A is decoded
    to * and then treated as a wildcard pattern.
    """
    # Create hosts that would match wildcard pattern
    host_match_1 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2",
            }
        }
    )

    host_match_2 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.5-2.el4_2",
            }
        }
    )

    # Create host with literal asterisk (also matches due to current behavior)
    host_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.*-2.el4_2",
            }
        }
    )

    # Test current behavior: URL-encoded asterisk acts as wildcard
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A-2.el4_2")
    response_status, response_data = api_get(url)

    assert response_status == 200
    actual_host_ids = {host["id"] for host in response_data["results"]}

    # Currently, all three hosts match because %2A is treated as wildcard
    expected_host_ids = {str(host_match_1.id), str(host_match_2.id), str(host_literal_asterisk.id)}

    assert actual_host_ids == expected_host_ids, (
        f"Current behavior: URL-encoded asterisk acts as wildcard. "
        f"Expected: {expected_host_ids}, Got: {actual_host_ids}"
    )


def test_wildcard_fields_support_patterns(db_create_host, api_get):
    """Test that wildcard-enabled fields support various wildcard patterns."""
    # Create hosts with different values for wildcard fields
    hosts_data = [
        {"insights_client_version": "3.0.1-2.el4_2", "os_release": "8.5.1"},
        {"insights_client_version": "3.0.5-2.el4_2", "os_release": "8.5.2"},
        {"insights_client_version": "3.1.0-1.el5_1", "os_release": "8.6.0"},
        {"insights_client_version": "4.0.0-1.el6_1", "os_release": "9.0.0"},
    ]

    created_hosts = []
    for data in hosts_data:
        host = db_create_host(extra_data={"system_profile_facts": data})
        created_hosts.append((host, data))

    # Test various wildcard patterns
    test_cases = [
        # Prefix patterns
        ("[insights_client_version]=3.0.*", [0, 1]),  # First two hosts
        ("[os_release]=8.5.*", [0, 1]),  # First two hosts
        # Suffix patterns
        ("[insights_client_version]=*el4_2", [0, 1]),  # First two hosts
        # Middle patterns
        ("[insights_client_version]=3.*.el4_2", [0, 1]),  # First two hosts
        # Full wildcard
        ("[insights_client_version]=*", [0, 1, 2, 3]),  # All hosts
    ]

    for filter_param, expected_indices in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile]{filter_param}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        actual_host_ids = {host["id"] for host in response_data["results"]}
        expected_host_ids = {str(created_hosts[i][0].id) for i in expected_indices}

        assert actual_host_ids == expected_host_ids, (
            f"Wildcard pattern {filter_param} should match expected hosts. "
            f"Expected: {expected_host_ids}, Got: {actual_host_ids}"
        )


def test_non_wildcard_fields_exact_match_only(db_create_host, api_get):
    """Test that non-wildcard fields only support exact matching."""
    # Create hosts with different arch values (arch is not a wildcard field)
    host_x86 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "arch": "x86_64",
            }
        }
    )

    db_create_host(
        extra_data={
            "system_profile_facts": {
                "arch": "aarch64",
            }
        }
    )

    host_with_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "arch": "x86*64",  # Literal asterisk in arch
            }
        }
    )

    # Test exact match works
    url = build_hosts_url(query="?filter[system_profile][arch]=x86_64")
    response_status, response_data = api_get(url)

    assert response_status == 200
    actual_host_ids = {host["id"] for host in response_data["results"]}
    expected_host_ids = {str(host_x86.id)}

    assert actual_host_ids == expected_host_ids

    # Test that asterisk in non-wildcard field is treated literally
    url = build_hosts_url(query="?filter[system_profile][arch]=x86*64")
    response_status, response_data = api_get(url)

    assert response_status == 200
    actual_host_ids = {host["id"] for host in response_data["results"]}
    expected_host_ids = {str(host_with_asterisk.id)}

    assert actual_host_ids == expected_host_ids


@pytest.mark.xfail(reason="URL-encoded asterisk fix is incomplete - needs deeper changes to connexion URL processing")
def test_mixed_url_encoded_and_regular_wildcards(db_create_host, api_get):
    """Test combinations of URL-encoded asterisks and regular wildcards.

    This test documents the expected behavior for complex patterns mixing
    literal asterisks (via %2A) and wildcard asterisks (via *).
    """
    # Create host with mixed literal and wildcard-matchable content
    host_mixed = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.*-2.el4_2",  # Has literal asterisk
            }
        }
    )

    # Create host that would match partial wildcard but not literal asterisk
    db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2",  # No literal asterisk
            }
        }
    )

    # Test: URL-encoded asterisk for literal match + regular wildcard for pattern
    # This should match only the host with literal asterisk in the right position
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A-*")
    response_status, response_data = api_get(url)

    assert response_status == 200
    actual_host_ids = {host["id"] for host in response_data["results"]}
    expected_host_ids = {str(host_mixed.id)}

    assert actual_host_ids == expected_host_ids, (
        f"Mixed URL-encoded and regular wildcard should match only literal asterisk host. "
        f"Expected: {expected_host_ids}, Got: {actual_host_ids}"
    )


def test_bootc_image_wildcard_fields(db_create_host, api_get):
    """Test wildcard functionality in bootc image fields."""
    # Create hosts with different bootc image values
    host_quay = db_create_host(
        extra_data={
            "system_profile_facts": {
                "bootc_status": {
                    "booted": {"image": "quay.io/repo/app:latest"},
                }
            }
        }
    )

    host_registry = db_create_host(
        extra_data={
            "system_profile_facts": {
                "bootc_status": {
                    "booted": {"image": "registry.io/myrepo/image:tag"},
                }
            }
        }
    )

    # Test wildcard patterns in bootc image fields
    test_cases = [
        ("[bootc_status][booted][image]=quay.io/*", [host_quay.id]),
        ("[bootc_status][booted][image]=registry.io/*", [host_registry.id]),
        ("[bootc_status][booted][image]=*:latest", [host_quay.id]),
        ("[bootc_status][booted][image]=*", [host_quay.id, host_registry.id]),
    ]

    for filter_param, expected_host_ids in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile]{filter_param}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        actual_host_ids = {host["id"] for host in response_data["results"]}
        expected_host_ids_set = {str(host_id) for host_id in expected_host_ids}

        assert actual_host_ids == expected_host_ids_set, (
            f"Bootc wildcard filter {filter_param} should match expected hosts. "
            f"Expected: {expected_host_ids_set}, Got: {actual_host_ids}"
        )


def test_backward_compatibility_existing_queries(db_create_host, api_get):
    """Test that existing wildcard queries continue to work unchanged."""
    # Create hosts for backward compatibility testing
    host_version_1 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2",
            }
        }
    )

    host_version_2 = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.5-2.el4_2",
            }
        }
    )

    host_different = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "4.0.1-2.el4_2",
            }
        }
    )

    # Test existing wildcard patterns that should continue working
    existing_patterns = [
        ("3.0.*", [host_version_1.id, host_version_2.id]),  # Prefix wildcard
        ("*el4_2", [host_version_1.id, host_version_2.id, host_different.id]),  # Suffix wildcard
        ("3.0.*-2.el4_2", [host_version_1.id, host_version_2.id]),  # Middle wildcard
        ("*", [host_version_1.id, host_version_2.id, host_different.id]),  # Match all
    ]

    for pattern, expected_host_ids in existing_patterns:
        url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={pattern}")
        response_status, response_data = api_get(url)

        assert response_status == 200
        actual_host_ids = {host["id"] for host in response_data["results"]}
        expected_host_ids_set = {str(host_id) for host_id in expected_host_ids}

        assert actual_host_ids == expected_host_ids_set, (
            f"Existing wildcard pattern '{pattern}' should continue working. "
            f"Expected: {expected_host_ids_set}, Got: {actual_host_ids}"
        )
