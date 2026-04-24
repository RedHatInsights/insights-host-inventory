import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from lib.staleness import NEAR_DEFAULT_THRESHOLD_SECONDS
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.test_utils import USER_IDENTITY

_INPUT_DATA = {"conventional_time_to_stale": 99}

# A PATCH body that, when merged with the full defaults, results in near-default values.
_NEAR_DEFAULT_PATCH_DATA = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


def test_update_existing_record(api_patch, db_create_staleness_culling):
    saved_staleness = db_create_staleness_culling(conventional_time_to_stale=1)

    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data=_INPUT_DATA)
    assert_response_status(response_status, 200)
    assert saved_staleness.conventional_time_to_stale == 99


def test_update_non_existing_record(api_patch):
    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data=_INPUT_DATA)
    assert_response_status(response_status, 404)


def test_update_with_wrong_data(api_patch):
    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data={"conventional_time_to_stale": "9999"})
    assert_response_status(response_status, 400)


@pytest.mark.usefixtures("enable_rbac")
def test_update_staleness_rbac_allowed(subtests, mocker, api_patch, db_create_staleness_culling):
    db_create_staleness_culling(conventional_time_to_stale=1)
    url = build_staleness_url()
    run_rbac_test(subtests, mocker, api_patch, STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES, 200, [url, _INPUT_DATA])


@pytest.mark.usefixtures("enable_rbac")
def test_update_staleness_rbac_denied(subtests, mocker, api_patch, db_create_staleness_culling):
    db_create_staleness_culling(conventional_time_to_stale=1)
    url = build_staleness_url()
    run_rbac_test(subtests, mocker, api_patch, STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES, 403, [url, _INPUT_DATA])


def test_update_to_near_default_deletes_record(api_patch, db_create_staleness_culling, db_get_staleness_culling):
    """PATCHing to near-default values should delete the custom record and return 204."""
    db_create_staleness_culling(conventional_time_to_stale=1)
    org_id = USER_IDENTITY["org_id"]
    assert db_get_staleness_culling(org_id) is not None

    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data=_NEAR_DEFAULT_PATCH_DATA)
    assert_response_status(response_status, 204)

    assert db_get_staleness_culling(org_id) is None, "Record should be deleted after near-default PATCH"


def test_update_to_near_default_no_existing_record_returns_404(api_patch):
    """PATCHing to near-default values when no record exists should return 404."""
    url = build_staleness_url()
    response_status, _ = api_patch(url, host_data=_NEAR_DEFAULT_PATCH_DATA)
    assert_response_status(response_status, 404)
