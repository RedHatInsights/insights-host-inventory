from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import build_sys_default_staleness_url


def test_get_default_staleness(api_get):
    url = build_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    expected_result = {
        "conventional_staleness_delta": 86400,
        "conventional_stale_warning_delta": 604800,
        "conventional_culling_delta": 1209600,
        "immutable_staleness_delta": 172800,
        "immutable_stale_warning_delta": 10368000,
        "immutable_culling_delta": 15552000,
    }
    assert response_data["conventional_staleness_delta"] == expected_result["conventional_staleness_delta"]
    assert response_data["conventional_stale_warning_delta"] == expected_result["conventional_stale_warning_delta"]
    assert response_data["conventional_culling_delta"] == expected_result["conventional_culling_delta"]
    assert response_data["immutable_staleness_delta"] == expected_result["immutable_staleness_delta"]
    assert response_data["immutable_stale_warning_delta"] == expected_result["immutable_stale_warning_delta"]
    assert response_data["immutable_culling_delta"] == expected_result["immutable_culling_delta"]


def test_get_custom_staleness(api_create_staleness, api_get):
    created_response_status, _ = api_create_staleness(_INPUT_DATA)
    url = build_staleness_url()
    response_status, response_data = api_get(url)
    assert response_data["conventional_staleness_delta"] == _INPUT_DATA["conventional_staleness_delta"]
    assert response_data["conventional_stale_warning_delta"] == _INPUT_DATA["conventional_stale_warning_delta"]
    assert response_data["conventional_culling_delta"] == _INPUT_DATA["conventional_culling_delta"]
    assert response_data["immutable_staleness_delta"] == _INPUT_DATA["immutable_staleness_delta"]
    assert response_data["immutable_stale_warning_delta"] == _INPUT_DATA["immutable_stale_warning_delta"]
    assert response_data["immutable_culling_delta"] == _INPUT_DATA["immutable_culling_delta"]
    assert_response_status(response_status, 200)


def test_get_sys_default_staleness(api_get):
    url = build_sys_default_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    expected_result = {
        "conventional_staleness_delta": 86400,
        "conventional_stale_warning_delta": 604800,
        "conventional_culling_delta": 1209600,
        "immutable_staleness_delta": 172800,
        "immutable_stale_warning_delta": 10368000,
        "immutable_culling_delta": 15552000,
    }
    assert response_data["conventional_staleness_delta"] == expected_result["conventional_staleness_delta"]
    assert response_data["conventional_stale_warning_delta"] == expected_result["conventional_stale_warning_delta"]
    assert response_data["conventional_culling_delta"] == expected_result["conventional_culling_delta"]
    assert response_data["immutable_staleness_delta"] == expected_result["immutable_staleness_delta"]
    assert response_data["immutable_stale_warning_delta"] == expected_result["immutable_stale_warning_delta"]
    assert response_data["immutable_culling_delta"] == expected_result["immutable_culling_delta"]
