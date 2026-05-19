"""
Test for RHINENG-4809: SP filtering uses "*" as wildcard even if it is formatted

This test verifies that URL-encoded asterisks (%2A) are treated as literal asterisks
rather than wildcard characters in system profile filtering.
"""

from tests.helpers.api_utils import build_hosts_url


def test_url_encoded_asterisk_treated_as_literal(db_create_host, api_get):
    """
    Test that URL-encoded asterisks (%2A) are treated as literal asterisks, not wildcards.

    This test creates hosts with different os_release values and verifies that:
    1. Regular asterisks (*) work as wildcards
    2. URL-encoded asterisks (%2A) are treated as literal asterisks
    """
    # Create hosts with different os_release values
    host1_data = {
        "system_profile_facts": {
            "os_release": "abc*123",  # Contains literal asterisk
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    host2_data = {
        "system_profile_facts": {
            "os_release": "abc.123",  # Matches wildcard pattern abc*123
        }
    }
    host2 = db_create_host(extra_data=host2_data)

    host3_data = {
        "system_profile_facts": {
            "os_release": "abcdefghijkl123",  # Also matches wildcard pattern abc*123
        }
    }
    host3 = db_create_host(extra_data=host3_data)

    host4_data = {
        "system_profile_facts": {
            "os_release": "xyz*456",  # Different literal asterisk value
        }
    }
    host4 = db_create_host(extra_data=host4_data)

    # Test 1: Regular asterisk should work as wildcard
    # This should match host1 (abc*123), host2 (abc.123), and host3 (abcdefghijkl123)
    url_wildcard = build_hosts_url(query="filter[system_profile][os_release]=abc*123")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match hosts with os_release that matches the wildcard pattern
    assert str(host1.id) in returned_ids  # abc*123 matches abc*123
    assert str(host2.id) in returned_ids  # abc.123 matches abc*123
    assert str(host3.id) in returned_ids  # abcdefghijkl123 matches abc*123
    assert str(host4.id) not in returned_ids  # xyz*456 doesn't match abc*123

    # Test 2: URL-encoded asterisk should be treated as literal
    # This should only match host1 (abc*123) because %2A should be treated as literal *
    url_encoded = build_hosts_url(query="filter[system_profile][os_release]=abc%2A123")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should only match the host with the exact literal asterisk
    assert str(host1.id) in returned_ids  # abc*123 matches literal abc*123
    assert str(host2.id) not in returned_ids  # abc.123 doesn't match literal abc*123
    assert str(host3.id) not in returned_ids  # abcdefghijkl123 doesn't match literal abc*123
    assert str(host4.id) not in returned_ids  # xyz*456 doesn't match literal abc*123


def test_backslash_escaping_with_url_encoded_asterisk(db_create_host, api_get):
    """
    Test the specific case mentioned in the ticket about backslash escaping.

    The ticket mentions: "if I have a host with SP value == 'test1*test2\\test3' and try to
    filter it with 'test1%2Atest2%5Ctest3', it will not return my host, because the
    backslash is used as an escape character for 't' and so it then misses in the query."
    """
    # Create a host with the exact value mentioned in the ticket
    host_data = {
        "system_profile_facts": {
            "os_release": "test1*test2\\test3",  # Contains literal asterisk and backslash
        }
    }
    host = db_create_host(extra_data=host_data)

    # Test with URL-encoded asterisk and backslash
    # %2A = *, %5C = \
    url_encoded = build_hosts_url(query="filter[system_profile][os_release]=test1%2Atest2%5Ctest3")
    response_status, response_data = api_get(url_encoded)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match the host with the exact literal value
    assert str(host.id) in returned_ids


def test_mixed_encoded_and_unencoded_asterisks(db_create_host, api_get):
    """
    Test edge case with mixed encoded and unencoded asterisks in the same filter value.
    """
    # Create hosts with different patterns
    host1_data = {
        "system_profile_facts": {
            "os_release": "abc*def*ghi",  # Two literal asterisks
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    host2_data = {
        "system_profile_facts": {
            "os_release": "abc.def.ghi",  # Would match if both asterisks were wildcards
        }
    }
    host2 = db_create_host(extra_data=host2_data)

    # Test with one encoded asterisk and one unencoded
    # This should be treated as literal since at least one asterisk was URL-encoded
    url_mixed = build_hosts_url(query="filter[system_profile][os_release]=abc%2Adef*ghi")
    response_status, response_data = api_get(url_mixed)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should only match the exact literal value
    assert str(host1.id) in returned_ids  # Exact match
    assert str(host2.id) not in returned_ids  # Not an exact match


def test_case_insensitive_url_encoding_detection(db_create_host, api_get):
    """
    Test that URL encoding detection works with both %2A and %2a.
    """
    host_data = {
        "system_profile_facts": {
            "os_release": "test*value",
        }
    }
    host = db_create_host(extra_data=host_data)

    # Test with lowercase %2a
    url_lowercase = build_hosts_url(query="filter[system_profile][os_release]=test%2avalue")
    response_status, response_data = api_get(url_lowercase)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]
    assert str(host.id) in returned_ids

    # Test with uppercase %2A
    url_uppercase = build_hosts_url(query="filter[system_profile][os_release]=test%2Avalue")
    response_status, response_data = api_get(url_uppercase)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]
    assert str(host.id) in returned_ids


def test_normal_wildcard_behavior_unchanged(db_create_host, api_get):
    """
    Test that normal wildcard behavior is not affected by the fix.
    """
    # Create hosts to test normal wildcard functionality
    host1_data = {
        "system_profile_facts": {
            "os_release": "version-1.2.3",
        }
    }
    host1 = db_create_host(extra_data=host1_data)

    host2_data = {
        "system_profile_facts": {
            "os_release": "version-2.4.6",
        }
    }
    host2 = db_create_host(extra_data=host2_data)

    host3_data = {
        "system_profile_facts": {
            "os_release": "different-3.5.7",
        }
    }
    host3 = db_create_host(extra_data=host3_data)

    # Test normal wildcard behavior (no URL encoding)
    url_wildcard = build_hosts_url(query="filter[system_profile][os_release]=version-*")
    response_status, response_data = api_get(url_wildcard)

    assert response_status == 200
    returned_ids = [host["id"] for host in response_data["results"]]

    # Should match hosts that start with "version-"
    assert str(host1.id) in returned_ids
    assert str(host2.id) in returned_ids
    assert str(host3.id) not in returned_ids  # Starts with "different-"
