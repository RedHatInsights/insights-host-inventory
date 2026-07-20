from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import grpc
import pytest

from app.auth.identity import IdentityType
from lib.middleware import _has_rbac_permission
from tests.helpers.api_utils import create_mock_rbac_response


class TestHasRbacPermission:
    """Unit tests for wildcard-aware RBAC permission matching."""

    def test_exact_match(self):
        assert _has_rbac_permission(["advisor:*:read"], "advisor:*:read")

    def test_full_wildcard(self):
        assert _has_rbac_permission(["vulnerability:*:*"], "vulnerability:vulnerability_results:read")

    def test_resource_wildcard(self):
        assert _has_rbac_permission(
            ["vulnerability:vulnerability_results:*"], "vulnerability:vulnerability_results:read"
        )

    def test_verb_wildcard(self):
        assert _has_rbac_permission(["vulnerability:*:read"], "vulnerability:vulnerability_results:read")

    def test_no_match_different_app(self):
        assert not _has_rbac_permission(["advisor:*:read"], "vulnerability:vulnerability_results:read")

    def test_no_match_wrong_verb(self):
        assert not _has_rbac_permission(["advisor:*:write"], "advisor:*:read")

    def test_no_match_wrong_resource(self):
        assert not _has_rbac_permission(["vulnerability:other:read"], "vulnerability:vulnerability_results:read")

    def test_multiple_permissions_one_matches(self):
        assert _has_rbac_permission(
            ["advisor:*:write", "vulnerability:*:read"], "vulnerability:vulnerability_results:read"
        )

    def test_empty_permission_list(self):
        assert not _has_rbac_permission([], "advisor:*:read")

    def test_hyphenated_app_name(self):
        assert _has_rbac_permission(["malware-detection:*:*"], "malware-detection:*:read")

    def test_specific_resource_matches_specific_required(self):
        """Custom role with exact resource permission matches specific required permission."""
        assert _has_rbac_permission(["advisor:recommendation-results:read"], "advisor:recommendation-results:read")

    def test_wildcard_resource_matches_specific_required(self):
        """Standard role with wildcard covers specific required permission."""
        assert _has_rbac_permission(["advisor:*:read"], "advisor:recommendation-results:read")

    def test_wrong_specific_resource_does_not_match(self):
        """Custom role with a different resource does not match."""
        assert not _has_rbac_permission(["advisor:exports:read"], "advisor:recommendation-results:read")

    def test_multiple_specific_resources_one_matches(self):
        """Custom role with several specific resources, only the right one matches."""
        assert _has_rbac_permission(
            ["advisor:exports:read", "advisor:weekly-email:read", "advisor:recommendation-results:read"],
            "advisor:recommendation-results:read",
        )

    def test_multiple_specific_resources_none_match(self):
        """Custom role with specific resources but not the required one."""
        assert not _has_rbac_permission(
            ["advisor:exports:read", "advisor:weekly-email:read"],
            "advisor:recommendation-results:read",
        )


@contextmanager
def _rbac_v1_mocks(rbac_data_file, identity_type=IdentityType.USER):
    """Shared mock setup for RBAC v1 tests."""
    with (
        patch("lib.middleware.inventory_config") as mock_config,
        patch("lib.middleware.get_current_identity") as mock_identity,
        patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
        patch("lib.middleware._build_rbac_request_headers", return_value={}),
        patch("lib.middleware.get_rbac_permissions") as mock_rbac,
    ):
        mock_config.return_value.bypass_rbac = False
        mock_identity.return_value.identity_type = identity_type
        mock_identity.return_value.org_id = "test_org"
        mock_identity.return_value.user = {"is_org_admin": False}
        mock_rbac.return_value = create_mock_rbac_response(rbac_data_file)
        yield


@contextmanager
def _kessel_mocks():
    """Shared mock setup for Kessel v2 tests."""
    with (
        patch("lib.middleware.inventory_config") as mock_config,
        patch("lib.middleware.get_current_identity") as mock_identity,
        patch("lib.middleware.is_rbac_v2_enabled", return_value=True),
        patch("lib.middleware.get_kessel_client") as mock_get_kessel,
    ):
        mock_config.return_value.bypass_rbac = False
        mock_identity.return_value.identity_type = IdentityType.USER
        mock_identity.return_value.org_id = "test_org"
        mock_identity.return_value.user = {"is_org_admin": False}

        mock_kessel = MagicMock()
        mock_get_kessel.return_value = mock_kessel
        yield mock_kessel


