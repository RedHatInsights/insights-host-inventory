# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.service_account]

logger = logging.getLogger(__name__)


class TestRBACSAGroupsReadPermission:
    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_groups_read_permission_get_groups_list(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        rbac_setup_resources: RBACResources,
        hbi_default_org_id: str,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:read" permission can get a list of groups
        """
        response = host_inventory_sa_1.apis.groups.get_groups()

        assert len(response) >= len(rbac_setup_resources.groups)
        for group in response:
            assert group.org_id == hbi_default_org_id

    def test_rbac_sa_groups_read_permission_get_groups_by_id(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:read" permission can get groups by ID
        """
        groups = rbac_setup_resources.groups

        response = host_inventory_sa_1.apis.groups.get_groups_by_id(groups[0])
        assert len(response) == 1
        assert response[0].id == groups[0].id
        assert response[0].host_count >= groups[0].host_count

        response = host_inventory_sa_1.apis.groups.get_groups_by_id(groups[-1])
        assert len(response) == 1
        assert response[0].id == groups[-1].id
        assert response[0].host_count == 0


class TestRBACSAGroupsNoReadPermission:
    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_sa_groups_no_read_permission_get_groups_list(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts users without "groups:read" permission
                 can't get a list of groups
        """
        with raises_apierror(403):
            host_inventory_sa_2.apis.groups.get_groups()

    def test_rbac_sa_groups_no_read_permission_get_groups_by_id(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_sa_2: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:read" permission can't get groups by ID
        """
        groups = rbac_setup_resources.groups

        for group in groups:
            with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
                host_inventory_sa_2.apis.groups.get_groups_by_id(group)
