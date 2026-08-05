# mypy: disallow-untyped-defs

from __future__ import annotations

from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.cert_auth,
]


@pytest.mark.usefixtures("rbac_inventory_admin_user_setup_class")
class TestRBACGroupsCertAuth:
    def test_rbac_groups_cert_auth_bypass_checks_create_group(
        self,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't create group with cert auth
        """
        group_name = generate_display_name()

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.create_group(
                generate_display_name(), wait_for_created=False
            )

        host_inventory.apis.groups.verify_not_created(group_name)

    def test_rbac_groups_cert_auth_bypass_checks_patch_group(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't patch group with cert auth
        """
        group = rbac_setup_resources.groups[0]
        new_group_name = generate_display_name()

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.patch_group(
                group, name=new_group_name, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name)

    def test_rbac_groups_cert_auth_bypass_checks_delete_group(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't delete group with cert auth
        """
        group = rbac_setup_resources.groups[0]

        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin_cert_auth.apis.groups.delete_groups_raw(group)

        host_inventory.apis.groups.verify_not_deleted(group)

    def test_rbac_groups_cert_auth_bypass_checks_remove_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't remove hosts from group with cert auth
        """
        group = rbac_setup_resources.groups[0]
        host = rbac_setup_resources.hosts[0][0]

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.remove_hosts_from_group(
                group, hosts=host.id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, hosts=host.id)

    def test_rbac_groups_cert_auth_bypass_checks_remove_hosts_from_multiple_groups(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't remove hosts from multiple groups with cert auth
        """
        group = rbac_setup_resources.groups[0]
        host = rbac_setup_resources.hosts[0][0]

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.remove_hosts_from_multiple_groups(
                host.id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, hosts=host.id)

    def test_rbac_groups_cert_auth_bypass_checks_add_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't add hosts to group with cert auth
        """
        group = rbac_setup_resources.groups[-1]
        host = rbac_setup_resources.hosts[-1][0]

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.add_hosts_to_group(
                group, hosts=host.id, wait_for_added=False
            )

        host_inventory.apis.groups.verify_not_updated(group, hosts=[])

    @pytest.mark.usefixtures("rbac_setup_resources")
    def test_rbac_groups_cert_auth_bypass_checks_get_groups_list(
        self,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't get group list with cert auth
        """
        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.get_groups()

    def test_rbac_groups_cert_auth_bypass_checks_get_groups_by_id(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-5262

        metadata:
          assignee: fstavela
          importance: medium
          negative: true
          title: Test that you can't get groups by IDs with cert auth
        """
        groups = rbac_setup_resources.groups

        with raises_apierror(
            403, "You don't have the permission to access the requested resource"
        ):
            host_inventory_non_org_admin_cert_auth.apis.groups.get_groups_by_id(groups)


def test_rbac_granular_groups_cert_auth_bypass_checks_get_groups_by_id(
    hbi_non_org_admin_user_rbac_setup: Any,
    rbac_setup_resources: RBACResources,
    host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
) -> None:
    """
    https://issues.redhat.com/browse/ESSNTL-5262

    metadata:
      assignee: fstavela
      importance: medium
      negative: true
      title: Test that granular RBAC doesn't work on Groups endpoints with cert auth
    """
    # Setup
    groups = rbac_setup_resources.groups
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[groups[0]]
    )

    # Test
    with raises_apierror(403, "You don't have the permission to access the requested resource"):
        host_inventory_non_org_admin_cert_auth.apis.groups.get_groups_by_id(groups)
