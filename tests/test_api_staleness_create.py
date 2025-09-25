import pytest

from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response


def _days_to_seconds(n_days):
    factor = 86400
    return n_days * factor


def test_create_staleness(api_create_staleness, db_get_staleness_culling):
    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data.conventional_time_to_stale == _INPUT_DATA["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _INPUT_DATA["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == _INPUT_DATA["conventional_time_to_delete"]


def test_create_staleness_with_only_one_data(api_create_staleness, db_get_staleness_culling):
    input_data = {
        "conventional_time_to_stale": 1,
    }
    response_status, response_data = api_create_staleness(input_data)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data.conventional_time_to_stale == input_data["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _days_to_seconds(7)
    assert saved_data.conventional_time_to_delete == _days_to_seconds(14)


def test_create_same_staleness(api_create_staleness):
    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)

    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 400)


def test_create_staleness_with_wrong_input(api_create_staleness):
    input_data = {
        "test_wrong_payload_data": "1",
    }
    response_status, response_data = api_create_staleness(input_data)
    assert_response_status(response_status, 400)


@pytest.mark.usefixtures("enable_rbac")
def test_create_staleness_rbac_allowed(subtests, mocker, api_create_staleness):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_staleness(_INPUT_DATA)

            assert_response_status(response_status, 201)


@pytest.mark.usefixtures("enable_rbac")
def test_create_staleness_rbac_denied(subtests, mocker, api_create_staleness):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_staleness(_INPUT_DATA)

            assert_response_status(response_status, 403)


@pytest.mark.parametrize(
    "input_data",
    (
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 1,
            "conventional_time_to_delete": 1209600,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 63072000,
        },
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 604800,
            "conventional_time_to_delete": 1,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 63072000,
        },
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 2000000,
            "conventional_time_to_delete": 1209600,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 63072000,
        },
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 604800,
            "conventional_time_to_delete": 1209600,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 1,
            "immutable_time_to_delete": 63072000,
        },
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 604800,
            "conventional_time_to_delete": 1209600,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 1,
        },
        {
            "conventional_time_to_stale": 104400,
            "conventional_time_to_stale_warning": 604800,
            "conventional_time_to_delete": 1209600,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 64000000,
            "immutable_time_to_delete": 63072000,
        },
    ),
)
def test_create_improper_staleness(api_create_staleness, input_data):
    response_status, _ = api_create_staleness(input_data)
    assert_response_status(response_status, 400)
