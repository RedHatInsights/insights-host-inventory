from __future__ import annotations

from typing import Any

V2_BASE_URL = "/api/inventory/v2"
V2_HOST_URL = f"{V2_BASE_URL}/hosts"
V2_HOST_EXISTS_URL = f"{V2_BASE_URL}/host-exists"
V2_HOST_VIEWS_URL = f"{V2_BASE_URL}/host-views"
V2_TAGS_URL = f"{V2_BASE_URL}/tags"
V2_SYSTEM_PROFILE_URL = f"{V2_BASE_URL}/system-profile"
V2_RESOURCE_TYPES_URL = f"{V2_BASE_URL}/resource-types"
V2_STALENESS_URL = f"{V2_BASE_URL}/staleness"


def assert_error_response(response_data: dict[str, Any], expected_status: int) -> None:
    """Assert that a response body conforms to RFC 7807 Problem Details format."""
    assert "status" in response_data, f"RFC 7807: 'status' field missing: {response_data}"
    assert "title" in response_data, f"RFC 7807: 'title' field missing: {response_data}"
    assert "detail" in response_data, f"RFC 7807: 'detail' field missing: {response_data}"
    assert response_data["status"] == expected_status, (
        f"RFC 7807: expected status {expected_status}, got {response_data['status']}"
    )
    if "type" in response_data:
        assert isinstance(response_data["type"], str)
