
import pytest

from tests.helpers.api_utils import build_hosts_url


@pytest.mark.parametrize(
    "filter_value, expected_match",
    [
        # Test case 1: Escaped asterisk should match literal '*'
        ("test1\\*test2", True),
        # Test case 2: Unescaped asterisk should act as a wildcard
        ("test1*test2", True),
        # Test case 3: Wildcard at the end
        ("test1*", True),
        # Test case 4: Escaped backslash should match literal '\'
        ("data\\\\center", True),
        # Test case 5: Combination of escaped and unescaped wildcards
        ("test1\\*t*2", True),
        # Test case 6: Should not match (no wildcard)
        ("test1_test2", False),
        # Test case 7: URL encoded value with literal '*' and '\'
        # The value 'test1*test2\\test3' is what the app sees after decoding
        ("test1*test2\\test3", True),
    ],
)
def test_sp_filter_wildcard_escaping(db_create_host, api_get, filter_value, expected_match):
    # Host with system profile data containing special characters
    host_data = {
        "system_profile_facts": {
            "os_release": "test1*test2",
            "data_center": "data\\center",
            "complex_field": "test1*test2\\test3",
        }
    }
    host = db_create_host(extra_data=host_data)

    # Determine which field to filter on based on the test case
    if "data" in filter_value:
        field = "data_center"
    elif "test3" in filter_value:
        field = "complex_field"
    else:
        field = "os_release"

    url = build_hosts_url(query=f"?filter[system_profile][{field}]={filter_value}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    if expected_match:
        assert len(response_data["results"]) == 1
        assert response_data["results"][0]["id"] == str(host.id)
    else:
        assert len(response_data["results"]) == 0
