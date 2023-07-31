from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_account_staleness_url


def test_reset_staleness(api_patch, subtests):
    url = build_account_staleness_url(path="/reset")
    response_status, response_data = api_patch(url, host_data=None)
    assert_response_status(response_status, 200)
