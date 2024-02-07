from copy import deepcopy

import pytest
from requests import exceptions

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_assignment_rules_url
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


def test_rbac_retry_error_handling(mocker, db_create_host, api_get, enable_rbac):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = exceptions.RetryError

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url)

    mock_rbac_failure.assert_called_once()
    abort_mock.assert_called_once_with(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")


def test_rbac_exception_handling(mocker, db_create_host, api_get, enable_rbac):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = Exception()

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url)

    mock_rbac_failure.assert_called_once()
    abort_mock.assert_called_once_with(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")


@pytest.mark.parametrize(
    "field",
    ["key", "operation", "value"],
)
def test_RBAC_invalid_attribute_filter(mocker, api_get, field, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"][field] = "invalidvalue"

    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_get(build_hosts_url())

    assert_response_status(response_status, 503)


def test_RBAC_invalid_UUIDs(mocker, api_get, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = ["not a UUID"]

    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_get(build_hosts_url())

    assert_response_status(response_status, 503)


@pytest.mark.parametrize(
    "url_builder",
    [build_staleness_url, build_assignment_rules_url, build_groups_url],
)
def test_non_host_endpoints_cannot_bypass_RBAC(api_get, enable_rbac, url_builder):
    url = url_builder()
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 403)


@pytest.mark.parametrize(
    "url_builder",
    [build_staleness_url, build_assignment_rules_url, build_groups_url],
)
def test_edge_parity_migration_bypass_rbac(api_get, enable_rbac, url_builder, mocker):
    user_admin_identity = deepcopy(USER_IDENTITY)
    user_admin_identity["user"]["is_org_admin"] = True

    # Test what happens when the edgeParity.groups-migration flag is set to True
    mocker.patch("lib.middleware.get_flag_value", return_value=True)
    response_status, _ = api_get(url=url_builder(), identity=user_admin_identity)

    assert_response_status(response_status, 200)


@pytest.mark.parametrize(
    "org_admin_value, expected_status",
    (
        ("False", 403),
        ("false", 403),
        (False, 403),
        ("test", 401),
        ("", 401),
        (None, 401),
    ),
)
def test_edge_parity_migration_wrong_org_id_format(api_get, enable_rbac, org_admin_value, expected_status, mocker):
    user_admin_identity = deepcopy(USER_IDENTITY)
    user_admin_identity["user"]["is_org_admin"] = org_admin_value

    # Pretend that the feature flag returns True
    mocker.patch("lib.middleware.get_flag_value", return_value=True)

    # Mock RBAC's response to grant no permissions
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response("tests/helpers/rbac-mock-data/inv-none.json")
    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_get(url=build_hosts_url(), identity=user_admin_identity)
    assert_response_status(response_status, expected_status)
