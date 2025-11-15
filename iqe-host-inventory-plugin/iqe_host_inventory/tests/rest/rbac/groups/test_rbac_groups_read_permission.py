"""
metadata:
  requirements: inv-rbac
"""

import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory.utils.api_utils import raises_apierror

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
]

logger = logging.getLogger(__name__)


@pytest.fixture(
    params=[
        lf("rbac_inventory_groups_read_user_setup_class"),
        lf("rbac_inventory_all_read_user_setup_class"),
        lf("rbac_inventory_groups_all_user_setup_class"),
        lf("rbac_inventory_admin_user_setup_class"),
    ],
    scope="class",
)
def read_permission_user_setup(request):
    return request.param


@pytest.fixture(
    params=[
        lf("rbac_inventory_hosts_read_user_setup_class"),
        lf("rbac_inventory_hosts_write_user_setup_class"),
        lf("rbac_inventory_hosts_all_user_setup_class"),
        lf("rbac_inventory_groups_write_user_setup_class"),
        lf("rbac_inventory_user_without_permissions_setup_class"),
    ],
    scope="class",
)
def no_read_permission_user_setup(request):
    return request.param


class TestRBACGroupsReadPermission:
    def test_rbac_groups_read_permission_get_groups_list(
        self,
        read_permission_user_setup,
        rbac_setup_resources,
        host_inventory_non_org_admin,
        hbi_non_org_admin_user_org_id,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4499

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          title: Test that users with "groups:read" permission can get a list of groups
        """
        response = host_inventory_non_org_admin.apis.groups.get_groups()

        assert len(response) >= 2
        for group in response:
            assert group.org_id == hbi_non_org_admin_user_org_id

    def test_rbac_groups_read_permission_get_groups_by_id(
        self,
        read_permission_user_setup,
        rbac_setup_resources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4500

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Test that users with "groups:read" permission can get groups by ID
        """
        groups = rbac_setup_resources[1]

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id(groups[0])
        assert len(response) == 1
        assert response[0].id == groups[0].id
        assert response[0].host_count >= 1

        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id(groups[1])
        assert len(response) == 1
        assert response[0].id == groups[1].id
        assert response[0].host_count == 0


class TestRBACGroupsNoReadPermission:
    def test_rbac_groups_no_read_permission_get_groups_list(
        self,
        no_read_permission_user_setup,
        rbac_setup_resources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4499

        metadata:
          requirements: inv-groups-get-list
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:read" permission can't get a list of groups
        """
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_non_org_admin.apis.groups.get_groups()

    def test_rbac_groups_no_read_permission_get_groups_by_id(
        self,
        no_read_permission_user_setup,
        rbac_setup_resources,
        host_inventory_non_org_admin,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-4500

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:read" permission can't get groups by ID
        """
        groups = rbac_setup_resources[1]

        for group in groups:
            with raises_apierror(
                403,
                "You don't have the permission to access the requested resource. "
                "It is either read-protected or not readable by the server.",
            ):
                host_inventory_non_org_admin.apis.groups.get_groups_by_id(group)
