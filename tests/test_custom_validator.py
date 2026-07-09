from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_hosts_url


def test_valid_deep_object_query_params(api_get):
    # Valid deepObject query parameters should return 200 OK
    for query in (
        "?filter[system_profile][arch]=x86_64",
        "?filter[system_profile][arch][eq]=x86_64",
        "?filter[system_profile][operating_system][RHEL][version][eq]=8.4",
    ):
        url = build_hosts_url(query=query)
        status, _ = api_get(url)
        assert_response_status(status, 200)


def test_invalid_query_params(api_get):
    # Genuinely invalid query parameters should return 400 Bad Request
    for query in (
        "?invalid_param=123",
        "?filter[invalid_field]=123",
        "?filter[system_profile][invalid_field]=123",
        "?fields[system_profile]=invalid_field",
    ):
        url = build_hosts_url(query=query)
        status, response_data = api_get(url)
        assert_response_status(status, 400)
        # Verify that the response contains error details
        assert "detail" in response_data or "title" in response_data
