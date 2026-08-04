# mypy: disallow-untyped-defs

import logging

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBACResources
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]

logger = logging.getLogger(__name__)


@pytest.fixture(
    params=[
        # TODO: Uncomment this when https://redhat.atlassian.net/browse/RHINENG-25822 is fixed
        # lf("host_inventory_rbac_groups_write"),
        lf("host_inventory_rbac_inv_admin"),
        lf("host_inventory_rbac_groups_admin"),
        lf("host_inventory_rbac_groups_all"),
    ],
    scope="class",
)
def host_inventory_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_hosts_admin"),
        lf("host_inventory_rbac_hosts_viewer"),
        lf("host_inventory_rbac_hosts_write"),
        lf("host_inventory_rbac_hosts_all"),
        lf("host_inventory_rbac_groups_viewer"),
        lf("host_inventory_rbac_all_read"),
        lf("host_inventory_rbac_no_perms"),
    ],
    scope="class",
)
def host_inventory_no_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


class TestRBACGroupsWritePermission:
    def test_rbac_groups_write_permission_create_group(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4392

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can create a group
        """
        group_name = generate_display_name()

        group = host_inventory_write_permissions.apis.groups.create_group(
            group_name,
            hosts=hbi_upload_prepare_host_class,
            wait_for_created=False,
            register_for_cleanup=False,
        )

        @request.addfinalizer
        def cleanup() -> None:
            # The non org admin user doesn't have read permissions, so it wouldn't be able to
            # verify if the cleanup was successful, so we need to use an org admin in a custom
            # finalizer for the group cleanup
            host_inventory.apis.groups.delete_groups(group)

        host_inventory.apis.groups.verify_updated(
            group, name=group_name, hosts=hbi_upload_prepare_host_class
        )

    def test_rbac_groups_write_permission_patch_group(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4438

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can patch a group
        """
        host1 = hbi_upload_prepare_host_class
        host2 = host_inventory.upload.create_host()
        original_group_name = generate_display_name()
        new_group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(original_group_name, hosts=host1)

        host_inventory_write_permissions.apis.groups.patch_group(
            group, name=new_group_name, hosts=host2, wait_for_updated=False
        )

        host_inventory.apis.groups.verify_updated(group, name=new_group_name, hosts=host2)

    def test_rbac_groups_write_permission_delete_group(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4393

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can delete a group
        """
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(
            group_name, hosts=hbi_upload_prepare_host_class
        )

        host_inventory_write_permissions.apis.groups.delete_groups(group, wait_for_deleted=False)
        host_inventory.apis.groups.verify_deleted(group)

    def test_rbac_groups_write_permission_remove_hosts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4394

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can remove hosts from a group
        """
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(
            group_name, hosts=hbi_upload_prepare_host_class
        )

        host_inventory_write_permissions.apis.groups.remove_hosts_from_group(
            group, hosts=hbi_upload_prepare_host_class, wait_for_removed=False
        )

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])

    def test_rbac_groups_write_permission_remove_hosts_from_multiple_groups(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
    ) -> None:
        """
        https://issues.redhat.com/browse/RHINENG-1655

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can
                 remove hosts from multiple groups via DELETE /groups/hosts/<host_ids> endpoint
        """
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(
            group_name, hosts=hbi_upload_prepare_host_class
        )

        host_inventory_write_permissions.apis.groups.remove_hosts_from_multiple_groups(
            hbi_upload_prepare_host_class, wait_for_removed=False
        )

        host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])

    def test_rbac_groups_write_permission_add_hosts(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_write_permissions: ApplicationHostInventory,
        hbi_upload_prepare_host_class: HostOut,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4377

        metadata:

          assignee: fstavela
          importance: high
          title: Test that users with "groups:write" permission can add hosts to a group
        """
        group_name = generate_display_name()
        group = host_inventory.apis.groups.create_group(group_name)

        host_inventory_write_permissions.apis.groups.add_hosts_to_group(
            group, hosts=hbi_upload_prepare_host_class, wait_for_added=False
        )

        @request.addfinalizer
        def cleanup() -> None:
            # The class cleanup deletes the group first, then the host is immediately deleted.
            # However, there is a small window when the host doesn't belong to any group in Kessel,
            # so the host deletion fails. If we remove the host from group, it will be part of the
            # ungrouped_hosts group and it will work fine.
            host_inventory.apis.groups.remove_hosts_from_group(
                group, hbi_upload_prepare_host_class
            )

        host_inventory.apis.groups.verify_updated(
            group, name=group_name, hosts=[hbi_upload_prepare_host_class]
        )


class TestRBACGroupsNoWritePermission:
    def test_rbac_groups_no_write_permission_create_group(
        self,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4392

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't create a group
        """
        group_name = generate_display_name()
        with raises_apierror(403):
            host_inventory_no_write_permissions.apis.groups.create_group(
                group_name, wait_for_created=False
            )

        host_inventory.apis.groups.verify_not_created(group_name=group_name)

    def test_rbac_groups_no_write_permission_patch_group(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4438
        https://issues.redhat.com/browse/RHINENG-18151

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't patch a group
        """
        hosts = rbac_setup_resources.hosts
        group = rbac_setup_resources.groups[0]
        new_group_name = generate_display_name()

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_no_write_permissions.apis.groups.patch_group(
                group, name=new_group_name, hosts=hosts[-1][0].id, wait_for_updated=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts[0])

    def test_rbac_groups_no_write_permission_delete_group(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4393

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't delete a group
        """
        groups = rbac_setup_resources.groups

        for group in groups:
            with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
                host_inventory_no_write_permissions.apis.groups.delete_groups_raw(group)

            host_inventory.apis.groups.verify_not_deleted(group)

    def test_rbac_groups_no_write_permission_remove_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4394
        https://issues.redhat.com/browse/RHINENG-18151

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't remove hosts from a group
        """
        group = rbac_setup_resources.groups[0]
        hosts = rbac_setup_resources.hosts[0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_no_write_permissions.apis.groups.remove_hosts_from_group(
                group, hosts=hosts[0].id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts)

    def test_rbac_groups_no_write_permission_remove_hosts_from_multiple_groups(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/RHINENG-1655
        https://issues.redhat.com/browse/RHINENG-18151

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't
                 remove hosts from multiple groups via DELETE /groups/hosts/<host_ids> endpoint
        """
        group = rbac_setup_resources.groups[0]
        hosts = rbac_setup_resources.hosts[0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_no_write_permissions.apis.groups.remove_hosts_from_multiple_groups(
                hosts[0].id, wait_for_removed=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=hosts)

    def test_rbac_groups_no_write_permission_add_hosts(
        self,
        rbac_setup_resources: RBACResources,
        host_inventory: ApplicationHostInventory,
        host_inventory_no_write_permissions: ApplicationHostInventory,
    ) -> None:
        """
        https://issues.redhat.com/browse/ESSNTL-4377

        metadata:

          assignee: fstavela
          importance: high
          negative: true
          title: Test that users without "groups:write" permission can't add hosts to a group
        """
        group = rbac_setup_resources.groups[-1]
        host = rbac_setup_resources.hosts[-1][0]

        with raises_apierror(
            403,
            "You don't have the permission to access the requested resource. "
            "It is either read-protected or not readable by the server.",
        ):
            host_inventory_no_write_permissions.apis.groups.add_hosts_to_group(
                group, hosts=host.id, wait_for_added=False
            )

        host_inventory.apis.groups.verify_not_updated(group, name=group.name, hosts=[])
