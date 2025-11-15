# mypy: disallow-untyped-defs

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
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import GroupOut
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.service_account]


@pytest.fixture
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    return host_inventory.upload.create_hosts(2)


class TestRBACSAHostsWritePermission:
    def test_rbac_sa_hosts_write_permission_delete_host_by_id(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory: ApplicationHostInventory,
        host_inventory_sa_1: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:write" permission can delete hosts by IDs
        """
        group = rbac_setup_resources[1][0]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_sa_1.apis.hosts.delete_by_id_raw([host1, host2])
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_sa_hosts_write_permission_delete_hosts_filtered(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory: ApplicationHostInventory,
        host_inventory_sa_1: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:write" permission
                   can delete filtered hosts
        """
        group = rbac_setup_resources[1][0]
        prefix = f"iqe-hbi-delete-filtered_{generate_uuid()}"
        host1 = host_inventory.upload.create_host(display_name=f"{prefix}_{generate_uuid()}")
        host2 = host_inventory.upload.create_host(display_name=f"{prefix}_{generate_uuid()}")
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        host_inventory_sa_1.apis.hosts.delete_filtered(display_name=prefix)
        host_inventory.apis.hosts.wait_for_deleted([host1, host2])

    def test_rbac_sa_hosts_write_permission_patch_host_display_name(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory: ApplicationHostInventory,
        host_inventory_sa_1: ApplicationHostInventory,
        prepare_hosts: list[HostOut],
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            title: Test that service accounts with "hosts:write" permission
                   can patch host's display name
        """
        group = rbac_setup_resources[1][0]
        host1 = prepare_hosts[0]
        host2 = prepare_hosts[1]
        host_inventory.apis.groups.add_hosts_to_group(group, host1)

        new_display_name = generate_display_name()
        host_inventory_sa_1.apis.hosts.patch_hosts(host1, display_name=new_display_name)
        host_inventory.apis.hosts.wait_for_updated(host1, display_name=new_display_name)

        new_display_name = generate_display_name()
        host_inventory_sa_1.apis.hosts.patch_hosts(host2, display_name=new_display_name)
        host_inventory.apis.hosts.wait_for_updated(host2, display_name=new_display_name)


class TestRBACSAHostsNoWritePermission:
    def test_rbac_sa_hosts_no_write_permission_delete_host_by_id(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-by-id
            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:write" permission
                   can't delete hosts by IDs
        """
        hosts_ids = [host.id for host in rbac_setup_resources[0]]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.delete_by_id_raw(hosts_ids[0])

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.delete_by_id_raw(hosts_ids[1])

        host_inventory.apis.hosts.verify_not_deleted(hosts_ids)

    def test_rbac_sa_hosts_no_write_permission_delete_hosts_filtered(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-delete-filtered-hosts
            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:write" permission
                   can't delete filtered hosts
        """
        hosts = rbac_setup_resources[0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.delete_filtered(display_name=hosts[0].display_name)

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.delete_filtered(display_name=hosts[1].display_name)

        host_inventory.apis.hosts.verify_not_deleted(hosts)

    def test_rbac_sa_hosts_no_write_permission_patch_host_display_name(
        self,
        rbac_setup_resources: tuple[list[HostOut], list[GroupOut], list[list[TagDict]]],
        host_inventory_sa_2: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ) -> None:
        """
        JIRA: https://issues.redhat.com/browse/RHINENG-7891

        metadata:
            requirements: inv-hosts-patch
            assignee: fstavela
            importance: high
            negative: true
            title: Test that service accounts without "hosts:write" permission
                   can't patch host's display name
        """
        hosts = rbac_setup_resources[0]
        new_display_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.patch_hosts(hosts[0], display_name=new_display_name)

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_sa_2.apis.hosts.patch_hosts(hosts[1], display_name=new_display_name)

        host_inventory.apis.hosts.verify_not_updated(hosts[0], display_name=hosts[0].display_name)
        host_inventory.apis.hosts.verify_not_updated(hosts[1], display_name=hosts[1].display_name)
