"""
Tests for RBAC v2 workspace functionality.

This file contains tests specifically for RBAC v2 workspace features.
These tests are isolated from the main group tests to prevent interference
with existing RBAC v1 group functionality.
"""

from unittest.mock import MagicMock

import pytest

from lib.feature_flags import FLAG_INVENTORY_KESSEL_PHASE_1
from lib.feature_flags import FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION
from lib.middleware import RBAC_V2_ROUTE
from lib.middleware import _get_rbac_workspace_url
from lib.middleware import get_rbac_v2_url
from lib.middleware import get_rbac_workspaces


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_v2_route_constant():
    """Test that RBAC_V2_ROUTE constant is correctly defined."""
    assert RBAC_V2_ROUTE == "/api/rbac/v2/"


@pytest.mark.usefixtures("enable_rbac")
def test_get_workspaces_happy_path(mocker):
    """Test basic RBAC v2 workspace URL construction."""
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test URL construction
    base_url = get_rbac_v2_url("test-endpoint")
    assert base_url == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}test-endpoint"

    # Test workspace URL construction
    workspace_url = _get_rbac_workspace_url()
    assert workspace_url == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/"


@pytest.mark.usefixtures("enable_rbac")
def test_workspace_url_construction_logic(mocker):
    """Test workspace URL construction with different parameters."""
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test different workspace URL patterns
    base_workspace_url = _get_rbac_workspace_url()
    assert base_workspace_url == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/"

    # Test with limit parameter
    workspace_url_with_limit = _get_rbac_workspace_url(query_params={"limit": 5})
    assert "limit=5" in workspace_url_with_limit
    assert workspace_url_with_limit == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?limit=5"


@pytest.mark.usefixtures("enable_rbac")
def test_workspace_endpoint_patterns(mocker):
    """Test various workspace endpoint URL patterns."""
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test different group types
    group_types = ["standard", "ungrouped-hosts", "all"]

    for group_type in group_types:
        endpoint_with_type = _get_rbac_workspace_url(query_params={"type": group_type})
        assert group_type in endpoint_with_type
        assert endpoint_with_type == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?type={group_type}"

        # Test with limit
        endpoint_with_limit = _get_rbac_workspace_url(query_params={"type": group_type, "limit": 5})
        assert group_type in endpoint_with_limit
        assert "limit=5" in endpoint_with_limit
        assert (
            endpoint_with_limit
            == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?type={group_type}&limit=5"
        )


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_v2_integration_points(mocker):
    """Test RBAC v2 integration points and function availability."""
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test that all required functions are available
    assert callable(get_rbac_workspaces)
    assert callable(get_rbac_v2_url)
    assert callable(_get_rbac_workspace_url)

    # Test URL construction
    base_url = get_rbac_v2_url("test")
    assert RBAC_V2_ROUTE in base_url


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize("group_type", ["standard", "ungrouped-hosts", "all"])
def test_get_workspaces_using_different_types(group_type, mocker):
    """Test getting workspaces using different group types."""
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test URL construction for different types
    endpoint = _get_rbac_workspace_url(query_params={"type": group_type})
    assert group_type in endpoint
    assert endpoint == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?type={group_type}"


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_v2_route_configuration(mocker):
    """
    Test RBAC v2 route configuration without making actual API calls.
    This test verifies that the RBAC v2 route is properly configured
    and can be used for workspace operations.
    """
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test that RBAC v2 URL construction works
    base_url = get_rbac_v2_url("workspaces")
    assert base_url == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces"

    # Test workspace URL construction
    workspace_url = _get_rbac_workspace_url()
    assert workspace_url == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/"

    # Test workspace URL with query parameters
    workspace_url_with_params = _get_rbac_workspace_url(query_params={"type": "standard", "limit": 5})
    assert "type=standard" in workspace_url_with_params
    assert "limit=5" in workspace_url_with_params
    assert (
        workspace_url_with_params == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?type=standard&limit=5"
    )

    # Verify that RBAC_V2_ROUTE constant is correct
    assert RBAC_V2_ROUTE == "/api/rbac/v2/"

    # Test that feature flags are available
    assert FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION is not None
    assert FLAG_INVENTORY_KESSEL_PHASE_1 is not None


@pytest.mark.usefixtures("enable_rbac")
def test_rbac_v2_invalid_group_type_handling(mocker):
    """
    Test RBAC v2 invalid group type handling without making actual API calls.
    This test verifies that the RBAC v2 system can handle invalid group types
    and construct appropriate URLs for error handling.
    """
    # Mock inventory config
    mock_config = MagicMock()
    mock_config.rbac_endpoint = "http://test-rbac-endpoint:8080"
    mocker.patch("lib.middleware.inventory_config", return_value=mock_config)

    # Test that invalid group types can be handled in URL construction
    invalid_types = ["invalid-type", "bad-type", "unknown-type"]

    for invalid_type in invalid_types:
        # The URL construction should still work even with invalid types
        endpoint = _get_rbac_workspace_url(query_params={"type": invalid_type})
        assert invalid_type in endpoint
        assert endpoint == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/?type={invalid_type}"

    # Verify that RBAC_V2_ROUTE constant is correct
    assert RBAC_V2_ROUTE == "/api/rbac/v2/"

    # Test that the system can handle empty query parameters
    base_endpoint = _get_rbac_workspace_url()
    assert base_endpoint == f"http://test-rbac-endpoint:8080{RBAC_V2_ROUTE}workspaces/"
