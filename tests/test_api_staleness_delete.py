from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES


def test_delete_existing_staleness(db_create_staleness_culling, api_delete_staleness, db_get_staleness_culling):
    saved_staleness = db_create_staleness_culling(
        conventional_time_to_stale=1,
        conventional_time_to_stale_warning=7,
        conventional_time_to_delete=14,
        immutable_time_to_stale=7,
        immutable_time_to_stale_warning=120,
        immutable_time_to_delete=120,
    )

    response_status, response_data = api_delete_staleness()
    assert_response_status(response_status, 204)

    # checking if the record was really removed
    deleted_staleness = db_get_staleness_culling(saved_staleness.org_id)
    assert deleted_staleness is None


def test_delete_non_existing_staleness(api_delete_staleness):
    response_status, response_data = api_delete_staleness()
    assert_response_status(response_status, 404)


def test_delete_staleness_rbac_allowed(
    subtests, mocker, api_delete_staleness, db_create_staleness_culling, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            db_create_staleness_culling(
                conventional_time_to_stale=1,
                conventional_time_to_stale_warning=7,
                conventional_time_to_delete=14,
                immutable_time_to_stale=7,
                immutable_time_to_stale_warning=120,
                immutable_time_to_delete=120,
            )

            response_status, _ = api_delete_staleness()

            assert_response_status(response_status, 204)


def test_delete_staleness_rbac_denied(subtests, mocker, api_delete_staleness, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_delete_staleness()

            assert_response_status(response_status, 403)
