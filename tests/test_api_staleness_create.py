import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import run_rbac_test
from tests.helpers.staleness_test_constants import AT_EXACTLY_ONE_HOUR
from tests.helpers.staleness_test_constants import BEYOND_TOLERANCE_STALENESS
from tests.helpers.staleness_test_constants import CUSTOM_STALENESS
from tests.helpers.staleness_test_constants import JUST_UNDER_ONE_HOUR


def test_create_staleness(api_create_staleness, db_get_staleness_culling):
    response_status, response_data = api_create_staleness(CUSTOM_STALENESS)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data is not None
    assert saved_data.conventional_time_to_stale == CUSTOM_STALENESS["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == CUSTOM_STALENESS["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == CUSTOM_STALENESS["conventional_time_to_delete"]


def test_create_staleness_at_defaults_does_not_persist_row(api_create_staleness, db_get_staleness_culling):
    """POST with default triple should not add a custom staleness row (RHINENG-20674)."""
    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)
    assert response_data["id"] == "system_default"
    org_id = response_data["org_id"]
    assert db_get_staleness_culling(org_id) is None


def test_create_staleness_just_under_one_hour_no_row(api_create_staleness, db_get_staleness_culling):
    """POST with each field +3599s (strictly under 1h) does not insert a custom row."""
    response_status, response_data = api_create_staleness(JUST_UNDER_ONE_HOUR)
    assert_response_status(response_status, 201)
    assert response_data["id"] == "system_default"
    assert db_get_staleness_culling(response_data["org_id"]) is None


def test_create_staleness_at_exactly_one_hour_creates_row(api_create_staleness, db_get_staleness_culling):
    """POST with each field offset by exactly +3600s is not default-equivalent; row is created."""
    response_status, response_data = api_create_staleness(AT_EXACTLY_ONE_HOUR)
    assert_response_status(response_status, 201)
    assert response_data["id"] != "system_default"
    row = db_get_staleness_culling(response_data["org_id"])
    assert row is not None
    assert row.conventional_time_to_stale == AT_EXACTLY_ONE_HOUR["conventional_time_to_stale"]
    assert row.conventional_time_to_stale_warning == AT_EXACTLY_ONE_HOUR["conventional_time_to_stale_warning"]
    assert row.conventional_time_to_delete == AT_EXACTLY_ONE_HOUR["conventional_time_to_delete"]


def test_create_staleness_beyond_one_hour_creates_row(api_create_staleness, db_get_staleness_culling):
    """POST with each field offset by +3601s from defaults persists custom staleness."""
    response_status, response_data = api_create_staleness(BEYOND_TOLERANCE_STALENESS)
    assert_response_status(response_status, 201)
    assert response_data["id"] != "system_default"
    row = db_get_staleness_culling(response_data["org_id"])
    assert row is not None
    assert row.conventional_time_to_stale == BEYOND_TOLERANCE_STALENESS["conventional_time_to_stale"]
    assert row.conventional_time_to_stale_warning == BEYOND_TOLERANCE_STALENESS["conventional_time_to_stale_warning"]
    assert row.conventional_time_to_delete == BEYOND_TOLERANCE_STALENESS["conventional_time_to_delete"]


def test_create_staleness_at_defaults_replaces_custom_row(
    api_create_staleness, db_create_staleness_culling, db_get_staleness_culling
):
    """POST near-defaults when a custom row exists should delete the custom record (RHINENG-20674)."""
    db_create_staleness_culling(
        conventional_time_to_stale=CUSTOM_STALENESS["conventional_time_to_stale"],
        conventional_time_to_stale_warning=CUSTOM_STALENESS["conventional_time_to_stale_warning"],
        conventional_time_to_delete=CUSTOM_STALENESS["conventional_time_to_delete"],
    )
    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)
    assert response_data["id"] == "system_default"
    assert db_get_staleness_culling(response_data["org_id"]) is None


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
    response_status, response_data = api_create_staleness(CUSTOM_STALENESS)
    assert_response_status(response_status, 201)

    response_status, response_data = api_create_staleness(CUSTOM_STALENESS)
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
        subtests, mocker, api_create_staleness, STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES, 201, [_INPUT_DATA]
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
    "immutables",
    (
        {
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 1,
            "immutable_time_to_delete": 63072000,
        },
        {
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 1,
        },
        {
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 64000000,
            "immutable_time_to_delete": 63072000,
        },
    ),
)
def test_create_staleness_ignores_immutable_fields(api_create_staleness, db_get_staleness_culling, immutables):
    """Test that immutable staleness fields are ignored even when they have invalid values."""
    input_data = {**CUSTOM_STALENESS, **immutables}
    response_status, response_data = api_create_staleness(input_data)
    # Should succeed even with invalid immutable field values, as they are filtered out
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    # Verify only conventional fields were saved, immutable fields were ignored
    assert saved_data.conventional_time_to_stale == CUSTOM_STALENESS["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == CUSTOM_STALENESS["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == CUSTOM_STALENESS["conventional_time_to_delete"]
