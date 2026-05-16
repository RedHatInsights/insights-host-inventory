"""Test for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted."""

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


def test_url_encoded_asterisk_should_be_literal(db_create_host, api_get):
    """Test that URL-encoded %2A should be treated as literal asterisk, not wildcard."""
    # Create a host with a literal asterisk in os_release
    host_with_literal_asterisk = minimal_host(system_profile={"os_release": "abc*123"})
    literal_host_id = str(
        db_create_host(extra_data={"system_profile_facts": host_with_literal_asterisk.system_profile}).id
    )

    # Create a host with a different os_release that would match wildcard pattern
    host_with_different_release = minimal_host(system_profile={"os_release": "abcXYZ123"})
    different_host_id = str(
        db_create_host(extra_data={"system_profile_facts": host_with_different_release.system_profile}).id
    )

    # Test 1: Using literal asterisk should match both (wildcard behavior)
    url_literal = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_literal)
    assert response_status == 200
    literal_result_ids = [host["id"] for host in response_data["results"]]
    # Both hosts should match because * is treated as wildcard
    assert literal_host_id in literal_result_ids
    assert different_host_id in literal_result_ids

    # Test 2: Using URL-encoded asterisk should only match the literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded)
    assert response_status == 200
    encoded_result_ids = [host["id"] for host in response_data["results"]]
    # Only the host with literal asterisk should match
    assert literal_host_id in encoded_result_ids
    assert different_host_id not in encoded_result_ids


def test_url_encoded_backslash_handling(db_create_host, api_get):
    """Test that URL-encoded backslash is handled correctly in ILIKE patterns."""
    # Create a host with backslash in os_release
    host_with_backslash = minimal_host(system_profile={"os_release": "test1*test2\\test3"})
    backslash_host_id = str(db_create_host(extra_data={"system_profile_facts": host_with_backslash.system_profile}).id)

    # Create a host that shouldn't match
    host_different = minimal_host(system_profile={"os_release": "test1Xtest2Ytest3"})
    different_host_id = str(db_create_host(extra_data={"system_profile_facts": host_different.system_profile}).id)

    # Test: Using URL-encoded values should match the exact string
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)
    assert response_status == 200
    result_ids = [host["id"] for host in response_data["results"]]
    # Only the host with the exact string should match
    assert backslash_host_id in result_ids
    assert different_host_id not in result_ids


def test_insights_client_version_wildcard_vs_literal(db_create_host, api_get):
    """Test wildcard vs literal behavior for insights_client_version field."""
    # Create a host with literal asterisk in insights_client_version
    host_with_literal = minimal_host(system_profile={"insights_client_version": "3.0.*-2.el4_2"})
    literal_host_id = str(db_create_host(extra_data={"system_profile_facts": host_with_literal.system_profile}).id)

    # Create a host that would match the wildcard pattern
    host_matching_pattern = minimal_host(system_profile={"insights_client_version": "3.0.1-2.el4_2"})
    pattern_host_id = str(db_create_host(extra_data={"system_profile_facts": host_matching_pattern.system_profile}).id)

    # Test 1: Using literal asterisk should match both (wildcard behavior)
    url_literal = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*-2.el4_2")
    response_status, response_data = api_get(url_literal)
    assert response_status == 200
    literal_result_ids = [host["id"] for host in response_data["results"]]
    # Both hosts should match because * is treated as wildcard
    assert literal_host_id in literal_result_ids
    assert pattern_host_id in literal_result_ids

    # Test 2: Using URL-encoded asterisk should only match the literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%2A-2.el4_2")
    response_status, response_data = api_get(url_encoded)
    assert response_status == 200
    encoded_result_ids = [host["id"] for host in response_data["results"]]
    # Only the host with literal asterisk should match
    assert literal_host_id in encoded_result_ids
    assert pattern_host_id not in encoded_result_ids
