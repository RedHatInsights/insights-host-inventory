"""
metadata:
  requirements: inv-rbac
"""

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import GroupOut
from iqe_host_inventory_api import HostOut

pytestmark = [
    pytest.mark.backend,
    pytest.mark.rbac_dependent,
    pytest.mark.service_account,
]

logger = logging.getLogger(__name__)


class TestRBACSAGroupsWritePermission:
    def test_rbac_sa_groups_write_permission_create_group(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-post
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission can create a group
        """
        host = hbi_upload_prepare_host_class
        group_name = generate_display_name()

        group = host_inventory_sa_1.apis.groups.create_group(
            group_name, hosts=host, wait_for_created=False
        )

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=host)

    def test_rbac_sa_groups_write_permission_patch_group(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission can patch a group
        """
        host1 = hbi_upload_prepare_host_class
        host2 = host_inventory.upload.create_host()
        original_group_name = generate_display_name()
        new_group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(original_group_name, hosts=host1)

        host_inventory_sa_1.apis.groups.patch_group(
            group, name=new_group_name, hosts=host2, wait_for_updated=False
        )

        host_inventory.apis.groups.verify_updated(group, name=new_group_name, hosts=host2)

    def test_rbac_sa_groups_write_permission_delete_group(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-delete
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission can delete a group
        """
        host = hbi_upload_prepare_host_class
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(group_name, hosts=host)

        host_inventory_sa_1.apis.groups.delete_groups(group, wait_for_deleted=False)
        host_inventory.apis.groups.verify_deleted(group)

    def test_rbac_sa_groups_write_permission_remove_hosts(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-remove-hosts
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission
                 can remove hosts from a group
        """
        host = hbi_upload_prepare_host_class
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(group_name, hosts=host)

        host_inventory_sa_1.apis.groups.remove_hosts_from_group(
            group, hosts=host, wait_for_removed=False
        )

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])

    def test_rbac_sa_groups_write_permission_remove_hosts_from_multiple_groups(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission can
                 remove hosts from multiple groups via DELETE /groups/hosts/<host_ids> endpoint
        """
        host = hbi_upload_prepare_host_class
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(group_name, hosts=host)

        host_inventory_sa_1.apis.groups.remove_hosts_from_multiple_groups(
            host, wait_for_removed=False
        )

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])

    def test_rbac_sa_groups_write_permission_add_hosts(
        self,
        host_inventory_sa_1: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-add-hosts
          assignee: fstavela
          importance: high
          title: Test that service accounts with "groups:write" permission can add hosts to a group
        """
        host = hbi_upload_prepare_host_class
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(group_name)

        host_inventory_sa_1.apis.groups.add_hosts_to_group(group, hosts=host, wait_for_added=False)

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[host])


class TestRBACSAGroupsNoWritePermission:
    def test_rbac_sa_groups_no_write_permission_create_group(
        self,
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-post
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission can't create a group
        """
        group_name = generate_display_name()
        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.groups.create_group(group_name, wait_for_created=False)

        host_inventory.apis.groups.verify_not_created(group_name=group_name)

    def test_rbac_sa_groups_no_write_permission_patch_group(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-patch
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission can't patch a group
        """
        hosts = rbac_setup_resources[0]
        group = rbac_setup_resources[1][0]
        new_group_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.groups.patch_group(
                group, name=new_group_name, hosts=hosts[1].id, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts[0].id)

    def test_rbac_sa_groups_no_write_permission_delete_group(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-delete
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission can't delete a group
        """
        groups = rbac_setup_resources[1]

        for group in groups:
            with raises_apierror((403, 404)):
                host_inventory_sa_2.apis.groups.delete_groups(group, wait_for_deleted=False)

            host_inventory.apis.groups.verify_not_deleted(group)

    def test_rbac_sa_groups_no_write_permission_remove_hosts(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-remove-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission
                 can't remove hosts from a group
        """
        group = rbac_setup_resources[1][0]
        host = rbac_setup_resources[0][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.groups.remove_hosts_from_group(
                group, hosts=host.id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=host.id)

    def test_rbac_sa_groups_no_write_permission_remove_hosts_from_multiple_groups(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-remove-hosts-multiple-groups
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission can't
                 remove hosts from multiple groups via DELETE /groups/hosts/<host_ids> endpoint
        """
        group = rbac_setup_resources[1][0]
        host = rbac_setup_resources[0][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.groups.remove_hosts_from_multiple_groups(
                host.id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=host.id)

    def test_rbac_sa_groups_no_write_permission_add_hosts(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
          requirements: inv-groups-add-hosts
          assignee: fstavela
          importance: high
          negative: true
          title: Test that service accounts without "groups:write" permission
                 can't add hosts to a group
        """
        group = rbac_setup_resources[1][1]
        host = rbac_setup_resources[0][1]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.groups.add_hosts_to_group(
                group, hosts=host.id, wait_for_added=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=[])
