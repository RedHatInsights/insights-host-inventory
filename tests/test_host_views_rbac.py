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
        """System identity bypasses RBAC — return None."""
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

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
            patch("lib.middleware._build_rbac_request_headers", return_value={}),
            patch("lib.middleware.get_rbac_permissions") as mock_rbac,
        ):
            mock_config.return_value.bypass_rbac = False
            identity = Mock(spec_set=["identity_type", "org_id", "service_account"])
            identity.identity_type = IdentityType.SERVICE_ACCOUNT
            identity.org_id = "test_org"
            mock_identity.return_value = identity
            mock_rbac.return_value = create_mock_rbac_response(
                "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json"
            )
            result = get_allowed_app_services()
            assert isinstance(result, set)
            assert "advisor" in result

    def test_partial_access_advisor_only(self):
        """User with only advisor permissions gets only advisor."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
            patch("lib.middleware._build_rbac_request_headers", return_value={}),
            patch("lib.middleware.get_rbac_permissions") as mock_rbac,
        ):
            mock_config.return_value.bypass_rbac = False
            mock_identity.return_value.identity_type = IdentityType.USER
            mock_identity.return_value.org_id = "test_org"
            mock_identity.return_value.user = {"is_org_admin": False}
            mock_rbac.return_value = create_mock_rbac_response(
                "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json"
            )
            result = get_allowed_app_services()
            assert result == {"advisor"}

    def test_no_app_permissions(self):
        """User with only inventory:hosts:read gets empty set."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
            patch("lib.middleware._build_rbac_request_headers", return_value={}),
            patch("lib.middleware.get_rbac_permissions") as mock_rbac,
        ):
            mock_config.return_value.bypass_rbac = False
            mock_identity.return_value.identity_type = IdentityType.USER
            mock_identity.return_value.org_id = "test_org"
            mock_identity.return_value.user = {"is_org_admin": False}
            mock_rbac.return_value = create_mock_rbac_response(
                "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json"
            )
            result = get_allowed_app_services()
            assert result == set()

    def test_all_app_permissions(self):
        """User with all service permissions gets full set."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
            patch("lib.middleware._build_rbac_request_headers", return_value={}),
            patch("lib.middleware.get_rbac_permissions") as mock_rbac,
        ):
            mock_config.return_value.bypass_rbac = False
            mock_identity.return_value.identity_type = IdentityType.USER
            mock_identity.return_value.org_id = "test_org"
            mock_identity.return_value.user = {"is_org_admin": False}
            mock_rbac.return_value = create_mock_rbac_response(
                "tests/helpers/rbac-mock-data/inv-hosts-read-all-apps.json"
            )
            result = get_allowed_app_services()
            assert result == {"vulnerability", "advisor", "compliance", "patch", "remediations", "malware"}



class TestGetAllowedAppServicesKessel:
    """Tests for get_allowed_app_services() Kessel v2 path."""

    def _setup_kessel_mocks(self, mock_config, mock_identity, mock_principal):
        mock_config.return_value.bypass_rbac = False
        mock_identity.return_value.identity_type = IdentityType.USER
        mock_identity.return_value.org_id = "test_org"
        mock_identity.return_value.user = {"is_org_admin": False}
        mock_identity.return_value._asdict = Mock(
            return_value={"type": "User", "org_id": "test_org", "user": {"is_org_admin": False}}
        )
        mock_principal.return_value = Mock()

    def test_kessel_partial_access(self):
        """CheckBulk returns some services allowed, some denied."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=True),
            patch("lib.middleware.get_kessel_client") as mock_get_kessel,
            patch("kessel.console.principal_from_rh_identity") as mock_principal,
        ):
            self._setup_kessel_mocks(mock_config, mock_identity, mock_principal)

            mock_kessel = MagicMock()
            mock_get_kessel.return_value = mock_kessel

            allowed_relations = {"advisor_recommendation_results_view", "patch_system_view"}

            def mock_check(_subject_ref, permission, resource_ids, _org_id):
                if permission.workspace_permission in allowed_relations:
                    return True, []
                return False, resource_ids

            mock_kessel._check_bulk_resources.side_effect = mock_check

            result = get_allowed_app_services()
            assert result == {"advisor", "patch"}

    @pytest.mark.parametrize(
        "check_return,expected",
        [
            pytest.param((True, []), "all", id="all_allowed"),
            pytest.param((False, ["root"]), "none", id="all_denied"),
        ],
    )
    def test_kessel_uniform_access(self, check_return, expected):
        """CheckBulk returns same result for all services."""
        from app.models.host_app_data import get_app_data_models
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=True),
            patch("lib.middleware.get_kessel_client") as mock_get_kessel,
            patch("kessel.console.principal_from_rh_identity") as mock_principal,
        ):
            self._setup_kessel_mocks(mock_config, mock_identity, mock_principal)

            mock_kessel = MagicMock()
            mock_get_kessel.return_value = mock_kessel
            mock_kessel._check_bulk_resources.return_value = check_return

            result = get_allowed_app_services()
            if expected == "all":
                assert result == set(get_app_data_models().keys())
            else:
                assert result == set()

    def test_kessel_grpc_error_fails_closed(self):
        """gRPC error on CheckBulk should deny all services (fail closed)."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=True),
            patch("lib.middleware.get_kessel_client") as mock_get_kessel,
            patch("kessel.console.principal_from_rh_identity") as mock_principal,
        ):
            self._setup_kessel_mocks(mock_config, mock_identity, mock_principal)

            mock_kessel = MagicMock()
            mock_get_kessel.return_value = mock_kessel

            error = grpc.RpcError()
            error.code = Mock(return_value=grpc.StatusCode.UNAVAILABLE)
            error.details = Mock(return_value="service unavailable")
            mock_kessel._check_bulk_resources.side_effect = error

            result = get_allowed_app_services()
            assert result == set()

    def test_kessel_grpc_error_partial_then_error(self):
        """First service succeeds, rest error — only 1 service allowed (fail-closed per service)."""
        from lib.middleware import get_allowed_app_services

        call_count = 0

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.is_rbac_v2_enabled", return_value=True),
            patch("lib.middleware.get_kessel_client") as mock_get_kessel,
            patch("kessel.console.principal_from_rh_identity") as mock_principal,
        ):
            self._setup_kessel_mocks(mock_config, mock_identity, mock_principal)

            mock_kessel = MagicMock()
            mock_get_kessel.return_value = mock_kessel

            error = grpc.RpcError()
            error.code = Mock(return_value=grpc.StatusCode.UNAVAILABLE)
            error.details = Mock(return_value="service unavailable")

            def mock_check(_subject_ref, _permission, _resource_ids, _org_id):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return True, []
                raise error

            mock_kessel._check_bulk_resources.side_effect = mock_check

            result = get_allowed_app_services()
            assert len(result) == 1
            assert "advisor" in result
            assert call_count == 6
