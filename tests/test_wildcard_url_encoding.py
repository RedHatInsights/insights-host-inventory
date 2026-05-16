from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_wildcard_should_be_literal(db_create_host, api_get):
    """
    Test that URL-encoded wildcards (%2A) are treated as literal asterisks,
    not as wildcard patterns.

    This is a regression test for RHINENG-4809.
    """
    # Create a host with a literal asterisk in os_release
    host_with_literal_asterisk = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "abc*123"  # Literal asterisk
            }
        }
    )

    # Create a host that would match if * were treated as wildcard
    host_that_matches_wildcard = db_create_host(
        extra_data={
            "system_profile_facts": {
                "os_release": "abcXYZ123"  # Would match abc*123 if * is wildcard
            }
        }
    )

    # Create a host that should not match
    host_no_match = db_create_host(extra_data={"system_profile_facts": {"os_release": "def456"}})

    # Test 1: URL-encoded asterisk (%2A) should match only the literal asterisk
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    # Should only match the host with literal asterisk
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_that_matches_wildcard.id) not in response_ids
    assert str(host_no_match.id) not in response_ids
    assert len(response_ids) == 1

    # Test 2: Regular asterisk should work as wildcard
    url_wildcard = build_hosts_url(query="?filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    # Should match both hosts (literal asterisk and wildcard match)
    assert str(host_with_literal_asterisk.id) in response_ids
    assert str(host_that_matches_wildcard.id) in response_ids
    assert str(host_no_match.id) not in response_ids
    assert len(response_ids) == 2


def test_url_encoded_backslash_with_wildcard(db_create_host, api_get):
    """
    Test that URL-encoded backslashes work correctly with wildcards.

    This tests the second part of RHINENG-4809 where backslashes cause issues.
    """
    # Create a host with backslash and asterisk
    host_with_backslash = db_create_host(extra_data={"system_profile_facts": {"os_release": "test1*test2\\test3"}})

    # Test URL-encoded version should match exactly
    url_encoded = build_hosts_url(query="?filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]

    # Should match the host with literal characters
    assert str(host_with_backslash.id) in response_ids
    assert len(response_ids) == 1
