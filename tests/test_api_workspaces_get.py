"""
Basic tests for RBAC v2 workspace functionality.

This file contains only basic tests for RBAC v2 route constants and URL construction.
Complex integration tests are moved to test_rbac_v2_workspaces.py to prevent
interference with existing group tests.
"""

from unittest.mock import MagicMock

import pytest

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
