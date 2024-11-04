from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_mock_rbac_response

_INPUT_DATA = {"conventional_time_to_stale": 99}


def test_update_existing_record(api_patch, db_create_staleness_culling):
    saved_staleness = db_create_staleness_culling(conventional_time_to_stale=1)

    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data=_INPUT_DATA)
    assert_response_status(response_status, 200)
    assert saved_staleness.conventional_time_to_stale == 99


def test_update_non_existing_record(api_patch):
    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data=_INPUT_DATA)
    assert_response_status(response_status, 404)


def test_update_with_wrong_data(api_patch):
    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data={"conventional_time_to_stale": "9999"})
    assert_response_status(response_status, 400)


def test_update_staleness_rbac_allowed(subtests, mocker, api_patch, db_create_staleness_culling, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    db_create_staleness_culling(conventional_time_to_stale=1)

    for response_file in STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            url = build_staleness_url()
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_patch(url, _INPUT_DATA)

            assert_response_status(response_status, 200)


def test_update_staleness_rbac_denied(subtests, mocker, api_patch, db_create_staleness_culling, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    db_create_staleness_culling(conventional_time_to_stale=1)

    for response_file in STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            url = build_staleness_url()
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_patch(url, _INPUT_DATA)

            assert_response_status(response_status, 403)
