from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_account_staleness_url


def test_get_staleness(api_get, subtests):
    url = build_account_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
