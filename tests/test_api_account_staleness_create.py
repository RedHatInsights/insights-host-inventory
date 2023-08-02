from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_account_staleness_url


def test_create_staleness(api_post, subtests):
    url = build_account_staleness_url()
    response_status, response_data = api_post(url, host_data=None)
    assert_response_status(response_status, 201)