class TestGetAllowedAppServices:
    """Tests for get_allowed_app_services() RBAC v1 path."""

    def test_bypass_rbac_returns_none(self):
        """When bypass_rbac is True, return None (all services allowed)."""
        from lib.middleware import get_allowed_app_services

        with patch("lib.middleware.inventory_config") as mock_config:
            mock_config.return_value.bypass_rbac = True
            result = get_allowed_app_services()
            assert result is None

    def test_system_identity_returns_none(self):
        """System identity bypasses RBAC -- return None."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
        ):
            mock_config.return_value.bypass_rbac = False
            mock_identity.return_value.identity_type = IdentityType.SYSTEM
            result = get_allowed_app_services()
            assert result is None

    def test_service_account_rbac_check(self):
        """Service account proceeds through RBAC v1 path and gets correct permissions."""
        from lib.middleware import get_allowed_app_services

        with _rbac_v1_mocks(
            "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json",
            identity_type=IdentityType.SERVICE_ACCOUNT,
        ):
            result = get_allowed_app_services()
            assert isinstance(result, set)
            assert "advisor" in result

    @pytest.mark.parametrize(
        "rbac_file,expected",
        [
            pytest.param(
                "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json",
                {"advisor"},
                id="partial_access",
            ),
            pytest.param(
                "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json",
                set(),
                id="no_access",
            ),
            pytest.param(
                "tests/helpers/rbac-mock-data/inv-hosts-read-all-apps.json",
                {"vulnerability", "advisor", "compliance", "patch", "remediations", "malware"},
                id="full_access",
            ),
        ],
    )
    def test_rbac_v1_access_levels(self, rbac_file, expected):
        """RBAC v1 returns correct allowed set for various permission levels."""
        from lib.middleware import get_allowed_app_services

        with _rbac_v1_mocks(rbac_file):
            result = get_allowed_app_services()
            assert result == expected


class TestGetAllowedAppServicesKessel:
    """Tests for get_allowed_app_services() Kessel v2 path."""

    def test_kessel_partial_access(self):
        """ListAllowedWorkspaces returns workspaces for some services, empty for others."""
        from lib.middleware import get_allowed_app_services

        allowed_relations = {"advisor_recommendation_results_view", "patch_system_view"}

        with _kessel_mocks() as mock_kessel:

            def mock_list(_identity, relation):
                if relation in allowed_relations:
                    return ["ws-1"]
                return []

            mock_kessel.ListAllowedWorkspaces.side_effect = mock_list

            result = get_allowed_app_services()
            assert result == {"advisor", "patch"}

    @pytest.mark.parametrize(
        "workspaces,expected",
        [
            pytest.param(["ws-1"], "all", id="all_allowed"),
            pytest.param([], "none", id="all_denied"),
        ],
    )
    def test_kessel_uniform_access(self, workspaces, expected):
        """ListAllowedWorkspaces returns same result for all services."""
        from app.models.host_app_data import get_app_data_models
        from lib.middleware import get_allowed_app_services

        with _kessel_mocks() as mock_kessel:
            mock_kessel.ListAllowedWorkspaces.return_value = workspaces

            result = get_allowed_app_services()
            if expected == "all":
                assert result == set(get_app_data_models().keys())
            else:
                assert result == set()

    def test_kessel_grpc_error_fails_closed(self):
        """gRPC error on ListAllowedWorkspaces should deny that service (fail closed)."""
        from lib.middleware import get_allowed_app_services

        error = grpc.RpcError()
        error.code = Mock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = Mock(return_value="service unavailable")

        with _kessel_mocks() as mock_kessel:
            mock_kessel.ListAllowedWorkspaces.side_effect = error

            result = get_allowed_app_services()
            assert result == set()

    def test_kessel_grpc_error_partial_then_error(self):
        """First service succeeds, rest error -- only 1 service allowed (fail-closed per service)."""
        from app.models.host_app_data import get_app_data_models
        from lib.middleware import get_allowed_app_services

        call_count = 0
        expected_model_count = len(
            [m for m in get_app_data_models().values() if getattr(m, "__kessel_relation__", "")]
        )

        error = grpc.RpcError()
        error.code = Mock(return_value=grpc.StatusCode.UNAVAILABLE)
        error.details = Mock(return_value="service unavailable")

        with _kessel_mocks() as mock_kessel:

            def mock_list(_identity, _relation):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return ["ws-1"]
                raise error

            mock_kessel.ListAllowedWorkspaces.side_effect = mock_list

            result = get_allowed_app_services()
            assert len(result) == 1
            assert call_count == expected_model_count
