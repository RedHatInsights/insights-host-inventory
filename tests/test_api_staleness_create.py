import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import run_rbac_test

# Differs from system defaults by more than 1 hour so a custom DB row is created (RHINENG-20674).
_CUSTOM_STALENESS = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 5000,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS + 5000,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 5000,
}


def test_create_staleness(api_create_staleness, db_get_staleness_culling):
    response_status, response_data = api_create_staleness(_CUSTOM_STALENESS)
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    assert saved_data is not None
    assert saved_data.conventional_time_to_stale == _CUSTOM_STALENESS["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _CUSTOM_STALENESS["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == _CUSTOM_STALENESS["conventional_time_to_delete"]


def test_create_staleness_at_defaults_does_not_persist_row(api_create_staleness, db_get_staleness_culling):
    """POST with values within 1h of system defaults should not add a custom staleness row (RHINENG-20674)."""
    response_status, response_data = api_create_staleness(_INPUT_DATA)
    assert_response_status(response_status, 201)
    assert response_data["id"] == "system_default"
    org_id = response_data["org_id"]
    assert db_get_staleness_culling(org_id) is None


def test_create_staleness_at_defaults_replaces_custom_row(
    api_create_staleness, db_create_staleness_culling, db_get_staleness_culling
):
    """POST near-defaults when a custom row exists should delete the custom record (RHINENG-20674)."""
    db_create_staleness_culling(
        conventional_time_to_stale=_CUSTOM_STALENESS["conventional_time_to_stale"],
        conventional_time_to_stale_warning=_CUSTOM_STALENESS["conventional_time_to_stale_warning"],
        conventional_time_to_delete=_CUSTOM_STALENESS["conventional_time_to_delete"],
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
    response_status, response_data = api_create_staleness(_CUSTOM_STALENESS)
    assert_response_status(response_status, 201)

    response_status, response_data = api_create_staleness(_CUSTOM_STALENESS)
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
    input_data = {**_CUSTOM_STALENESS, **immutables}
    response_status, response_data = api_create_staleness(input_data)
    # Should succeed even with invalid immutable field values, as they are filtered out
    assert_response_status(response_status, 201)

    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)

    # Verify only conventional fields were saved, immutable fields were ignored
    assert saved_data.conventional_time_to_stale == _CUSTOM_STALENESS["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == _CUSTOM_STALENESS["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == _CUSTOM_STALENESS["conventional_time_to_delete"]
