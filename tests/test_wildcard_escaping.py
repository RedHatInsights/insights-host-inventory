import pytest

from tests.helpers.api_utils import build_hosts_url


@pytest.mark.parametrize(
    "filter_value,expected_match_host,expected_nomatch_host",
    (
        # Test escaped asterisks (\\*) are treated as literal characters
        ("test\\*value", "test*value", "testXvalue"),
        ("\\*start", "*start", "Xstart"),
        ("end\\*", "end*", "endX"),
        ("\\*middle\\*", "*middle*", "XmiddleX"),
        # Test unescaped asterisks (*) continue to work as wildcards
        ("test*value", "testXvalue", "different"),
        ("*start", "Xstart", "different"),
        ("end*", "endX", "different"),
        ("*middle*", "XmiddleX", "different"),
        # Test mixed scenarios with both escaped and unescaped asterisks
        ("test\\**value", "test*Xvalue", "different"),
        ("*test\\*", "Xtest*", "different"),
        ("\\*test*", "*testX", "different"),
        ("pre\\*mid*post", "pre*midXpost", "different"),
    ),
)
def test_system_profile_wildcard_escaped_asterisk_insights_client_version(
    db_create_host, api_get, filter_value, expected_match_host, expected_nomatch_host
):
    """Test escaped asterisk handling for insights_client_version field (x-wildcard: true)."""
    # Create host that should match the filter
    match_host_data = {
        "system_profile_facts": {
            "insights_client_version": expected_match_host,
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match the filter
    nomatch_host_data = {
        "system_profile_facts": {
            "insights_client_version": expected_nomatch_host,
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][insights_client_version]={filter_value}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "filter_value,expected_match_host,expected_nomatch_host",
    (
        # Test escaped asterisks for bios_release_date field
        ("2023\\*01\\*15", "2023*01*15", "2023-01-15"),
        ("\\*special", "*special", "Xspecial"),
        ("date\\*", "date*", "dateX"),
        # Test unescaped asterisks as wildcards
        ("2023*01*15", "2023-01-15", "different"),
        ("*special", "Xspecial", "different"),
        ("date*", "dateX", "different"),
    ),
)
def test_system_profile_wildcard_escaped_asterisk_bios_release_date(
    db_create_host, api_get, filter_value, expected_match_host, expected_nomatch_host
):
    """Test escaped asterisk handling for bios_release_date field (x-wildcard: true)."""
    # Create host that should match the filter
    match_host_data = {
        "system_profile_facts": {
            "bios_release_date": expected_match_host,
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match the filter
    nomatch_host_data = {
        "system_profile_facts": {
            "bios_release_date": expected_nomatch_host,
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][bios_release_date]={filter_value}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "filter_value,expected_match_host,expected_nomatch_host",
    (
        # Test escaped asterisks for bootc image field
        ("quay.io\\*image", "quay.io*image", "quay.io/image"),
        ("\\*registry", "*registry", "Xregistry"),
        ("image\\*tag", "image*tag", "image:tag"),
        # Test unescaped asterisks as wildcards
        ("quay.io*image", "quay.io/image", "different"),
        ("*registry", "Xregistry", "different"),
        ("image*tag", "image:tag", "different"),
    ),
)
def test_system_profile_wildcard_escaped_asterisk_bootc_image(
    db_create_host, api_get, filter_value, expected_match_host, expected_nomatch_host
):
    """Test escaped asterisk handling for bootc image field (x-wildcard: true)."""
    # Create host that should match the filter
    match_host_data = {
        "system_profile_facts": {
            "bootc_status": {
                "booted": {
                    "image": expected_match_host,
                }
            }
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match the filter
    nomatch_host_data = {
        "system_profile_facts": {
            "bootc_status": {
                "booted": {
                    "image": expected_nomatch_host,
                }
            }
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][bootc_status][booted][image]={filter_value}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "filter_value,expected_match_host,expected_nomatch_host",
    (
        # Test escaped asterisks for workload ansible controller_version
        ("1.0\\*beta", "1.0*beta", "1.0.beta"),
        ("\\*version", "*version", "Xversion"),
        ("ver\\*", "ver*", "verX"),
        # Test unescaped asterisks as wildcards
        ("1.0*beta", "1.0.beta", "different"),
        ("*version", "Xversion", "different"),
        ("ver*", "verX", "different"),
    ),
)
def test_system_profile_wildcard_escaped_asterisk_workload_ansible_version(
    db_create_host, api_get, filter_value, expected_match_host, expected_nomatch_host
):
    """Test escaped asterisk handling for workload ansible controller_version field (x-wildcard: true)."""
    # Create host that should match the filter
    match_host_data = {
        "system_profile_facts": {
            "workloads": {
                "ansible": {
                    "controller_version": expected_match_host,
                }
            }
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match the filter
    nomatch_host_data = {
        "system_profile_facts": {
            "workloads": {
                "ansible": {
                    "controller_version": expected_nomatch_host,
                }
            }
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][workloads][ansible][controller_version]={filter_value}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


@pytest.mark.parametrize(
    "filter_value,expected_match_host,expected_nomatch_host",
    (
        # Test escaped asterisks for workload mssql version
        ("15.3\\*enterprise", "15.3*enterprise", "15.3.enterprise"),
        ("\\*sql", "*sql", "Xsql"),
        ("version\\*", "version*", "versionX"),
        # Test unescaped asterisks as wildcards
        ("15.3*enterprise", "15.3.enterprise", "different"),
        ("*sql", "Xsql", "different"),
        ("version*", "versionX", "different"),
    ),
)
def test_system_profile_wildcard_escaped_asterisk_workload_mssql_version(
    db_create_host, api_get, filter_value, expected_match_host, expected_nomatch_host
):
    """Test escaped asterisk handling for workload mssql version field (x-wildcard: true)."""
    # Create host that should match the filter
    match_host_data = {
        "system_profile_facts": {
            "workloads": {
                "mssql": {
                    "version": expected_match_host,
                }
            }
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match the filter
    nomatch_host_data = {
        "system_profile_facts": {
            "workloads": {
                "mssql": {
                    "version": expected_nomatch_host,
                }
            }
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    url = build_hosts_url(query=f"?filter[system_profile][workloads][mssql][version]={filter_value}")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


def test_system_profile_wildcard_url_encoded_escaped_asterisk(db_create_host, api_get):
    """Test URL-encoded escaped asterisks (%5C%2A) work correctly."""
    # Create host with literal asterisk in insights_client_version
    match_host_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0*beta",
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match
    nomatch_host_data = {
        "system_profile_facts": {
            "insights_client_version": "3.0.beta",
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    # Use URL-encoded escaped asterisk: %5C%2A represents \*
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=3.0%5C%2Abeta")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the host with literal asterisk is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


def test_system_profile_wildcard_complex_mixed_scenario(db_create_host, api_get):
    """Test complex scenario with multiple escaped and unescaped asterisks."""
    # Create host that should match the complex pattern
    match_host_data = {
        "system_profile_facts": {
            "insights_client_version": "prefix*middle*suffix",
        }
    }
    match_host_id = str(db_create_host(extra_data=match_host_data).id)

    # Create host that should NOT match
    nomatch_host_data = {
        "system_profile_facts": {
            "insights_client_version": "different_pattern",
        }
    }
    nomatch_host_id = str(db_create_host(extra_data=nomatch_host_data).id)

    # Filter: prefix\\**middle\\**suffix
    # This should match: prefix*Xmiddle*Xsuffix (where X can be any character)
    # The \\* becomes literal *, the * becomes wildcard %
    url = build_hosts_url(query="?filter[system_profile][insights_client_version]=prefix\\**middle\\**suffix")

    response_status, response_data = api_get(url)

    assert response_status == 200

    # Assert that only the matching host is returned
    response_ids = [result["id"] for result in response_data["results"]]
    assert match_host_id in response_ids
    assert nomatch_host_id not in response_ids


def test_system_profile_wildcard_empty_and_edge_cases(db_create_host, api_get):
    """Test edge cases like empty strings and only asterisks."""
    # Create hosts for edge case testing
    host_empty = str(db_create_host(extra_data={"system_profile_facts": {"insights_client_version": ""}}).id)
    host_asterisk = str(db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "*"}}).id)
    host_escaped_asterisk = str(
        db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "\\*"}}).id
    )

    # Test empty string filter
    url_empty = build_hosts_url(query="?filter[system_profile][insights_client_version]=")
    response_status, response_data = api_get(url_empty)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_empty in response_ids
    assert host_asterisk not in response_ids
    assert host_escaped_asterisk not in response_ids

    # Test escaped asterisk filter (should match literal backslash-asterisk)
    url_escaped = build_hosts_url(query="?filter[system_profile][insights_client_version]=\\\\\\*")
    response_status, response_data = api_get(url_escaped)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_empty not in response_ids
    assert host_asterisk not in response_ids
    assert host_escaped_asterisk in response_ids

    # Test wildcard asterisk filter (should match any character including empty)
    url_wildcard = build_hosts_url(query="?filter[system_profile][insights_client_version]=*")
    response_status, response_data = api_get(url_wildcard)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    # All hosts should match since * matches any string (including empty)
    assert host_empty in response_ids
    assert host_asterisk in response_ids
    assert host_escaped_asterisk in response_ids


def test_system_profile_wildcard_basic_escaping_functionality(db_create_host, api_get):
    """Test basic escaping functionality with simple cases."""
    # Create hosts with different patterns
    host_literal_asterisk = str(
        db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "version*1.0"}}).id
    )

    host_no_asterisk = str(
        db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "version.1.0"}}).id
    )

    host_different = str(db_create_host(extra_data={"system_profile_facts": {"insights_client_version": "other"}}).id)

    # Test escaped asterisk - should match only the literal asterisk
    url_escaped = build_hosts_url(query="?filter[system_profile][insights_client_version]=version\\*1.0")
    response_status, response_data = api_get(url_escaped)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_literal_asterisk in response_ids
    assert host_no_asterisk not in response_ids
    assert host_different not in response_ids

    # Test unescaped asterisk - should match both version*1.0 and version.1.0 (wildcard)
    url_wildcard = build_hosts_url(query="?filter[system_profile][insights_client_version]=version*1.0")
    response_status, response_data = api_get(url_wildcard)
    assert response_status == 200
    response_ids = [result["id"] for result in response_data["results"]]
    assert host_literal_asterisk in response_ids
    assert host_no_asterisk in response_ids
    assert host_different not in response_ids
