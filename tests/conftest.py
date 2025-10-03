import os
import sys

import pytest

from app.utils import HostWrapper

# Make test helpers available to be imported
sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

# Make fixtures available
pytest_plugins = [
    "tests.fixtures.api_fixtures",
    "tests.fixtures.app_fixtures",
    "tests.fixtures.db_fixtures",
    "tests.fixtures.mq_fixtures",
    "tests.fixtures.tracker_fixtures",
]


def pytest_assertrepr_compare(config, op, left, right):
    """
    until pytest diffs multiline repr: https://github.com/pytest-dev/pytest/issues/8346
    """
    if isinstance(left, HostWrapper) and isinstance(right, HostWrapper) and op == "==":
        res = config.hook.pytest_assertrepr_compare(config=config, op=op, left=repr(left), right=repr(right))
        return res[0]


def pytest_sessionfinish():
    """Remove handlers from all loggers"""
    import logging

    loggers = [logging.getLogger()] + list(logging.Logger.manager.loggerDict.values())
    for logger in loggers:
        if not hasattr(logger, "handlers"):
            continue
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)


@pytest.fixture(autouse=True)
def disable_kessel_for_tests(mocker):
    """
    Automatically disable Kessel for all tests to prevent connection errors.
    This fixture runs automatically for all tests and mocks the feature flags
    to disable Kessel (FLAG_INVENTORY_KESSEL_PHASE_1), workspace migration
    (FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION), and read-only mode
    (FLAG_INVENTORY_API_READ_ONLY) so that tests use the legacy RBAC system
    instead of trying to connect to Kessel.
    """
    from lib.feature_flags import FLAG_INVENTORY_API_READ_ONLY
    from lib.feature_flags import FLAG_INVENTORY_KESSEL_PHASE_1
    from lib.feature_flags import FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION

    # Mock the flags to use old RBAC system and disable read-only mode
    # Mock both middleware and feature_flags modules since different endpoints import from different places
    disabled_flags = [
        FLAG_INVENTORY_KESSEL_PHASE_1,
        FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION,
        FLAG_INVENTORY_API_READ_ONLY,
    ]
    mocker.patch("lib.middleware.get_flag_value", side_effect=lambda name: name not in disabled_flags)
    mocker.patch("lib.feature_flags.get_flag_value", side_effect=lambda name: name not in disabled_flags)


@pytest.fixture
def mock_rbac_v1(mocker):
    """
    Mock RBAC v1 functions to prevent actual HTTP calls to RBAC service.
    Returns a mock that can be configured by individual tests.
    """
    # Mock the main RBAC v1 functions
    rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    rbac_request_mock = mocker.patch("lib.middleware.rbac_get_request_using_endpoint_and_headers")
    rbac_make_request_mock = mocker.patch("lib.middleware._make_rbac_request")

    # Default to allowing all permissions
    rbac_permissions_mock.return_value = [{"permission": "inventory:*:*"}]
    rbac_request_mock.return_value = {"data": [{"permission": "inventory:*:*"}]}
    rbac_make_request_mock.return_value = {"data": [{"permission": "inventory:*:*"}]}

    return {"permissions": rbac_permissions_mock, "request": rbac_request_mock, "make_request": rbac_make_request_mock}


@pytest.fixture
def mock_rbac_v2(mocker):
    """
    Mock RBAC v2 (Kessel) functions to prevent actual gRPC calls to Kessel service.
    Returns a mock that can be configured by individual tests.
    """
    # Mock Kessel client and methods
    kessel_client_mock = mocker.patch("lib.middleware.get_kessel_client")
    kessel_instance_mock = mocker.MagicMock()
    kessel_client_mock.return_value = kessel_instance_mock

    # Default to allowing all permissions
    kessel_instance_mock.check.return_value = True
    kessel_instance_mock.list_workspaces.return_value = []

    return {"client": kessel_client_mock, "instance": kessel_instance_mock}


@pytest.fixture
def mock_rbac_v2_workspace_functions(mocker):
    """
    Mock RBAC v2 workspace functions that use get_rbac_v2_url.
    Use this fixture for tests that specifically need to mock workspace operations.
    """
    from tests.helpers.test_utils import generate_uuid

    # Mock the workspace functions that use get_rbac_v2_url
    post_workspace_mock = mocker.patch("lib.middleware.post_rbac_workspace")
    delete_workspace_mock = mocker.patch("lib.middleware.delete_rbac_workspace")
    patch_workspace_mock = mocker.patch("lib.middleware.patch_rbac_workspace")
    get_workspaces_mock = mocker.patch("lib.middleware.get_rbac_workspaces")
    get_default_workspace_mock = mocker.patch("lib.middleware.get_rbac_default_workspace")

    # Default to successful operations
    post_workspace_mock.return_value = generate_uuid()
    delete_workspace_mock.return_value = True
    patch_workspace_mock.return_value = None
    get_workspaces_mock.return_value = []
    get_default_workspace_mock.return_value = generate_uuid()

    return {
        "post_workspace": post_workspace_mock,
        "delete_workspace": delete_workspace_mock,
        "patch_workspace": patch_workspace_mock,
        "get_workspaces": get_workspaces_mock,
        "get_default_workspace": get_default_workspace_mock,
    }


@pytest.fixture
def mock_rbac_v1_denied(mocker):
    """
    Mock RBAC v1 to deny all permissions.
    """
    rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    rbac_request_mock = mocker.patch("lib.middleware.rbac_get_request_using_endpoint_and_headers")
    rbac_make_request_mock = mocker.patch("lib.middleware._make_rbac_request")

    # Return empty permissions (denied)
    rbac_permissions_mock.return_value = []
    rbac_request_mock.return_value = {"data": []}
    rbac_make_request_mock.return_value = {"data": []}

    return {"permissions": rbac_permissions_mock, "request": rbac_request_mock, "make_request": rbac_make_request_mock}


@pytest.fixture
def mock_rbac_v2_denied(mocker):
    """
    Mock RBAC v2 (Kessel) to deny all permissions.
    """
    kessel_client_mock = mocker.patch("lib.middleware.get_kessel_client")
    kessel_instance_mock = mocker.MagicMock()
    kessel_client_mock.return_value = kessel_instance_mock

    # Deny all permissions
    kessel_instance_mock.check.return_value = False
    kessel_instance_mock.list_workspaces.return_value = []

    return {"client": kessel_client_mock, "instance": kessel_instance_mock}
