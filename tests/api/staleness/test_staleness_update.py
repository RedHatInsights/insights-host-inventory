import pytest

from tests.helpers.api_utils import _INPUT_DATA as _DEFAULT_STALENESS_TRIPLE
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.staleness_test_constants import AT_EXACTLY_ONE_HOUR
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.staleness_test_constants import JUST_UNDER_ONE_HOUR
from tests.helpers.staleness_test_constants import assert_staleness_row_matches_triple
from tests.helpers.test_utils import USER_IDENTITY

_INPUT_DATA = {"conventional_time_to_stale": 99}


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


def test_patch_staleness_at_defaults_without_custom_returns_404(api_patch):
    """No custom row: PATCH does not update anything and returns 404 (even for default-equivalent payload)."""
    response_status, _ = api_patch(build_staleness_url(), host_data=_DEFAULT_STALENESS_TRIPLE)
    assert_response_status(response_status, 404)


def test_patch_staleness_just_under_one_hour_without_custom_returns_404(api_patch, db_get_staleness_culling):
    """Near-default-equivalent payload does not turn PATCH into 200 when there is no custom row."""
    response_status, _ = api_patch(build_staleness_url(), host_data=JUST_UNDER_ONE_HOUR)
    assert_response_status(response_status, 404)
    assert db_get_staleness_culling(USER_IDENTITY["org_id"]) is None


def test_patch_staleness_just_under_one_hour_deletes_custom(
    api_patch, db_create_staleness_culling, db_get_staleness_culling
):
    """All three fields +3599s from defaults (strictly < 1h) removes the custom row."""
    db_create_staleness_culling(**CUSTOM_STALENESS)
    response_status, response_data = api_patch(build_staleness_url(), host_data=JUST_UNDER_ONE_HOUR)
    assert_response_status(response_status, 200)
    assert response_data["id"] == "system_default"
    assert db_get_staleness_culling(response_data["org_id"]) is None


def test_patch_staleness_at_exactly_one_hour_keeps_custom(
    api_patch, db_create_staleness_culling, db_get_staleness_culling
):
    """All three fields exactly +3600s from defaults should keep a custom row (not default-equivalent)."""
    db_create_staleness_culling(**CUSTOM_STALENESS)
    response_status, response_data = api_patch(build_staleness_url(), host_data=AT_EXACTLY_ONE_HOUR)
    assert_response_status(response_status, 200)
    assert response_data["id"] != "system_default"
    row = db_get_staleness_culling(response_data["org_id"])
    assert row is not None
    assert_staleness_row_matches_triple(row, AT_EXACTLY_ONE_HOUR)
