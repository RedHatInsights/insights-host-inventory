import pytest

from tests.helpers.api_utils import build_hosts_url


@pytest.mark.parametrize(
    "filter_value,host_value,should_match",
    (
        # Test escaped asterisks - should match literal asterisks
        ("\\*", "*", True),
        ("\\*", "test", False),
        ("test\\*", "test*", True),
        ("test\\*", "test", False),
        ("\\*test", "*test", True),
        ("\\*test", "test", False),
        ("test\\*value", "test*value", True),
        ("test\\*value", "testvalue", False),
        # Test escaped backslashes - should match literal backslashes
        ("\\\\", "\\", True),
        ("\\\\", "test", False),
        ("test\\\\", "test\\", True),
        ("test\\\\", "test", False),
        ("\\\\test", "\\test", True),
        ("\\\\test", "test", False),
        ("test\\\\value", "test\\value", True),
        ("test\\\\value", "testvalue", False),
        # Test unescaped asterisks - should work as wildcards
        ("test*", "test", True),
        ("test*", "testing", True),
        ("test*", "tes", False),
        ("*test", "test", True),
        ("*test", "mytest", True),
        ("*test", "tes", False),
        ("test*value", "testvalue", True),
        ("test*value", "test123value", True),
        ("test*value", "testval", False),
        # Test mixed patterns with escaped and unescaped characters
        ("\\**", "*anything", True),
        ("\\**", "anything", False),
        ("*\\*", "anything*", True),
        ("*\\*", "anything", False),
        ("test\\**", "test*anything", True),
        ("test\\**", "testanything", False),
        ("*\\*test", "anything*test", True),
        ("*\\*test", "anythingtest", False),
        # Test complex mixed patterns
        ("\\*test*value\\*", "*testANYTHINGvalue*", True),
        ("\\*test*value\\*", "testANYTHINGvalue*", False),
        ("\\*test*value\\*", "*testANYTHINGvalue", False),
        # Test edge cases
        ("", "", True),
        ("", "test", False),
        ("test", "test", True),
        ("test", "other", False),
    ),
)
def test_system_profile_wildcard_escaping(db_create_host, api_get, filter_value, host_value, should_match):
    """Test that wildcard escaping works correctly for system profile fields."""
    # Create a host with the test value in insights_client_version field
    host_data = {"system_profile_facts": {"insights_client_version": host_value}}
    created_host_id = str(db_create_host(extra_data=host_data).id)

    # Create a non-matching host to ensure we're filtering correctly
    # Use a value that won't match any of our test patterns
    nomatch_host_data = {"system_profile_facts": {"insights_client_version": "ZZZNOMATCHZZZ"}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    # Query with the filter value
    url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={filter_value}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]

    if should_match:
        assert created_host_id in response_ids, (
            f"Expected host with value '{host_value}' to match filter '{filter_value}'"
        )
    else:
        assert created_host_id not in response_ids, (
            f"Expected host with value '{host_value}' NOT to match filter '{filter_value}'"
        )

    # The non-matching host should never be in results unless we're using a wildcard that matches everything
    if filter_value not in ["*", "*test*", "*value*", "*anything*"]:
        assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "field_path,filter_value,host_value",
    (
        ("insights_client_version", "\\*special\\*", "*special*"),
        ("insights_client_version", "version\\*3.0", "version*3.0"),
        ("bootc_status][booted][image", "quay.io\\*special", "quay.io*special"),
        ("bootc_status][booted][image", "registry\\\\path", "registry\\path"),
    ),
)
def test_system_profile_wildcard_escaping_multiple_fields(
    db_create_host, api_get, field_path, filter_value, host_value
):
    """Test that wildcard escaping works across different system profile fields."""
    # Create appropriate host data based on field path
    if "bootc_status" in field_path:
        host_data = {"system_profile_facts": {"bootc_status": {"booted": {"image": host_value}}}}
    else:
        host_data = {"system_profile_facts": {field_path: host_value}}

    created_host_id = str(db_create_host(extra_data=host_data).id)

    # Query with the filter value
    url = build_hosts_url(query=f"?filter[system_profile][{field_path}]={filter_value}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert created_host_id in response_ids


def test_system_profile_wildcard_escaping_backward_compatibility(db_create_host, api_get):
    """Test that existing wildcard functionality remains unchanged."""
    # Create hosts with various insights_client_version values
    hosts_data = [
        {"system_profile_facts": {"insights_client_version": "3.0.1-2.el4_2"}},
        {"system_profile_facts": {"insights_client_version": "3.0.5-1.el7_9"}},
        {"system_profile_facts": {"insights_client_version": "3.1.0-3.el8_4"}},
        {"system_profile_facts": {"insights_client_version": "2.9.8-1.el6_10"}},
    ]

    created_host_ids = [str(db_create_host(extra_data=data).id) for data in hosts_data]

    # Test that unescaped wildcards still work as before
    test_cases = [
        ("3.0.*", [0, 1]),  # Should match first two hosts
        ("*el4_2", [0]),  # Should match first host
        ("*el*", [0, 1, 2, 3]),  # Should match all hosts
        ("3.*", [0, 1, 2]),  # Should match first three hosts
    ]

    for filter_value, expected_indices in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={filter_value}")
        response_status, response_data = api_get(url)

        assert response_status == 200

        response_ids = [result["id"] for result in response_data["results"]]
        expected_ids = [created_host_ids[i] for i in expected_indices]

        assert len(response_ids) == len(expected_ids), (
            f"Filter '{filter_value}' returned {len(response_ids)} hosts, expected {len(expected_ids)}"
        )

        for expected_id in expected_ids:
            assert expected_id in response_ids, f"Filter '{filter_value}' should have matched host {expected_id}"


def test_system_profile_wildcard_escaping_complex_scenarios(db_create_host, api_get):
    """Test complex scenarios with multiple escaped and unescaped characters."""
    # Create hosts with complex values that test various escaping scenarios
    hosts_data = [
        {"system_profile_facts": {"insights_client_version": "*literal*asterisk*"}},
        {"system_profile_facts": {"insights_client_version": "\\literal\\backslash\\"}},
        {"system_profile_facts": {"insights_client_version": "mixed*and\\literal"}},
        {"system_profile_facts": {"insights_client_version": "normal_version_3.0.1"}},
    ]

    created_host_ids = [str(db_create_host(extra_data=data).id) for data in hosts_data]

    # Test complex filter patterns
    test_cases = [
        # Match literal asterisks with escaped pattern
        ("\\*literal\\*asterisk\\*", [0]),
        # Match literal backslashes with escaped pattern
        ("\\\\literal\\\\backslash\\\\", [1]),
        # Mixed pattern with both escaped and wildcard
        ("mixed\\**literal", [2]),
        # Wildcard pattern that should match multiple hosts
        ("*literal*", [0, 1, 2]),
        # Normal wildcard pattern
        ("normal*", [3]),
    ]

    for filter_value, expected_indices in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={filter_value}")
        response_status, response_data = api_get(url)

        assert response_status == 200

        response_ids = [result["id"] for result in response_data["results"]]
        expected_ids = [created_host_ids[i] for i in expected_indices]

        assert len(response_ids) == len(expected_ids), (
            f"Filter '{filter_value}' returned {len(response_ids)} hosts, expected {len(expected_ids)}"
        )

        for expected_id in expected_ids:
            assert expected_id in response_ids, f"Filter '{filter_value}' should have matched host {expected_id}"


def test_system_profile_wildcard_escaping_nested_fields(db_create_host, api_get):
    """Test that wildcard escaping works for nested system profile fields."""
    # Create hosts with nested field values containing special characters
    hosts_data = [
        {"system_profile_facts": {"bootc_status": {"booted": {"image": "quay.io*special*image"}}}},
        {"system_profile_facts": {"bootc_status": {"booted": {"image": "quay.io\\literal\\backslash"}}}},
        {"system_profile_facts": {"bootc_status": {"booted": {"image": "quay.io/normal/image:latest"}}}},
    ]

    created_host_ids = [str(db_create_host(extra_data=data).id) for data in hosts_data]

    # Test escaping in nested fields
    test_cases = [
        # Match literal asterisks in nested field
        ("quay.io\\*special\\*image", [0]),
        # Match literal backslashes in nested field
        ("quay.io\\\\literal\\\\backslash", [1]),
        # Wildcard pattern that should match multiple hosts
        ("quay.io*", [0, 1, 2]),
        # Specific wildcard pattern
        ("*normal*", [2]),
    ]

    for filter_value, expected_indices in test_cases:
        url = build_hosts_url(query=f"?filter[system_profile][bootc_status][booted][image]={filter_value}")
        response_status, response_data = api_get(url)

        assert response_status == 200

        response_ids = [result["id"] for result in response_data["results"]]
        expected_ids = [created_host_ids[i] for i in expected_indices]

        assert len(response_ids) == len(expected_ids), (
            f"Filter '{filter_value}' returned {len(response_ids)} hosts, expected {len(expected_ids)}"
        )

        for expected_id in expected_ids:
            assert expected_id in response_ids, f"Filter '{filter_value}' should have matched host {expected_id}"


def test_wildcard_escaping_specific_cases(db_create_host, api_get):
    """Test specific wildcard escaping cases to ensure the fix works correctly."""
    # Test case 1: Escaped asterisk should match literal asterisk
    host1_data = {"system_profile_facts": {"insights_client_version": "test*value"}}
    host1_id = str(db_create_host(extra_data=host1_data).id)

    # Test case 2: Escaped backslash should match literal backslash
    host2_data = {"system_profile_facts": {"insights_client_version": "test\\value"}}
    host2_id = str(db_create_host(extra_data=host2_data).id)

    # Test case 3: Normal value for wildcard testing
    host3_data = {"system_profile_facts": {"insights_client_version": "testvalue"}}
    host3_id = str(db_create_host(extra_data=host3_data).id)

    # Test escaped asterisk filter
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=test\\*value")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host1_id in response_ids, "Escaped asterisk should match literal asterisk"
    assert host2_id not in response_ids, "Escaped asterisk should not match backslash"
    assert host3_id not in response_ids, "Escaped asterisk should not match without asterisk"

    # Test escaped backslash filter
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=test\\\\value")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host1_id not in response_ids, "Escaped backslash should not match asterisk"
    assert host2_id in response_ids, "Escaped backslash should match literal backslash"
    assert host3_id not in response_ids, "Escaped backslash should not match without backslash"

    # Test wildcard filter (should match all that start with "test")
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=test*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host1_id in response_ids, "Wildcard should match host with asterisk"
    assert host2_id in response_ids, "Wildcard should match host with backslash"
    assert host3_id in response_ids, "Wildcard should match normal host"
