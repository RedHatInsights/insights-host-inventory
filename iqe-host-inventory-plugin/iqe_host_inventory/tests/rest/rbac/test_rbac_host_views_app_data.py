"""
metadata:
    requirements: inv-rbac
"""

from __future__ import annotations

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.host_views_fixtures import add_app_data_to_host
from iqe_host_inventory.modeling.host_view_api import APP_NAMES
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import wait_for_kessel_sync

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.usefixtures("enable_inventory_views_rbac_module"),
]

ALL_APPS = set(APP_NAMES)

SERVICE_PERMISSION_MAP = {
    "advisor": RBACInventoryPermission.ADVISOR_READ,
    "vulnerability": RBACInventoryPermission.VULNERABILITY_READ,
    "compliance": RBACInventoryPermission.COMPLIANCE_READ,
    "patch": RBACInventoryPermission.PATCH_READ,
    "remediations": RBACInventoryPermission.REMEDIATIONS_READ,
    "malware": RBACInventoryPermission.MALWARE_READ,
}

SYSTEM_ROLE_NAMES = {
    "malware": "Malware detection viewer",
}


@pytest.fixture(scope="module")
def host_with_all_app_data(host_inventory: ApplicationHostInventory):
    """Create one host with app_data for every known service."""
    host = host_inventory.kafka.create_host(cleanup_scope="module")
    for app_name in APP_NAMES:
        add_app_data_to_host(host_inventory, host, app_name)
    return host


@pytest.fixture(params=sorted(SERVICE_PERMISSION_MAP.keys()), scope="class")
def single_service_rbac_setup(
    request,
    hbi_non_org_admin_user_rbac_setup_class,
    host_inventory: ApplicationHostInventory,
):
    """Set up the non-org-admin user with HOSTS_READ + one service permission.

    Some services (e.g., malware-detection) don't allow custom RBAC v1 role creation.
    For those, we look up and assign the existing system viewer role instead.
    """
    service = request.param
    system_role_name = SYSTEM_ROLE_NAMES.get(service)

    if system_role_name:
        hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.HOSTS_READ])
        role = host_inventory.apis.rbac.get_role_by_name(system_role_name)
        group = host_inventory.apis.rbac.raw_api.group_api.list_groups(name="iqe-hbi").data[0]
        host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)
        wait_for_kessel_sync(host_inventory)
    else:
        hbi_non_org_admin_user_rbac_setup_class(
            permissions=[RBACInventoryPermission.HOSTS_READ, SERVICE_PERMISSION_MAP[service]]
        )

    return service


class TestPerServiceAccess:
    """Each single-service user sees only their service's data; others are denied."""

    def test_single_service_user_sees_only_their_data(
        self,
        single_service_rbac_setup: str,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        service = single_service_rbac_setup
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id)
        )

        assert service not in response.denied_services
        for other in ALL_APPS - {service}:
            assert other in response.denied_services

        host = response.results[0]
        assert getattr(host.app_data, service) is not None
        for other in ALL_APPS - {service}:
            assert getattr(host.app_data, other) is None


@pytest.mark.usefixtures("rbac_hosts_read_all_services_user_setup_class")
class TestAllServicesAccess:
    """User with all service permissions sees all app_data."""

    def test_all_apps_user_sees_all_data(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id)
        )

        for app in ALL_APPS:
            assert app not in (response.denied_services or [])

        host = response.results[0]
        for app in ALL_APPS:
            assert getattr(host.app_data, app) is not None


@pytest.mark.usefixtures("rbac_inventory_hosts_read_user_setup_class")
class TestNoServiceAccess:
    """User with only hosts:read and no service permissions sees no app_data."""

    def test_no_apps_user_sees_no_data(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id)
        )

        for app in ALL_APPS:
            assert app in response.denied_services

        host = response.results[0]
        for app in ALL_APPS:
            assert getattr(host.app_data, app) is None

    def test_sort_by_denied_service_returns_403(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        with raises_apierror(403, "Insufficient permissions to sort"):
            host_inventory_non_org_admin.apis.host_views.get_host_views_response(
                order_by="vulnerability:critical_cves", order_how="DESC"
            )

    def test_filter_by_denied_service_returns_403(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        with raises_apierror(403, "Insufficient permissions to filter"):
            host_inventory_non_org_admin.apis.host_views.get_host_views_response(
                filter=["[advisor][recommendations][gte]=1"]
            )


@pytest.mark.usefixtures("rbac_hosts_read_advisor_read_user_setup_class")
class TestAllowedSortAndFilter:
    """User with a service permission can sort/filter by that service."""

    def test_sort_by_allowed_service_returns_200(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            order_by="advisor:recommendations", order_how="DESC"
        )
        assert response.total >= 0

    def test_filter_by_allowed_service_returns_200(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            filter=["[advisor][recommendations][gte]=0"]
        )
        assert response.total >= 0


@pytest.mark.usefixtures("rbac_hosts_read_advisor_read_user_setup_class")
class TestSparseFieldsWithDenial:
    """Sparse field requests interact correctly with per-service RBAC."""

    def test_denied_service_excluded_from_sparse_fields(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id),
            fields=["[vulnerability]=true"],
        )

        assert "vulnerability" in response.denied_services

        host = response.results[0]
        assert host.app_data.vulnerability is None

    def test_allowed_service_sparse_fields_work(
        self,
        host_with_all_app_data,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory_non_org_admin.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id),
            fields=["[advisor]=true"],
        )

        assert "advisor" not in (response.denied_services or [])

        host = response.results[0]
        assert host.app_data.advisor is not None


class TestOrgAdminBypass:
    """Org admin bypasses per-service RBAC."""

    def test_org_admin_sees_all_data(
        self,
        host_with_all_app_data,
        host_inventory: ApplicationHostInventory,
    ):
        """
        metadata:
            jira: RHINENG-28773
        """
        response = host_inventory.apis.host_views.get_host_views_response(
            hostname_or_id=str(host_with_all_app_data.id)
        )

        assert not response.denied_services

        host = response.results[0]
        for app in ALL_APPS:
            assert getattr(host.app_data, app) is not None
