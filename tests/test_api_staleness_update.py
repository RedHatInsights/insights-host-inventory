import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from tests.helpers.api_utils import _INPUT_DATA as _DEFAULT_STALENESS_TRIPLE
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import run_rbac_test

_INPUT_DATA = {"conventional_time_to_stale": 99}

_CUSTOM_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 5000,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 5000,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 5000,
}

# Within 1h of system defaults
_NEAR_DEFAULT_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 100,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 100,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 100,
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


def test_patch_staleness_near_default_deletes_custom(api_patch, db_create_staleness_culling, db_get_staleness_culling):
    db_create_staleness_culling(
        conventional_time_to_stale=_CUSTOM_STALENESS["conventional_time_to_stale"],
        conventional_time_to_stale_warning=_CUSTOM_STALENESS["conventional_time_to_stale_warning"],
        conventional_time_to_delete=_CUSTOM_STALENESS["conventional_time_to_delete"],
    )
    response_status, response_data = api_patch(build_staleness_url(), host_data=_NEAR_DEFAULT_STALENESS)
    assert_response_status(response_status, 200)
    assert response_data["id"] == "system_default"
    org_id = response_data["org_id"]
    assert db_get_staleness_culling(org_id) is None


def test_patch_staleness_at_defaults_without_custom_returns_200(api_patch, db_get_staleness_culling):
    response_status, response_data = api_patch(build_staleness_url(), host_data=_DEFAULT_STALENESS_TRIPLE)
    assert_response_status(response_status, 200)
    assert response_data["id"] == "system_default"
    assert db_get_staleness_culling(response_data["org_id"]) is None
