import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response


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
    assert saved_data.conventional_time_to_stale_warning == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert saved_data.conventional_time_to_delete == CONVENTIONAL_TIME_TO_DELETE_SECONDS


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
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 1,
            "immutable_time_to_delete": 63072000,
        },
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
            "immutable_time_to_stale": 172800,
            "immutable_time_to_stale_warning": 15552000,
            "immutable_time_to_delete": 1,
        },
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
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
    assert saved_data.conventional_time_to_stale == input_data["conventional_time_to_stale"]
    assert saved_data.conventional_time_to_stale_warning == input_data["conventional_time_to_stale_warning"]
    assert saved_data.conventional_time_to_delete == input_data["conventional_time_to_delete"]


@pytest.mark.parametrize(
    "input_data",
    (
        # Exactly at defaults
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        },
        # Within tolerance (60 seconds) of defaults
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 30,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 30,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 60,
        },
        # At the edge of tolerance
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 60,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 60,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        },
        # Only one field within tolerance
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 10,
        },
    ),
)
def test_create_staleness_with_values_close_to_defaults(api_create_staleness, db_get_staleness_culling, input_data):
    """Test that creating staleness with values close to defaults returns 200 and doesn't create a DB record."""
    response_status, response_data = api_create_staleness(input_data)
    # Should return 200 (not 201) since no custom staleness was created
    assert_response_status(response_status, 200)

    # Verify the response contains system defaults
    assert response_data["conventional_time_to_stale"] == CONVENTIONAL_TIME_TO_STALE_SECONDS
    assert response_data["conventional_time_to_stale_warning"] == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert response_data["conventional_time_to_delete"] == CONVENTIONAL_TIME_TO_DELETE_SECONDS

    # Verify no custom staleness record was created in the database
    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)
    assert saved_data is None


def test_create_staleness_just_outside_tolerance(api_create_staleness, db_get_staleness_culling):
    """Test that creating staleness just outside tolerance does create a DB record."""
    input_data = {
        "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 61,  # Just outside 60 second tolerance
        "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
        "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
    }
    response_status, response_data = api_create_staleness(input_data)
    # Should return 201 since this is outside tolerance
    assert_response_status(response_status, 201)

    # Verify custom staleness record was created in the database
    saved_org_id = response_data["org_id"]
    saved_data = db_get_staleness_culling(saved_org_id)
    assert saved_data is not None
    assert saved_data.conventional_time_to_stale == input_data["conventional_time_to_stale"]
