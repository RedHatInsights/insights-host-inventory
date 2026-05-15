"""
Test for URL-encoded wildcard handling in system profile filtering.

This test verifies that URL-encoded wildcards (%2A) are treated as literal asterisks,
while unencoded wildcards (*) are treated as wildcard patterns.
"""

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_wildcard_literal_match(db_create_host, api_get):
    """Test that URL-encoded %2A is treated as literal asterisk, not wildcard."""
    # Create a host with a literal asterisk in os_release
    host_with_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "abc*123"  # Literal asterisk
            }
        }
    )

    # Create a host that would match wildcard pattern but not literal
    host_wildcard_match = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "abcXYZ123"  # Would match abc*123 as wildcard
            }
        }
    )

    # Test 1: URL-encoded %2A should match only the literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should only match the host with literal asterisk
    assert str(host_with_asterisk.id) in returned_ids
    assert str(host_wildcard_match.id) not in returned_ids
    assert len(returned_ids) == 1

    # Test 2: Unencoded * should match both (wildcard behavior)
    url_wildcard = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match both hosts (wildcard pattern)
    assert str(host_with_asterisk.id) in returned_ids
    assert str(host_wildcard_match.id) in returned_ids
    assert len(returned_ids) == 2


def test_url_encoded_backslash_literal_match(db_create_host, api_get):
    """Test that URL-encoded backslash is handled correctly in literal matching."""
    # Create a host with backslash and asterisk
    host_with_backslash = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "test1*test2\\test3"  # Literal backslash and asterisk
            }
        }
    )

    # Test: URL-encoded %2A and %5C should match literally
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match the host with literal characters
    assert str(host_with_backslash.id) in returned_ids
    assert len(returned_ids) == 1


def test_mixed_encoded_unencoded_wildcards(db_create_host, api_get):
    """Test mixed URL-encoded and unencoded wildcards in the same filter."""
    # Create hosts with different patterns
    host_literal_star = db_create_host(extra_data={"system_profile_facts": {"os_release": "prefix*suffix.version"}})

    host_wildcard_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "prefixXsuffix.123"}})

    # Test: prefix%2Asuffix.* should match literal * in prefix but wildcard at end
    url_mixed = build_hosts_url(query="?filter[system_profile][os_release]=prefix%2Asuffix.*")
    response_status, response_data = api_get(url_mixed)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match the host with literal asterisk in prefix
    assert str(host_literal_star.id) in returned_ids
    # Should not match the other host (doesn't have literal * in prefix)
    assert str(host_wildcard_match.id) not in returned_ids
    assert len(returned_ids) == 1


def test_insights_client_version_wildcard_encoding(db_create_host, api_get):
    """Test wildcard encoding with insights_client_version field."""
    # Create hosts with different version patterns
    host_literal_star = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.*-2.el4_2"  # Literal asterisk
            }
        }
    )

    host_wildcard_match = db_create_host(
        extra_data={
            "system_profile_facts": {
                "insights_client_version": "3.0.1-2.el4_2"  # Would match 3.0.* as wildcard
            }
        }
    )

    # Test 1: URL-encoded %2A should match only literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A-2.el4_2")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should only match the host with literal asterisk
    assert str(host_literal_star.id) in returned_ids
    assert str(host_wildcard_match.id) not in returned_ids
    assert len(returned_ids) == 1

    # Test 2: Unencoded * should match both (wildcard behavior)
    url_wildcard = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*-2.el4_2")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match both hosts (wildcard pattern)
    assert str(host_literal_star.id) in returned_ids
    assert str(host_wildcard_match.id) in returned_ids
    assert len(returned_ids) == 2
