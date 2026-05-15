import pytest

from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import run_rbac_test


def test_delete_existing_staleness(db_create_staleness_culling, api_delete_staleness, db_get_staleness_culling):
    saved_staleness = db_create_staleness_culling(
        conventional_time_to_stale=1,
        conventional_time_to_stale_warning=7,
        conventional_time_to_delete=30,
    )
    org_id = saved_staleness.org_id

    response_status, _ = api_delete_staleness()
    assert_response_status(response_status, 204)

    # checking if the record was really removed
    deleted_staleness = db_get_staleness_culling(org_id)
    assert deleted_staleness is None


def test_delete_non_existing_staleness(api_delete_staleness):
    response_status, _ = api_delete_staleness()
    assert_response_status(response_status, 404)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_staleness_rbac_allowed(subtests, mocker, api_delete_staleness, db_create_staleness_culling):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    for response_file in STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        with subtests.test():
            get_rbac_permissions_mock.return_value = create_mock_rbac_response(response_file)
            db_create_staleness_culling(
                conventional_time_to_stale=1,
                conventional_time_to_stale_warning=7,
                conventional_time_to_delete=30,
            )
            response_status, _ = api_delete_staleness()
            assert_response_status(response_status, 204)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_staleness_rbac_denied(subtests, mocker, api_delete_staleness):
    run_rbac_test(subtests, mocker, api_delete_staleness, STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_staleness_rbac_denied_granular(subtests, mocker, api_delete_staleness):
    run_rbac_test(
        subtests,
        mocker,
        api_delete_staleness,
        ("tests/helpers/rbac-mock-data/inv-staleness-hosts-write-granular.json",),
        403,
    )
