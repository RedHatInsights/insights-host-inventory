import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from lib.staleness import NEAR_DEFAULT_THRESHOLD_SECONDS
from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.test_utils import USER_IDENTITY

# Custom values well outside the near-default threshold (> 3600s from defaults).
_CUSTOM_INPUT_DATA = {
    "conventional_time_to_stale": 172800,  # 2 days (default: 29 h)
    "conventional_time_to_stale_warning": 432000,  # 5 days (default: 7 days)
    "conventional_time_to_delete": 1296000,  # 15 days (default: 30 days)
}

# Values within NEAR_DEFAULT_THRESHOLD_SECONDS of the defaults.
_NEAR_DEFAULT_INPUT_DATA = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + NEAR_DEFAULT_THRESHOLD_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


def test_create_staleness(api_create_staleness, db_get_staleness_culling):
    response_status, response_data = api_create_staleness(_CUSTOM_INPUT_DATA)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data.conventional_time_to_stale == _CUSTOM_INPUT_DATA["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _CUSTOM_INPUT_DATA["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == _CUSTOM_INPUT_DATA["conventional_time_to_delete"]


def test_create_near_default_staleness_returns_no_content(api_create_staleness, db_get_staleness_culling):
    """When all values are within one hour of the defaults no record should be stored."""
    response_status, _ = api_create_staleness(_NEAR_DEFAULT_INPUT_DATA)
    assert_response_status(response_status, 204)

    org_id = USER_IDENTITY["org_id"]
    assert db_get_staleness_culling(org_id) is None, "No DB record should be created for near-default data"


def test_create_exact_default_staleness_returns_no_content(api_create_staleness, db_get_staleness_culling):
    """Exact default values also trigger the near-default path and return 204."""
    response_status, _ = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 204)

    org_id = USER_IDENTITY["org_id"]
    assert db_get_staleness_culling(org_id) is None


def test_create_near_default_staleness_deletes_existing_record(
    api_create_staleness, db_create_staleness_culling, db_get_staleness_culling
):
    """If a custom record already exists and the new POST is near-default, the record is deleted."""
    db_create_staleness_culling(conventional_time_to_stale=1)
    org_id = USER_IDENTITY["org_id"]
    assert db_get_staleness_culling(org_id) is not None

    response_status, _ = api_create_staleness(_NEAR_DEFAULT_INPUT_DATA)
    assert_response_status(response_status, 204)

    assert db_get_staleness_culling(org_id) is None, "Existing record should be deleted"


def test_create_staleness_with_only_one_data(api_create_staleness, db_get_staleness_culling):
    input_data = {
        "conventional_time_to_stale": 1,
    }
    response_status, response_data = api_create_staleness(input_data)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data.conventional_time_to_stale == input_data["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert saved_data.conventional_time_to_delete == CONVENTIONAL_TIME_TO_DELETE_SECONDS


def test_create_same_staleness(api_create_staleness):
    response_status, _ = api_create_staleness(_CUSTOM_INPUT_DATA)
    assert_response_status(response_status, 201)

    response_status, _ = api_create_staleness(_CUSTOM_INPUT_DATA)
    assert_response_status(response_status, 400)


def test_create_staleness_with_wrong_input(api_create_staleness):
    input_data = {
        "test_wrong_payload_data": "1",
    }
    response_status, response_data = api_create_staleness(input_data)
    assert_response_status(response_status, 400)


@pytest.mark.usefixtures("enable_rbac")
def test_create_staleness_rbac_allowed(subtests, mocker, api_create_staleness):
    run_rbac_test(
        subtests, mocker, api_create_staleness, STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES, 201, [_CUSTOM_INPUT_DATA]
    )


@pytest.mark.usefixtures("enable_rbac")
def test_create_staleness_rbac_denied(subtests, mocker, api_create_staleness):
    run_rbac_test(
        subtests, mocker, api_create_staleness, STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES, 403, [_INPUT_DATA]
    )


@pytest.mark.parametrize(
    "input_data",
    (
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": 1,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        },
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": 1,
        },
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 1,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        },
    ),
)
def test_create_improper_staleness(api_create_staleness, input_data):
    """Test that invalid conventional staleness values are rejected."""
    response_status, _ = api_create_staleness(input_data)
    assert_response_status(response_status, 400)


@pytest.mark.parametrize(
    "input_data",
    (
        {
            **_CUSTOM_INPUT_DATA,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 1,
            "immutable_time_to_delete": 63072000,
        },
        {
            **_CUSTOM_INPUT_DATA,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 1,
        },
        {
            **_CUSTOM_INPUT_DATA,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 64000000,
            "immutable_time_to_delete": 63072000,
        },
    ),
)
def test_create_staleness_ignores_immutable_fields(api_create_staleness, db_get_staleness_culling, input_data):
    """Test that immutable staleness fields are ignored even when they have invalid values."""
    response_status, response_data = api_create_staleness(input_data)
    # Should succeed even with invalid immutable field values, as they are filtered out
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    # Verify only conventional fields were saved, immutable fields were ignored
    assert saved_data.conventional_time_to_stale == _CUSTOM_INPUT_DATA["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _CUSTOM_INPUT_DATA["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == _CUSTOM_INPUT_DATA["conventional_time_to_delete"]
