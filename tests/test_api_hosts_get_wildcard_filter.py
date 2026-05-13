
import pytest

from tests.helpers.api_utils import build_hosts_url


def test_query_sp_filters_with_wildcard_and_escape_chars(db_create_host, api_get):
    # Create host with a system profile value containing '*' and '\'
    match_sp_data = {
        "system_profile_facts": {
            "os_release": "test1*test2\\test3",
            "bios_vendor": "some_vendor*",
        }
    }
    match_host_id = str(db_create_host(extra_data=match_sp_data).id)

    # Test 1: URL-encoded '*' and '\' should match literally
    # The filter value "test1%2Atest2%5Ctest3" gets decoded to "test1*test2\test3" by the web framework
    # The application logic should treat this as a literal search, not a wildcard search
    url = build_hosts_url(query="?filter[system_profile][os_release]=test1*test2\\test3")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == 1
    assert response_data["results"][0]["id"] == match_host_id

    # Test 2: Unencoded '*' should still act as a wildcard
    url_wildcard = build_hosts_url(query="?filter[system_profile][os_release]=test1*")
    response_status_wildcard, response_data_wildcard = api_get(url_wildcard)

    assert response_status_wildcard == 200
    assert len(response_data_wildcard["results"]) == 1
    assert response_data_wildcard["results"][0]["id"] == match_host_id

    # Test 3: Test another wildcard case
    url_wildcard_2 = build_hosts_url(query="?filter[system_profile][bios_vendor]=some_vendor*")
    response_status_wildcard_2, response_data_wildcard_2 = api_get(url_wildcard_2)

    assert response_status_wildcard_2 == 200
    assert len(response_data_wildcard_2["results"]) == 1
    assert response_data_wildcard_2["results"][0]["id"] == match_host_id

    # Test 4: A value that should not match
    url_no_match = build_hosts_url(query="?filter[system_profile][os_release]=test1_test2_test3")
    response_status_no_match, response_data_no_match = api_get(url_no_match)

    assert response_status_no_match == 200
    assert len(response_data_no_match["results"]) == 0
