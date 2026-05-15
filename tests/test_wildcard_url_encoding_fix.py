"""
Test for RHINENG-4809: URL-encoded wildcards should be treated as literal characters.

When a user sends %2A in the URL, it should be treated as a literal "*" character,
not as a wildcard pattern.
"""

import pytest

from tests.helpers.api_utils import build_hosts_url
from tests.helpers.test_utils import minimal_host


def test_url_encoded_wildcard_treated_as_literal(mq_create_or_update_host, api_get):
    """
    Test that URL-encoded wildcards (%2A) are treated as literal characters.

    This test verifies the fix for RHINENG-4809 where URL-encoded wildcards
    were incorrectly being treated as wildcard patterns.
    """
    # Create a host with a literal "*" in the os_release field
    host_with_literal_star = minimal_host(system_profile={"os_release": "abc*123"})
    created_host = mq_create_or_update_host(host_with_literal_star)

    # Create a host that would match if "*" was treated as a wildcard
    host_that_matches_wildcard = minimal_host(system_profile={"os_release": "abcXYZ123"})
    mq_create_or_update_host(host_that_matches_wildcard)

    # Test 1: URL-encoded wildcard (%2A) should match only the literal "*"
    url_encoded_query = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded_query)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == created_host.id

    # Test 2: Regular wildcard (*) should match both hosts
    wildcard_query = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(wildcard_query)

    assert response_status == 200
    assert len(response_data["results"]) == 2


def test_url_encoded_backslash_in_wildcard_field(mq_create_or_update_host, api_get):
    """
    Test that URL-encoded backslashes are handled correctly in wildcard fields.

    This addresses the second part of RHINENG-4809 where backslashes in URL-encoded
    values cause issues with ILIKE pattern matching.
    """
    # Create a host with backslashes and asterisks in the os_release field
    host_with_backslash_star = minimal_host(system_profile={"os_release": "test1*test2\\test3"})
    created_host = mq_create_or_update_host(host_with_backslash_star)

    # Test: URL-encoded query should match the exact literal value
    url_encoded_query = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded_query)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == created_host.id


def test_regular_wildcard_still_works(mq_create_or_update_host, api_get):
    """
    Test that regular wildcard functionality is not broken by the fix.
    """
    # Create hosts with different os_release values
    host1 = mq_create_or_update_host(minimal_host(system_profile={"os_release": "abc.123"}))
    host2 = mq_create_or_update_host(minimal_host(system_profile={"os_release": "abc*123"}))
    host3 = mq_create_or_update_host(minimal_host(system_profile={"os_release": "abcdefghijkl123"}))

    # Test: Regular wildcard should match all three hosts
    wildcard_query = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(wildcard_query)

    assert response_status == 200
    assert len(response_data["results"]) == 3

    returned_ids = {result["id"] for result in response_data["results"]}
    expected_ids = {host1.id, host2.id, host3.id}
    assert returned_ids == expected_ids


@pytest.mark.parametrize("field_name", ["os_release", "bios_release_date", "insights_client_version"])
def test_url_encoded_wildcard_multiple_fields(mq_create_or_update_host, api_get, field_name):
    """
    Test URL-encoded wildcard handling across different wildcard-enabled fields.
    """
    # Create a host with a literal "*" in the specified field
    system_profile = {field_name: "test*value"}
    host_with_literal_star = minimal_host(system_profile=system_profile)
    created_host = mq_create_or_update_host(host_with_literal_star)

    # Test: URL-encoded wildcard should match only the literal "*"
    url_encoded_query = build_hosts_url(query=f"?filter[system_profile][{field_name}]=test%2Avalue")
    response_status, response_data = api_get(url_encoded_query)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == created_host.id
