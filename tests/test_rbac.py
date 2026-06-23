import json

import pytest
from requests import exceptions

import lib.middleware
from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_resource_types_groups_url
from tests.helpers.api_utils import build_resource_types_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import build_sys_default_staleness_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import get_required_headers
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_retry_error_handling(mocker, db_create_host, api_get):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = exceptions.RetryError

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url)

    mock_rbac_failure.assert_called_once()
    abort_mock.assert_called_once_with(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_exception_handling(mocker, db_create_host, api_get):
    request_session_get_mock = mocker.patch("lib.middleware.Session.get")
    request_session_get_mock.side_effect = Exception()

    host = db_create_host()

    url = build_hosts_url(host_list_or_id=host.id)

    mock_rbac_failure = mocker.patch("lib.middleware.rbac_failure")
    abort_mock = mocker.patch("lib.middleware.abort")

    api_get(url)

    mock_rbac_failure.assert_called_once()
    abort_mock.assert_called_once_with(503, "Failed to reach RBAC endpoint, request cannot be fulfilled")


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize(
    "field",
    ["key", "operation", "value"],
)
def test_RBAC_invalid_attribute_filter(mocker, api_get, field):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-hosts-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"][field] = "invalidvalue"

    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, _ = api_get(build_hosts_url())

    assert_response_status(response_status, 503)


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize("rbac_operation", [RBACFilterOperation.IN, RBACFilterOperation.EQUAL])
def test_RBAC_invalid_UUIDs(mocker, api_get, rbac_operation):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    get_rbac_permissions_mock.return_value = create_custom_rbac_response(["not a UUID"], rbac_operation)

    response_status, _ = api_get(build_hosts_url())

    assert_response_status(response_status, 503)


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize(
    "method,url,data,expected_status",
    [
        ("get", build_staleness_url(), None, 403),
        ("post", build_staleness_url(), {}, 403),
        ("patch", build_staleness_url(), {}, 403),
        ("delete", build_staleness_url(), None, 403),
        ("get", build_sys_default_staleness_url(), None, 403),
        ("get", build_groups_url(), None, 403),
        ("post", build_groups_url(), {"name": "test"}, 403),
        ("patch", build_groups_url(group_id=generate_uuid()), {"name": "test"}, 403),
        ("delete", build_groups_url(group_id=generate_uuid()), None, 403),
        ("post", f"{build_groups_url(group_id=generate_uuid())}/hosts", [str(generate_uuid())], 404),
        ("delete", f"{build_groups_url(group_id=generate_uuid())}/hosts/{generate_uuid()}", None, 404),
        ("delete", f"{build_groups_url()}/hosts/{generate_uuid()}", None, 403),
        ("get", build_resource_types_url(), None, 403),
        ("get", build_resource_types_groups_url(), None, 403),
    ],
    ids=[
        "GET /staleness",
        "POST /staleness",
        "PATCH /staleness",
        "DELETE /staleness",
        "GET /staleness/defaults",
        "GET /groups",
        "POST /groups",
        "PATCH /groups/{id}",
        "DELETE /groups/{id}",
        "POST /groups/{id}/hosts",
        "DELETE /groups/{id}/hosts/{host_id}",
        "DELETE /groups/hosts/{host_id}",
        "GET /resource-types",
        "GET /resource-types/inventory-groups",
    ],
)
def test_non_host_endpoints_cannot_bypass_RBAC(flask_client, method, url, data, expected_status):
    headers = get_required_headers(SYSTEM_IDENTITY)
    if data is not None:
        response = getattr(flask_client, method)(url, headers=headers, data=json.dumps(data))
    else:
        response = getattr(flask_client, method)(url, headers=headers)
    assert_response_status(response.status_code, expected_status)


@pytest.mark.usefixtures("enable_rbac")
def test_access_decorator_returns_404_for_nonexistent_host_with_permission_denied(mocker, api_get):
    """
    Test that accessing a non-existent host with permission denied returns 404, not 403.

    This prevents information leakage about whether a resource exists when the user
    doesn't have permission to access it.
    """
    # Mock RBAC to deny permission
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response("tests/helpers/rbac-mock-data/inv-none.json")
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Try to access a host that doesn't exist
    nonexistent_host_id = generate_uuid()
    url = build_hosts_url(host_list_or_id=nonexistent_host_id)

    response_status, _ = api_get(url)

    # Should return 404, not 403
    assert_response_status(response_status, 404)


@pytest.mark.usefixtures("enable_rbac")
def test_access_decorator_returns_403_for_existing_host_with_permission_denied(mocker, api_get, db_create_host):
    """
    Test that accessing an existing host with permission denied still returns 403.

    This ensures that the existing behavior is preserved when the resource actually exists.
    """
    # Create a host
    host = db_create_host()

    # Mock RBAC to deny permission
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response("tests/helpers/rbac-mock-data/inv-none.json")
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Try to access the existing host
    url = build_hosts_url(host_list_or_id=host.id)

    response_status, _ = api_get(url)

    # Should return 403 (because the host exists but permission is denied)
    assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_access_decorator_delete_nonexistent_host_with_permission_denied(mocker, api_delete_host):
    """
    Test that deleting a non-existent host with permission denied returns 404, not 403.
    """
    # Mock RBAC to deny permission
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response("tests/helpers/rbac-mock-data/inv-none.json")
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Try to delete a host that doesn't exist
    nonexistent_host_id = generate_uuid()

    response_status, _ = api_delete_host(nonexistent_host_id)

    # Should return 404, not 403
    assert_response_status(response_status, 404)


@pytest.mark.usefixtures("enable_rbac")
def test_access_decorator_patch_nonexistent_host_with_permission_denied(mocker, api_patch):
    """
    Test that patching a non-existent host with permission denied returns 404, not 403.
    """
    # Mock RBAC to deny permission
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response("tests/helpers/rbac-mock-data/inv-none.json")
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Try to patch a host that doesn't exist
    nonexistent_host_id = generate_uuid()
    url = build_hosts_url(host_list_or_id=nonexistent_host_id)

    response_status, _ = api_patch(url, {"display_name": "new_name"})

    # Should return 404, not 403
    assert_response_status(response_status, 404)


def test_build_rbac_auth_request_headers(mocker):
    """
    Test that _build_rbac_auth_request_headers produces correct headers with OAuth2 token
    and org context, without x-rh-identity.

    JIRA: RHINENG-25611
    """
    mocker.patch("lib.middleware._get_rbac_access_token", return_value="sa_token_abc")

    mock_config = mocker.Mock()
    mock_config.bypass_kessel = False
    mock_config.kessel_auth_enabled = True
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    headers = lib.middleware._build_rbac_auth_request_headers("org-42")

    assert headers["Authorization"] == "Bearer sa_token_abc"
    assert headers["X-RH-RBAC-ORG-ID"] == "org-42"
    assert headers["X-RH-RBAC-CLIENT-ID"] == "inventory"
    assert len(headers) == 3
    assert "x-rh-identity" not in {k.lower() for k in headers}
