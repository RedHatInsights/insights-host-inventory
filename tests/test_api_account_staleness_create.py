from tests.helpers.api_utils import ACCOUNT_STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import ACCOUNT_STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response

_INPUT_DATA = {
    "conventional_staleness_delta": "1",
    "conventional_stale_warning_delta": "7",
    "conventional_culling_delta": "14",
    "immutable_staleness_delta": "7",
    "immutable_stale_warning_delta": "120",
    "immutable_culling_delta": "120",
}


def _days_to_seconds(n_days):
    factor = 86400
    return str(n_days * factor)


def test_create_staleness(api_create_account_staleness, db_get_account_staleness_culling):
    response_status, response_data = api_create_account_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_account_staleness_culling(saved_org_id)

    assert saved_data.conventional_staleness_delta == _INPUT_DATA["conventional_staleness_delta"]
    assert saved_data.immutable_culling_delta == _INPUT_DATA["immutable_culling_delta"]
    assert saved_data.conventional_culling_delta == _INPUT_DATA["conventional_culling_delta"]
    assert saved_data.immutable_staleness_delta == _INPUT_DATA["immutable_staleness_delta"]
    assert saved_data.immutable_stale_warning_delta == _INPUT_DATA["immutable_stale_warning_delta"]
    assert saved_data.immutable_culling_delta == _INPUT_DATA["immutable_culling_delta"]


def test_create_staleness_with_only_one_data(api_create_account_staleness, db_get_account_staleness_culling):
    input_data = {
        "conventional_staleness_delta": "1",
    }
    response_status, response_data = api_create_account_staleness(input_data)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_account_staleness_culling(saved_org_id)

    assert saved_data.conventional_staleness_delta == input_data["conventional_staleness_delta"]
    assert saved_data.conventional_stale_warning_delta == _days_to_seconds(7)
    assert saved_data.conventional_culling_delta == _days_to_seconds(14)
    assert saved_data.immutable_staleness_delta == _days_to_seconds(2)
    assert saved_data.immutable_stale_warning_delta == _days_to_seconds(120)
    assert saved_data.immutable_culling_delta == _days_to_seconds(180)


def test_create_same_staleness(api_create_account_staleness):
    response_status, response_data = api_create_account_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)

    response_status, response_data = api_create_account_staleness(_INPUT_DATA)
    assert_response_status(response_status, 400)


def test_create_staleness_with_wrong_input(api_create_account_staleness):
    input_data = {
        "test_wrong_payload_data": "1",
    }
    response_status, response_data = api_create_account_staleness(input_data)
    assert_response_status(response_status, 400)

    # test  only positive number
    input_data = {
        "immutable_staleness_delta": "-1",
    }
    response_status, response_data = api_create_account_staleness(input_data)
    assert_response_status(response_status, 400)


def test_create_staleness_rbac_allowed(
    subtests, mocker, api_create_account_staleness, db_get_account_staleness_culling, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in ACCOUNT_STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_account_staleness(_INPUT_DATA)

            assert_response_status(response_status, 201)


def test_create_staleness_rbac_denied(
    subtests, mocker, api_create_account_staleness, db_get_account_staleness_culling, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in ACCOUNT_STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_account_staleness(_INPUT_DATA)

            assert_response_status(response_status, 403)
