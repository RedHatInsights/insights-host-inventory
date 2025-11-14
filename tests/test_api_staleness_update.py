import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from tests.helpers.api_utils import STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_mock_rbac_response

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
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    db_create_staleness_culling(conventional_time_to_stale=1)

    for response_file in STALENESS_WRITE_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            url = build_staleness_url()
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_patch(url, _INPUT_DATA)

            assert_response_status(response_status, 200)


@pytest.mark.usefixtures("enable_rbac")
def test_update_staleness_rbac_denied(subtests, mocker, api_patch, db_create_staleness_culling):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    db_create_staleness_culling(conventional_time_to_stale=1)

    for response_file in STALENESS_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            url = build_staleness_url()
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_patch(url, _INPUT_DATA)

            assert_response_status(response_status, 403)


@pytest.mark.parametrize(
    "update_data",
    (
        # Update to exactly defaults
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
        },
        # Update within tolerance (60 seconds) of defaults
        {
            "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 30,
            "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS - 30,
            "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS + 60,
        },
    ),
)
def test_update_staleness_to_values_close_to_defaults(
    api_patch, db_create_staleness_culling, db_get_staleness_culling, update_data
):
    """Test that updating staleness to values close to defaults removes custom config and returns defaults."""
    # Create a custom staleness configuration
    saved_staleness = db_create_staleness_culling(
        conventional_time_to_stale=100,
        conventional_time_to_stale_warning=200,
        conventional_time_to_delete=300,
    )

    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data=update_data)
    assert_response_status(response_status, 200)

    # Verify the response contains system defaults (not the updated values)
    assert response_data["conventional_time_to_stale"] == CONVENTIONAL_TIME_TO_STALE_SECONDS
    assert response_data["conventional_time_to_stale_warning"] == CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert response_data["conventional_time_to_delete"] == CONVENTIONAL_TIME_TO_DELETE_SECONDS

    # Verify the custom staleness record was removed from the database
    deleted_staleness = db_get_staleness_culling(saved_staleness.org_id)
    assert deleted_staleness is None


def test_update_staleness_just_outside_tolerance(api_patch, db_create_staleness_culling, db_get_staleness_culling):
    """Test that updating staleness just outside tolerance keeps the custom config."""
    # Create a custom staleness configuration with higher values so update won't fail validation
    saved_staleness = db_create_staleness_culling(
        conventional_time_to_stale=100000,
        conventional_time_to_stale_warning=200000,
        conventional_time_to_delete=300000,
    )

    update_data = {
        "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS + 61,  # Just outside 60 second tolerance
    }
    url = build_staleness_url()
    response_status, response_data = api_patch(url, host_data=update_data)
    assert_response_status(response_status, 200)

    # Verify the custom staleness record still exists and was updated
    updated_staleness = db_get_staleness_culling(saved_staleness.org_id)
    assert updated_staleness is not None
    assert updated_staleness.conventional_time_to_stale == update_data["conventional_time_to_stale"]
    # Other fields should remain unchanged
    assert updated_staleness.conventional_time_to_stale_warning == 200000
    assert updated_staleness.conventional_time_to_delete == 300000
