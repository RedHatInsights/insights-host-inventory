import pytest
from requests import exceptions

import lib.middleware
from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_custom_rbac_response
from tests.helpers.api_utils import create_mock_rbac_response
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
    "url_builder",
    [build_staleness_url, build_groups_url],
)
def test_non_host_endpoints_cannot_bypass_RBAC(api_get, url_builder):
    url = url_builder()
    response_status, _ = api_get(url, SYSTEM_IDENTITY)

    assert_response_status(response_status, 403)


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


# ============================================================================
# RBAC v2 Service Account Authentication Tests (RHINENG-25611)
# ============================================================================


def test_get_rbac_oauth_credentials_delegates_to_shared(mocker):
    """
    Test that _get_rbac_oauth_credentials delegates to the shared get_oauth2_credentials.

    JIRA: RHINENG-25611
    """
    mock_credentials = mocker.Mock()
    mock_get_oauth2 = mocker.patch("lib.middleware.get_oauth2_credentials", return_value=mock_credentials)

    mock_config = mocker.Mock()
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    creds1 = lib.middleware._get_rbac_oauth_credentials()
    creds2 = lib.middleware._get_rbac_oauth_credentials()

    assert creds1 is creds2
    assert creds1 is mock_credentials
    assert mock_get_oauth2.call_count == 2
    mock_get_oauth2.assert_called_with(mock_config)


@pytest.mark.parametrize(
    "token_value, side_effect",
    [
        pytest.param("test_token_12345", None, id="success"),
        pytest.param(None, Exception("Token fetch failed"), id="failure"),
    ],
)
def test_get_rbac_access_token(mocker, token_value, side_effect):
    """
    Test OAuth2 access token fetch: success returns token, failure re-raises.

    JIRA: RHINENG-25611
    """
    mock_oauth_credentials = mocker.Mock()
    if side_effect:
        mock_oauth_credentials.get_token.side_effect = side_effect
    else:
        mock_token_response = mocker.Mock()
        mock_token_response.access_token = token_value
        mock_oauth_credentials.get_token.return_value = mock_token_response
    mocker.patch("lib.middleware._get_rbac_oauth_credentials", return_value=mock_oauth_credentials)

    if side_effect:
        with pytest.raises(Exception, match="Token fetch failed"):
            lib.middleware._get_rbac_access_token()
    else:
        assert lib.middleware._get_rbac_access_token() == token_value
    mock_oauth_credentials.get_token.assert_called_once()


@pytest.mark.parametrize(
    "use_service_account, custom_identity, custom_request_id",
    [
        pytest.param(True, None, None, id="with_service_account"),
        pytest.param(False, None, None, id="without_service_account"),
        pytest.param(True, "custom_identity", "custom_request_id", id="custom_identity"),
    ],
)
def test_build_rbac_request_headers(mocker, flask_app, use_service_account, custom_identity, custom_request_id):
    """
    Test _build_rbac_request_headers with various argument combinations.

    JIRA: RHINENG-25611
    """
    if use_service_account:
        mocker.patch("lib.middleware._get_rbac_access_token", return_value="mock_token")

    with flask_app.app.test_request_context(
        headers={"x-rh-identity": "default_identity", "x-rh-insights-request-id": "default_request_id"}
    ):
        kwargs = {"use_service_account": use_service_account}
        if custom_identity:
            kwargs["identity_header"] = custom_identity
        if custom_request_id:
            kwargs["request_id_header"] = custom_request_id

        headers = lib.middleware._build_rbac_request_headers(**kwargs)

        assert headers["x-rh-identity"] == (custom_identity or "default_identity")
        assert headers["x-rh-insights-request-id"] == (custom_request_id or "default_request_id")

        if use_service_account:
            assert headers["Authorization"] == "Bearer mock_token"
        else:
            assert "Authorization" not in headers


def test_rbac_create_ungrouped_workspace_uses_service_account(mocker, flask_app):  # noqa: ARG001
    """
    Test that ungrouped workspace creation uses OAuth2 service account, not PSK.

    JIRA: RHINENG-25611 - PSK removal
    """
    mocker.patch("lib.middleware._get_rbac_access_token", return_value="mock_token")

    mock_rbac_request = mocker.patch("lib.middleware.rbac_get_request_using_endpoint_and_headers")
    mock_rbac_request.return_value = {"id": "workspace-uuid-12345"}

    mock_config = mocker.Mock()
    mock_config.bypass_kessel = False
    mock_config.rbac_endpoint = "http://rbac-service:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    test_identity = mocker.Mock()
    test_identity.org_id = "test-org-123"

    workspace_id = lib.middleware.rbac_create_ungrouped_hosts_workspace(test_identity)

    assert workspace_id == "workspace-uuid-12345"

    headers_used = mock_rbac_request.call_args[0][1]
    assert "X-RH-RBAC-PSK" not in headers_used
    assert "Authorization" in headers_used


def test_build_service_account_headers(mocker):
    """
    Test that _build_service_account_headers produces correct headers with OAuth2 token
    and org context, without x-rh-identity.

    JIRA: RHINENG-25611
    """
    mocker.patch("lib.middleware._get_rbac_access_token", return_value="sa_token_abc")

    headers = lib.middleware._build_service_account_headers("org-42")

    assert headers["Authorization"] == "Bearer sa_token_abc"
    assert headers["X-RH-RBAC-ORG-ID"] == "org-42"
    assert headers["X-RH-RBAC-CLIENT-ID"] == "inventory"
    assert len(headers) == 3
    assert "x-rh-identity" not in {k.lower() for k in headers}
