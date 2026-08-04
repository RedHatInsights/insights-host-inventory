# mypy: disallow-untyped-defs

import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
]

logger = logging.getLogger(__name__)


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_inv_admin"),
        lf("host_inventory_rbac_groups_admin"),
        lf("host_inventory_rbac_groups_viewer"),
        lf("host_inventory_rbac_groups_all"),
        lf("host_inventory_rbac_all_read"),
    ],
    scope="class",
)
def host_inventory_read_permissions(request: pytest.FixtureRequest) -> ApplicationHostInventory:
    return request.param


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_hosts_admin"),
        lf("host_inventory_rbac_hosts_viewer"),
        lf("host_inventory_rbac_hosts_write"),
        lf("host_inventory_rbac_hosts_all"),
        lf("host_inventory_rbac_groups_write"),
        lf("host_inventory_rbac_no_perms"),
    ],
    scope="class",
)
def host_inventory_no_read_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


class TestRBACGroupsReadPermission:
    def test_rbac_groups_read_permission_get_groups_list(
        self,
        host_inventory_read_permissions: ApplicationHostInventory,
        rbac_setup_resources: RBACResources,
        hbi_default_org_id: str,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4499

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:read" permission can get a list of groups
        """
        response = host_inventory_read_permissions.apis.groups.get_groups()

        assert len(response) >= len(rbac_setup_resources.groups)
        for group in response:
            assert group.org_id == hbi_default_org_id

    def test_rbac_groups_read_permission_get_groups_by_id(
        self,
        host_inventory_read_permissions: ApplicationHostInventory,
        rbac_setup_resources: RBACResources,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4500

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:read" permission can get groups by ID
        """
        groups = rbac_setup_resources.groups

        response = host_inventory_read_permissions.apis.groups.get_groups_by_id(groups[0])
        assert len(response) == 1
        assert response[0].id == groups[0].id
        assert response[0].host_count >= 1

        response = host_inventory_read_permissions.apis.groups.get_groups_by_id(groups[-1])
        assert len(response) == 1
        assert response[0].id == groups[-1].id
        assert response[0].host_count == 0


class TestRBACGroupsNoReadPermission:
    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_groups_no_read_permission_get_groups_list(
        self,
        host_inventory_no_read_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4499

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:read" permission can't get a list of groups
        """
        with raises_apierror(403):
            host_inventory_no_read_permissions.apis.groups.get_groups()

    def test_rbac_groups_no_read_permission_get_groups_by_id(
        self,
        host_inventory_no_read_permissions: ApplicationHostInventory,
        rbac_setup_resources: RBACResources,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4500

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:read" permission can't get groups by ID
        """
        groups = rbac_setup_resources.groups

        for group in groups:
            with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
                host_inventory_no_read_permissions.apis.groups.get_groups_by_id(group)
