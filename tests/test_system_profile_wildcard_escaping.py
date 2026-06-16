"""Tests for system profile wildcard asterisk escaping functionality."""

import pytest

from tests.helpers.api_utils import build_hosts_url


@pytest.mark.parametrize(
    "field_name,field_value,search_pattern,should_match",
    [
        # Test literal asterisk matching with backslash escaping
        ("insights_client_version", "3.0.*-2.el8", "3.0.\\*-2.el8", True),
        ("insights_client_version", "3.0.1-2.el8", "3.0.\\*-2.el8", False),
        ("insights_client_version", "3.0.*-2.el8", "3.0.*-2.el8", True),  # Wildcard still works
        ("insights_client_version", "3.0.1-2.el8", "3.0.*-2.el8", True),  # Wildcard still works
        # Test with bios_release_date field
        ("bios_release_date", "2021-*-15", "2021-\\*-15", True),
        ("bios_release_date", "2021-01-15", "2021-\\*-15", False),
        ("bios_release_date", "2021-*-15", "2021-*-15", True),  # Wildcard still works
        ("bios_release_date", "2021-01-15", "2021-*-15", True),  # Wildcard still works
        # Test with os_release field (supports wildcards)
        ("os_release", "RHEL-*", "RHEL-\\*", True),
        ("os_release", "RHEL-8.5", "RHEL-\\*", False),
        ("os_release", "RHEL-*", "RHEL-*", True),  # Wildcard still works
        ("os_release", "RHEL-8.5", "RHEL-*", True),  # Wildcard still works
        # Test mixed scenarios with both literal and wildcard asterisks
        ("insights_client_version", "3.0.*-2.el8_*", "3.0.\\*-2.el8_*", True),
        (
            "insights_client_version",
            "3.0.1-2.el8_4",
            "3.0.\\*-2.el8_*",
            False,
        ),  # First * is literal, second is wildcard
        (
            "insights_client_version",
            "3.0.*-2.el8_4",
            "3.0.\\*-2.el8_*",
            True,
        ),  # First * is literal, second is wildcard
    ],
)
def test_system_profile_wildcard_asterisk_escaping(
    db_create_host, api_get, field_name, field_value, search_pattern, should_match
):
    """Test that backslash-escaped asterisks are treated as literal characters in wildcard-enabled fields."""

    # Create system profile data
    sp_data = {"system_profile_facts": {field_name: field_value}}
    filter_param = f"[{field_name}]={search_pattern}"

    # Create host with the test data
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create a non-matching host for comparison
    nomatch_sp_data = {"system_profile_facts": {field_name: "completely_different_value"}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Query with the search pattern
    url = build_hosts_url(query=f"?filter[system_profile]{filter_param}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]

    if should_match:
        assert host_id in response_ids, (
            f"Host with {field_name}='{field_value}' should match pattern '{search_pattern}'"
        )
        assert nomatch_host_id not in response_ids
    else:
        assert host_id not in response_ids, (
            f"Host with {field_name}='{field_value}' should NOT match pattern '{search_pattern}'"
        )
        assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "field_name,test_values,search_pattern,expected_matches",
    [
        # Test multiple hosts with different asterisk patterns
        (
            "insights_client_version",
            ["3.0.*-2.el8", "3.0.1-2.el8", "3.0.2-2.el8", "4.0.*-2.el8"],
            "3.0.\\*-2.el8",  # Should only match the literal asterisk
            ["3.0.*-2.el8"],
        ),
        (
            "insights_client_version",
            ["3.0.*-2.el8", "3.0.1-2.el8", "3.0.2-2.el8", "4.0.*-2.el8"],
            "3.0.*-2.el8",  # Should match both literal and numeric versions
            ["3.0.*-2.el8", "3.0.1-2.el8", "3.0.2-2.el8"],
        ),
        (
            "bios_release_date",
            ["2021-*-15", "2021-01-15", "2021-12-15", "2022-*-15"],
            "2021-\\*-15",  # Should only match the literal asterisk
            ["2021-*-15"],
        ),
        (
            "bios_release_date",
            ["2021-*-15", "2021-01-15", "2021-12-15", "2022-*-15"],
            "2021-*-15",  # Should match both literal and date versions
            ["2021-*-15", "2021-01-15", "2021-12-15"],
        ),
    ],
)
def test_system_profile_wildcard_multiple_hosts(
    db_create_host, api_get, field_name, test_values, search_pattern, expected_matches
):
    """Test asterisk escaping behavior with multiple hosts having different patterns."""

    # Create hosts with different values
    host_ids = {}
    for value in test_values:
        sp_data = {"system_profile_facts": {field_name: value}}
        host_id = str(db_create_host(extra_data=sp_data).id)
        host_ids[value] = host_id

    # Query with the search pattern
    url = build_hosts_url(query=f"?filter[system_profile][{field_name}]={search_pattern}")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    expected_host_ids = [host_ids[value] for value in expected_matches]

    assert len(response_ids) == len(expected_host_ids), (
        f"Expected {len(expected_host_ids)} matches, got {len(response_ids)}"
    )

    for expected_id in expected_host_ids:
        assert expected_id in response_ids, f"Expected host with ID {expected_id} to be in results"

    # Verify no unexpected hosts are returned
    for host_id in response_ids:
        assert host_id in expected_host_ids, f"Unexpected host with ID {host_id} in results"


def test_system_profile_wildcard_url_encoding_asterisk(db_create_host, api_get):
    """Test that URL-encoded asterisk (%2A) is treated as literal when part of escaped sequence (%5C%2A)."""

    # Create host with literal asterisk in insights_client_version
    sp_data = {"system_profile_facts": {"insights_client_version": "3.0.*-2.el8"}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create host with numeric version (should not match literal asterisk search)
    nomatch_sp_data = {"system_profile_facts": {"insights_client_version": "3.0.1-2.el8"}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Test URL-encoded backslash-asterisk sequence (%5C%2A)
    # This should be decoded to \* and then treated as literal asterisk
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0.%5C%2A-2.el8")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match URL-encoded escaped asterisk"
    assert nomatch_host_id not in response_ids, "Host with numeric version should not match literal asterisk search"


def test_system_profile_wildcard_complex_escaping_scenarios(db_create_host, api_get):
    """Test complex scenarios with multiple asterisks and escaping combinations."""

    test_cases = [
        {
            "field_value": "test*value*end",
            "search_pattern": "test\\*value*end",  # First * literal, second * wildcard
            "description": "mixed literal and wildcard asterisks",
            "should_match": True,
        },
        {
            "field_value": "test1value2end",
            "search_pattern": "test\\*value*end",  # First * literal, second * wildcard
            "description": "numeric chars where literal asterisk expected",
            "should_match": False,
        },
        {
            "field_value": "test*value*end",
            "search_pattern": "test\\*value\\*end",  # Both asterisks literal
            "description": "both asterisks literal",
            "should_match": True,
        },
        {
            "field_value": "test1value2end",
            "search_pattern": "test\\*value\\*end",  # Both asterisks literal
            "description": "numeric chars where both literal asterisks expected",
            "should_match": False,
        },
    ]

    for i, test_case in enumerate(test_cases):
        # Create host with test value
        sp_data = {"system_profile_facts": {"insights_client_version": test_case["field_value"]}}
        host_id = str(db_create_host(extra_data=sp_data).id)

        # Query with search pattern
        url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={test_case['search_pattern']}")
        response_status, response_data = api_get(url)

        assert response_status == 200

        response_ids = [result["id"] for result in response_data["results"]]

        if test_case["should_match"]:
            assert host_id in response_ids, f"Test case {i + 1} ({test_case['description']}): Host should match"
        else:
            assert host_id not in response_ids, (
                f"Test case {i + 1} ({test_case['description']}): Host should not match"
            )


def test_system_profile_wildcard_backwards_compatibility(db_create_host, api_get):
    """Test that existing wildcard functionality remains unchanged."""

    # Create hosts with different insights_client_version values
    test_values = ["3.0.1-2.el8", "3.0.2-2.el8", "3.0.10-2.el8", "4.0.1-2.el8", "3.1.1-2.el8"]

    host_ids = []
    for value in test_values:
        sp_data = {"system_profile_facts": {"insights_client_version": value}}
        host_id = str(db_create_host(extra_data=sp_data).id)
        host_ids.append(host_id)

    # Test that regular wildcard patterns still work as expected
    wildcard_tests = [
        {
            "pattern": "3.0.*",
            "expected_matches": ["3.0.1-2.el8", "3.0.2-2.el8", "3.0.10-2.el8"],
            "description": "prefix wildcard",
        },
        {
            "pattern": "*-2.el8",
            "expected_matches": test_values,  # All should match
            "description": "suffix wildcard",
        },
        {
            "pattern": "3.*.1-2.el8",
            "expected_matches": ["3.0.1-2.el8", "3.1.1-2.el8"],
            "description": "middle wildcard",
        },
    ]

    for test in wildcard_tests:
        url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={test['pattern']}")
        response_status, response_data = api_get(url)

        assert response_status == 200

        response_ids = [result["id"] for result in response_data["results"]]
        expected_count = len(test["expected_matches"])

        assert len(response_ids) == expected_count, (
            f"Wildcard test '{test['description']}': expected {expected_count} matches, got {len(response_ids)}"
        )

        # Verify all expected values are matched
        for expected_value in test["expected_matches"]:
            expected_index = test_values.index(expected_value)
            expected_host_id = host_ids[expected_index]
            assert expected_host_id in response_ids, (
                f"Wildcard test '{test['description']}': missing expected host with value '{expected_value}'"
            )


def test_system_profile_wildcard_bootc_image_field(db_create_host, api_get):
    """Test asterisk escaping in nested bootc image field."""

    # Create host with literal asterisk in bootc image
    sp_data = {"system_profile_facts": {"bootc_status": {"booted": {"image": "quay.io/test*image:latest"}}}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create host without asterisk (should not match literal asterisk search)
    nomatch_sp_data = {"system_profile_facts": {"bootc_status": {"booted": {"image": "quay.io/testimage:latest"}}}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Test literal asterisk search
    url = build_hosts_url(query="?filter[system_profile][bootc_status][booted][image]=quay.io/test\\*image:latest")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match escaped asterisk search"
    assert nomatch_host_id not in response_ids, "Host without asterisk should not match literal asterisk search"

    # Test wildcard search (should match both)
    url = build_hosts_url(query="?filter[system_profile][bootc_status][booted][image]=quay.io/test*image:latest")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match wildcard search"
    assert nomatch_host_id in response_ids, "Host without asterisk should match wildcard search"


def test_system_profile_wildcard_workloads_mssql_version(db_create_host, api_get):
    """Test asterisk escaping in workloads mssql version field."""

    # Create host with literal asterisk in mssql version
    sp_data = {"system_profile_facts": {"workloads": {"mssql": {"version": "15.*"}}}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create host with numeric version (should not match literal asterisk search)
    nomatch_sp_data = {"system_profile_facts": {"workloads": {"mssql": {"version": "15.3"}}}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Test literal asterisk search
    url = build_hosts_url(query="?filter[system_profile][workloads][mssql][version]=15.\\*")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match escaped asterisk search"
    assert nomatch_host_id not in response_ids, "Host with numeric version should not match literal asterisk search"

    # Test wildcard search (should match both)
    url = build_hosts_url(query="?filter[system_profile][workloads][mssql][version]=15.*")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match wildcard search"
    assert nomatch_host_id in response_ids, "Host with numeric version should match wildcard search"


def test_system_profile_wildcard_legacy_field_access(db_create_host, api_get):
    """Test asterisk escaping with legacy field access patterns."""

    # Create host with literal asterisk in mssql version using legacy access
    sp_data = {"system_profile_facts": {"workloads": {"mssql": {"version": "15.*"}}}}
    host_id = str(db_create_host(extra_data=sp_data).id)

    # Create host with numeric version
    nomatch_sp_data = {"system_profile_facts": {"workloads": {"mssql": {"version": "15.3"}}}}
    nomatch_host_id = str(db_create_host(extra_data=nomatch_sp_data).id)

    # Test literal asterisk search using legacy field access
    url = build_hosts_url(query="?filter[system_profile][mssql][version]=15.\\*")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match escaped asterisk search (legacy access)"
    assert nomatch_host_id not in response_ids, (
        "Host with numeric version should not match literal asterisk search (legacy access)"
    )

    # Test wildcard search using legacy field access (should match both)
    url = build_hosts_url(query="?filter[system_profile][mssql][version]=15.*")
    response_status, response_data = api_get(url)

    assert response_status == 200

    response_ids = [result["id"] for result in response_data["results"]]
    assert host_id in response_ids, "Host with literal asterisk should match wildcard search (legacy access)"
    assert nomatch_host_id in response_ids, "Host with numeric version should match wildcard search (legacy access)"
