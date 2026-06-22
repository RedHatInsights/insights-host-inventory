import pytest

from tests.helpers.api_utils import build_hosts_url


@pytest.mark.parametrize(
    "system_profile_value,filter_value,should_match",
    [
        # Test backslash-escaped asterisk handling - should be treated as literal
        ("test*value", "test\\*value", True),  # Escaped asterisk should match literal *
        ("testXvalue", "test\\*value", False),  # Escaped asterisk should not be wildcard
        ("test*value", "test*value", True),  # Regular * should still work as wildcard
        ("testXvalue", "test*value", True),  # Regular * should match any character
        # Test mixed patterns with both escaped and wildcard asterisks
        ("test*prod*env", "test\\*prod*env", True),  # Escaped *, wildcard *
        ("testXprodYenv", "test\\*prod*env", False),  # Escaped * should not match X
        ("test*prodYenv", "test\\*prod*env", True),  # Escaped * matches *, * matches Y
        # Test multiple escaped asterisks
        ("test**value", "test\\*\\*value", True),  # Multiple escaped * should match multiple *
        ("testXXvalue", "test\\*\\*value", False),  # Escaped * should not match other chars
        # Test edge cases
        ("*", "\\*", True),  # Single escaped * should match single *
        ("X", "\\*", False),  # Single escaped * should not match other chars
        ("", "*", True),  # Empty string should match wildcard
        ("", "\\*", False),  # Empty string should not match literal *
    ],
)
def test_system_profile_wildcard_backslash_escaped_asterisk(
    db_create_host, api_get, system_profile_value, filter_value, should_match
):
    """Test that backslash-escaped asterisks (\\*) are treated as literals in wildcard fields."""
    # Create host with specific system profile value
    created_host = db_create_host(
        extra_data={"system_profile_facts": {"insights_client_version": system_profile_value}}
    )

    # Query with the filter value
    url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={filter_value}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    if should_match:
        assert len(response_data["results"]) == 1
        assert response_data["results"][0]["id"] == str(created_host.id)
    else:
        assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "os_release_value,filter_pattern,should_match",
    [
        # Test various combinations of literal and wildcard asterisks using os_release (wildcard field)
        ("7.4*beta", "7.4\\*beta", True),  # Escaped * should match literal *
        ("7.4_beta", "7.4\\*beta", False),  # Escaped * should not match _
        ("7.4*beta", "7.4*beta", True),  # Regular * should work as wildcard
        ("7.4_beta", "7.4*beta", True),  # Regular * should match _
        # Test complex patterns
        ("8.2*rc*final", "8.2\\*rc*final", True),  # Mixed literal and wildcard
        ("8.2Xrc*final", "8.2\\*rc*final", False),  # Escaped * should not match X
        ("8.2*rcYfinal", "8.2\\*rc*final", True),  # Escaped * matches *, * matches Y
    ],
)
def test_system_profile_os_release_wildcard_patterns(
    db_create_host, api_get, os_release_value, filter_pattern, should_match
):
    """Test wildcard patterns in os_release field with backslash-escaped asterisks."""
    # Create host with specific os_release value
    created_host = db_create_host(extra_data={"system_profile_facts": {"os_release": os_release_value}})

    # Query with the filter pattern
    url = build_hosts_url(query=f"?filter[system_profile][os_release]={filter_pattern}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    if should_match:
        assert len(response_data["results"]) == 1
        assert response_data["results"][0]["id"] == str(created_host.id)
    else:
        assert len(response_data["results"]) == 0


def test_system_profile_wildcard_regression_check(db_create_host, api_get):
    """Ensure existing wildcard functionality still works after URL-encoding fix."""
    # Create hosts with different insights_client_version values
    hosts_data = [
        ("3.0.1-2.el4_2", "exact_match"),
        ("3.0.5-1.el4_2", "wildcard_match_1"),
        ("3.0.10-3.el4_2", "wildcard_match_2"),
        ("2.9.1-1.el4_2", "no_match"),
    ]

    created_hosts = []
    for version, tag in hosts_data:
        host = db_create_host(
            extra_data={
                "system_profile_facts": {"insights_client_version": version},
                "tags": [{"namespace": "test", "key": "type", "value": tag}],
            }
        )
        created_hosts.append(host)

    # Test exact match (no wildcards)
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.1-2.el4_2")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == str(created_hosts[0].id)

    # Test wildcard match - should match 3.0.* pattern
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 3  # Should match first 3 hosts

    result_ids = {result["id"] for result in response_data["results"]}
    expected_ids = {str(host.id) for host in created_hosts[:3]}
    assert result_ids == expected_ids


def test_system_profile_wildcard_edge_cases(db_create_host, api_get):
    """Test edge cases for wildcard handling with backslash-escaped characters."""
    # Create hosts with edge case values - use unique display names to identify them
    edge_cases = [
        ("*", "single_asterisk_host"),
        ("**", "double_asterisk_host"),
        ("test*", "trailing_asterisk_host"),
        ("*test", "leading_asterisk_host"),
        ("te*st", "middle_asterisk_host"),
        ("", "empty_string_host"),
        ("no_asterisk", "no_asterisk_host"),
    ]

    created_hosts = []
    for value, display_name in edge_cases:
        host = db_create_host(
            extra_data={"system_profile_facts": {"insights_client_version": value}, "display_name": display_name}
        )
        created_hosts.append(host)

    # Test escaped single asterisk should match literal asterisk only
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["display_name"] == "single_asterisk_host"

    # Test escaped double asterisk should match literal double asterisk only
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\*\\*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["display_name"] == "double_asterisk_host"

    # Test regular wildcard should match multiple hosts
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=*")
    response_status, response_data = api_get(url)
    assert response_status == 200
    # Should match all hosts including empty string (7 total)
    assert len(response_data["results"]) == 7


def test_system_profile_wildcard_mixed_escaping_patterns(db_create_host, api_get):
    """Test complex patterns mixing escaped and regular asterisks."""
    # Create hosts with specific patterns - use unique display names to identify them
    test_cases = [
        ("prod*env*test", "mixed_pattern_1_host"),
        ("prod*env_test", "mixed_pattern_2_host"),
        ("prodXenvYtest", "mixed_pattern_3_host"),
        ("prod*envXtest", "mixed_pattern_4_host"),
    ]

    created_hosts = []
    for value, display_name in test_cases:
        host = db_create_host(
            extra_data={"system_profile_facts": {"insights_client_version": value}, "display_name": display_name}
        )
        created_hosts.append(host)

    # Test pattern: prod\\*env*test
    # \\* should match literal *, * should match any characters
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=prod\\*env*test")
    response_status, response_data = api_get(url)
    assert response_status == 200

    # Should match hosts with literal * after "prod" and any characters after "env"
    # This includes "prod*env*test", "prod*env_test", and "prod*envXtest"
    result_names = {result["display_name"] for result in response_data["results"]}
    expected_names = {"mixed_pattern_1_host", "mixed_pattern_2_host", "mixed_pattern_4_host"}
    assert result_names == expected_names
