from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import build_sys_default_staleness_url


def test_get_default_staleness(api_get):
    url = build_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    expected_result = {
        "conventional_time_to_stale": 104400,
        "conventional_time_to_stale_warning": 604800,
        "conventional_time_to_delete": 1209600,
        "immutable_time_to_stale": 172800,
        "immutable_time_to_stale_warning": 15552000,
        "immutable_time_to_delete": 63072000,
    }
    assert response_data["conventional_time_to_stale"] == expected_result["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == expected_result["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == expected_result["conventional_time_to_delete"]
    assert response_data["immutable_time_to_stale"] == expected_result["immutable_time_to_stale"]
    assert response_data["immutable_time_to_stale_warning"] == expected_result["immutable_time_to_stale_warning"]
    assert response_data["immutable_time_to_delete"] == expected_result["immutable_time_to_delete"]


def test_get_custom_staleness(api_create_staleness, api_get):
    created_response_status, _ = api_create_staleness(_INPUT_DATA)
    url = build_staleness_url()
    response_status, response_data = api_get(url)
    assert response_data["conventional_time_to_stale"] == _INPUT_DATA["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == _INPUT_DATA["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == _INPUT_DATA["conventional_time_to_delete"]
    assert response_data["immutable_time_to_stale"] == _INPUT_DATA["immutable_time_to_stale"]
    assert response_data["immutable_time_to_stale_warning"] == _INPUT_DATA["immutable_time_to_stale_warning"]
    assert response_data["immutable_time_to_delete"] == _INPUT_DATA["immutable_time_to_delete"]
    assert_response_status(response_status, 200)


def test_get_sys_default_staleness(api_get):
    url = build_sys_default_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    expected_result = {
        "conventional_time_to_stale": 104400,
        "conventional_time_to_stale_warning": 604800,
        "conventional_time_to_delete": 1209600,
        "immutable_time_to_stale": 172800,
        "immutable_time_to_stale_warning": 15552000,
        "immutable_time_to_delete": 63072000,
    }
    assert response_data["conventional_time_to_stale"] == expected_result["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == expected_result["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == expected_result["conventional_time_to_delete"]
    assert response_data["immutable_time_to_stale"] == expected_result["immutable_time_to_stale"]
    assert response_data["immutable_time_to_stale_warning"] == expected_result["immutable_time_to_stale_warning"]
    assert response_data["immutable_time_to_delete"] == expected_result["immutable_time_to_delete"]
