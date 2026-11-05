from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from app.auth.identity import IdentityType
from lib.middleware import _has_rbac_permission
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_host_view_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.db_utils import db_create_host_app_data


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

    def test_specific_resource_does_not_satisfy_wildcard_required(self):
        """User with specific resource cannot satisfy a wildcard-resource requirement."""
        assert not _has_rbac_permission(["patch:system:read"], "patch:*:read")


@contextmanager
def _rbac_v1_mocks(rbac_data_file, identity_type=IdentityType.USER):
    """Shared mock setup for RBAC v1 tests."""
    with (
        patch("lib.middleware.inventory_config") as mock_config,
        patch("lib.middleware.get_current_identity") as mock_identity,
        patch("lib.middleware.is_rbac_v2_enabled", return_value=False),
        patch("lib.middleware.get_flag_value", return_value=True),
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
        patch("lib.middleware.get_flag_value", return_value=True),
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

    def test_flag_off_returns_none(self):
        """Feature flag disabled means all services allowed (no RBAC enforcement)."""
        from lib.middleware import get_allowed_app_services

        with (
            patch("lib.middleware.inventory_config") as mock_config,
            patch("lib.middleware.get_current_identity") as mock_identity,
            patch("lib.middleware.get_flag_value", return_value=False),
        ):
            mock_config.return_value.bypass_rbac = False
            mock_identity.return_value.identity_type = IdentityType.USER
            mock_identity.return_value.org_id = "test_org"
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

    def test_explicit_identity_and_headers(self):
        """get_allowed_app_services accepts explicit identity and rbac_request_headers."""
        from app.auth.identity import Identity
        from lib.middleware import get_allowed_app_services

        with _rbac_v1_mocks("tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json"):
            identity = Identity(
                {
                    "org_id": "explicit_org",
                    "type": "User",
                    "auth_type": "basic-auth",
                    "user": {"is_org_admin": False},
                }
            )
            headers = {"x-rh-identity": "explicit_hdr", "x-rh-insights-request-id": "req-123"}
            result = get_allowed_app_services(identity=identity, rbac_request_headers=headers)
            assert result == {"advisor"}


class TestGetAllowedAppServicesKessel:
    """Tests for get_allowed_app_services() Kessel v2 path (ListAllowedWorkspaces)."""

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

    def test_kessel_full_access(self):
        """ListAllowedWorkspaces returns workspaces for all services."""
        from app.models.host_app_data import get_app_data_models
        from lib.middleware import get_allowed_app_services

        with _kessel_mocks() as mock_kessel:
            mock_kessel.ListAllowedWorkspaces.return_value = ["ws-1"]

            result = get_allowed_app_services()
            assert result == set(get_app_data_models().keys())

    def test_kessel_no_access(self):
        """ListAllowedWorkspaces returns empty for all services."""
        from lib.middleware import get_allowed_app_services

        with _kessel_mocks() as mock_kessel:
            mock_kessel.ListAllowedWorkspaces.return_value = []

            result = get_allowed_app_services()
            assert result == set()

    def test_kessel_grpc_error_fails_closed(self):
        """gRPC error on ListAllowedWorkspaces denies that service (fail closed)."""
        from lib.middleware import get_allowed_app_services

        with _kessel_mocks() as mock_kessel:
            mock_kessel.ListAllowedWorkspaces.side_effect = Exception("gRPC unavailable")

            result = get_allowed_app_services()
            assert result == set()

    def test_kessel_partial_error(self):
        """First service succeeds, rest error — only allowed services returned."""
        from lib.middleware import get_allowed_app_services

        call_count = 0

        with _kessel_mocks() as mock_kessel:

            def mock_list(_identity, _relation):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return ["ws-1"]
                raise Exception("gRPC unavailable")

            mock_kessel.ListAllowedWorkspaces.side_effect = mock_list

            result = get_allowed_app_services()
            assert len(result) == 1


@pytest.mark.usefixtures("enable_rbac")
class TestHostViewPerServiceRBAC:
    """Integration tests for per-service RBAC filtering on /beta/hosts-view."""

    def _mock_rbac(self, mocker, response_file):
        """Mock RBAC permissions for per-service checks."""
        mock_data = create_mock_rbac_response(response_file)
        mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_data)
        mocker.patch("lib.middleware.get_flag_value", return_value=True)

    def _find_host_in_results(self, results, host_id):
        """Find a specific host by ID in the results list."""
        for r in results:
            if str(r["id"]) == str(host_id):
                return r
        raise AssertionError(f"Host {host_id} not found in results")

    def test_partial_access_filters_app_data(self, api_get, db_create_host, mocker):
        """User with advisor-only permissions sees advisor data but not vulnerability."""
        host = db_create_host()
        host_id = str(host.id)
        db_create_host_app_data(
            host.id, host.org_id, "advisor", recommendations=5, incidents=1, critical=1, important=2, moderate=1, low=1
        )
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=0,
        )

        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = self._find_host_in_results(response_data["results"], host_id)
        assert "advisor" in result["app_data"]
        assert "vulnerability" not in result["app_data"]
        assert "denied_services" in response_data
        assert "vulnerability" in response_data["denied_services"]
        assert "advisor" not in response_data["denied_services"]

    def test_no_service_permissions_returns_empty_app_data(self, api_get, db_create_host, mocker):
        """User with only inventory:hosts:read gets empty app_data."""
        host = db_create_host()
        host_id = str(host.id)
        db_create_host_app_data(
            host.id, host.org_id, "advisor", recommendations=5, incidents=1, critical=1, important=2, moderate=1, low=1
        )

        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json")

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = self._find_host_in_results(response_data["results"], host_id)
        assert result["app_data"] == {}

    def test_full_access_returns_all_app_data(self, api_get, db_create_host, mocker):
        """User with all service permissions gets all app_data."""
        host = db_create_host()
        host_id = str(host.id)
        db_create_host_app_data(
            host.id, host.org_id, "advisor", recommendations=5, incidents=1, critical=1, important=2, moderate=1, low=1
        )
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=0,
        )

        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-all-apps.json")

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = self._find_host_in_results(response_data["results"], host_id)
        assert "advisor" in result["app_data"]
        assert "vulnerability" in result["app_data"]
        assert response_data["denied_services"] == []

    def test_sort_by_unauthorized_field_returns_403(self, api_get, mocker):
        """Sorting by an unauthorized service's field returns 403."""
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?order_by=vulnerability:critical_cves")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 403)

    def test_filter_by_unauthorized_field_returns_403(self, api_get, mocker):
        """Filtering by an unauthorized service's field returns 403."""
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?filter[vulnerability][critical_cves][gte]=1")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 403)

    def test_filter_by_authorized_field_works(self, api_get, db_create_host, mocker):
        """Filtering by an authorized service's field returns 200."""
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?filter[advisor][recommendations][gte]=0")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 200)

    def test_sort_by_authorized_field_works(self, api_get, db_create_host, mocker):
        """Sorting by an authorized service's field returns 200."""
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?order_by=advisor:recommendations")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 200)

    def test_sort_by_non_app_field_always_works(self, api_get, db_create_host, mocker):
        """Sorting by display_name works regardless of service permissions."""
        db_create_host()
        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-no-apps.json")

        url = build_host_view_url(query="?order_by=display_name")
        response_status, _ = api_get(url)

        assert_response_status(response_status, 200)

    def test_sparse_fields_plus_no_permission(self, api_get, db_create_host, mocker):
        """fields[vulnerability]=true but no vuln permission — key still omitted."""
        host = db_create_host()
        host_id = str(host.id)
        db_create_host_app_data(
            host.id,
            host.org_id,
            "vulnerability",
            total_cves=10,
            critical_cves=2,
            important_cves=3,
            cves_with_security_rules=1,
            cves_with_known_exploits=0,
        )

        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-advisor-only.json")

        url = build_host_view_url(query="?fields[vulnerability]=true")
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        result = self._find_host_in_results(response_data["results"], host_id)
        assert "vulnerability" not in result["app_data"]

    def test_bypass_rbac_omits_denied_services(self, api_get, db_create_host, mocker):
        """When RBAC is bypassed, denied_services is absent from response."""
        host = db_create_host()
        db_create_host_app_data(
            host.id, host.org_id, "advisor", recommendations=5, incidents=1, critical=1, important=2, moderate=1, low=1
        )

        self._mock_rbac(mocker, "tests/helpers/rbac-mock-data/inv-hosts-read-all-apps.json")
        mocker.patch("lib.middleware._should_bypass_app_service_rbac", return_value=True)

        url = build_host_view_url()
        response_status, response_data = api_get(url)

        assert_response_status(response_status, 200)
        assert "denied_services" not in response_data
