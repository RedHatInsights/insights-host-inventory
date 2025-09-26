import pytest

from tests.helpers.api_utils import _INPUT_DATA
from tests.helpers.api_utils import STALENESS_READ_ALLOWED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import STALENESS_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import build_sys_default_staleness_url
from tests.helpers.api_utils import create_mock_rbac_response


def test_get_default_staleness(api_get):
    url = build_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    assert response_data["conventional_time_to_stale"] == _INPUT_DATA["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == _INPUT_DATA["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == _INPUT_DATA["conventional_time_to_delete"]


def test_get_custom_staleness(api_get):
    url = build_sys_default_staleness_url()
    response_status, response_data = api_get(url)
    assert response_data["conventional_time_to_stale"] == _INPUT_DATA["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == _INPUT_DATA["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == _INPUT_DATA["conventional_time_to_delete"]
    assert_response_status(response_status, 200)


def test_get_sys_default_staleness(api_get):
    url = build_sys_default_staleness_url()
    response_status, response_data = api_get(url)
    assert_response_status(response_status, 200)
    assert response_data["conventional_time_to_stale"] == _INPUT_DATA["conventional_time_to_stale"]
    assert response_data["conventional_time_to_stale_warning"] == _INPUT_DATA["conventional_time_to_stale_warning"]
    assert response_data["conventional_time_to_delete"] == _INPUT_DATA["conventional_time_to_delete"]


@pytest.mark.usefixtures("enable_rbac")
def test_get_staleness_rbac_denied(subtests, mocker, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    url = build_sys_default_staleness_url()

    for response_file in STALENESS_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)
        if mock_rbac_response and len(mock_rbac_response[0]["resourceDefinitions"]) > 0:
            mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [None]

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_get(url)

            assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_get_staleness_rbac_allowed(subtests, mocker, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    url = build_sys_default_staleness_url()

    for response_file in STALENESS_READ_ALLOWED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_get(url)

            assert_response_status(response_status, 200)
