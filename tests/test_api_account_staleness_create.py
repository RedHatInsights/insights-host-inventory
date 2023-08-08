from lib.account_staleness import get_account_staleness_by_org_id
from tests.helpers.api_utils import assert_response_status


def test_create_staleness(api_create_account_staleness, event_producer, mocker):
    input_data = {
        "system_staleness_delta": "1",
        "system_stale_warning_delta": "7",
        "system_culling_delta": "14",
        "edge_staleness_delta": "7",
        "edge_stale_warning_delta": "120",
        "edge_culling_delta": "120",
    }
    response_status, response_data = api_create_account_staleness(input_data)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = get_account_staleness_by_org_id(saved_org_id)

    assert saved_data.conventional_staleness_delta == input_data["system_staleness_delta"]
    assert saved_data.conventional_stale_warning_delta == input_data["system_stale_warning_delta"]
    assert saved_data.conventional_culling_delta == input_data["system_culling_delta"]
    assert saved_data.immutable_staleness_delta == input_data["edge_staleness_delta"]
    assert saved_data.immutable_stale_warning_delta == input_data["edge_stale_warning_delta"]
    assert saved_data.immutable_culling_delta == input_data["edge_culling_delta"]


def test_create_staleness_with_missing_input(api_create_account_staleness, event_producer, mocker):
    input_data = {
        "test_system_staleness_delta": "1",
    }
    response_status, response_data = api_create_account_staleness(input_data)
    assert_response_status(response_status, 400)
