import logging
from collections.abc import Generator
from typing import NamedTuple

import pytest
from iqe_bindings.v7.rbac_v2 import WorkspacesCreateWorkspaceResponse

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import FORBIDDEN_OR_NOT_FOUND
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

"""
REVISIT: Kessel still requires a special setup for the EE (see below).

To run in the EE:

1. Run insights-service-deployer:
    - Clone https://github.com/project-kessel/insights-service-deployer
    - Run deploy.sh deploy_with_hbi_demo

2. Run the tests with --kessel option
"""

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]
logger = logging.getLogger(__name__)


class NestedWorkspaceResources(NamedTuple):
    parent_workspace: WorkspacesCreateWorkspaceResponse
    child_workspace: WorkspacesCreateWorkspaceResponse
    child_hosts: list[HostOut]
    other_group: GroupOutWithHostCount
    other_host: HostOut


@pytest.fixture(scope="module")
def nested_workspace_resources(
    host_inventory: ApplicationHostInventory,
) -> Generator[NestedWorkspaceResources]:
    """Set up a parent workspace with a nested child workspace containing hosts.

    Creates:
    - A parent workspace (and its corresponding HBI group)
    - A child workspace under the parent (and its corresponding HBI group)
    - 2 hosts assigned to the child workspace's group
    - A separate group with 1 host (not under the parent) for negative testing
    """
    parent_workspace = host_inventory.apis.workspaces.create_workspace(
        generate_display_name(), cleanup_scope="module"
    )

    child_workspace = host_inventory.apis.workspaces.create_workspace(
        generate_display_name(), parent_id=parent_workspace.id, cleanup_scope="module"
    )
    host_inventory.apis.groups.wait_for_created([parent_workspace.id, child_workspace.id])

    hosts = host_inventory.upload.create_hosts(3, cleanup_scope="module")
    child_hosts = hosts[:2]
    other_host = hosts[2]

    host_inventory.apis.groups.add_hosts_to_group(child_workspace.id, child_hosts)

    other_group = host_inventory.apis.groups.create_group(
        generate_display_name(), hosts=other_host, cleanup_scope="module"
    )

    yield NestedWorkspaceResources(
        parent_workspace=parent_workspace,
        child_workspace=child_workspace,
        child_hosts=child_hosts,
        other_group=other_group,
        other_host=other_host,
    )


@pytest.fixture(scope="class")
def nested_workspace_read_rbac_setup(
    nested_workspace_resources: NestedWorkspaceResources,
    hbi_non_org_admin_user_rbac_setup_class,
):
    parent_group_id = nested_workspace_resources.parent_workspace.id
    child_group_id = nested_workspace_resources.child_workspace.id
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_READ, RBACInventoryPermission.GROUPS_READ],
        hbi_groups=[parent_group_id],
        expected_hbi_groups=[parent_group_id, child_group_id],
    )


@pytest.fixture(scope="class")
def nested_workspace_write_rbac_setup(
    nested_workspace_resources: NestedWorkspaceResources,
    hbi_non_org_admin_user_rbac_setup_class,
):
    parent_group_id = nested_workspace_resources.parent_workspace.id
    child_group_id = nested_workspace_resources.child_workspace.id
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[
            RBACInventoryPermission.HOSTS_READ,
            RBACInventoryPermission.HOSTS_WRITE,
            RBACInventoryPermission.GROUPS_READ,
            RBACInventoryPermission.GROUPS_WRITE,
        ],
        hbi_groups=[parent_group_id],
        expected_hbi_groups=[parent_group_id, child_group_id],
    )


class TestNestedWorkspaceReadPermissions:
    def test_kessel_rbac_nested_workspace_hosts_read(
        self,
        nested_workspace_resources: NestedWorkspaceResources,
        nested_workspace_read_rbac_setup,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            assignee: fstavela
            importance: high
            title: Test that hosts:read permission on a parent workspace grants read access
              to hosts in the child workspace via GET /hosts and GET /hosts/<host_id>
        """
        resources = nested_workspace_resources
        child_host_ids = {host.id for host in resources.child_hosts}

        # GET /hosts — only child hosts should be visible
        response = host_inventory_non_org_admin.apis.hosts.get_hosts_response()
        response_host_ids = {host.id for host in response.results}
        assert response_host_ids == child_host_ids

        # GET /hosts/<host_id> — child hosts should be accessible by ID
        response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(
            resources.child_hosts
        )
        response_host_ids = {host.id for host in response.results}
        assert response_host_ids == child_host_ids

        # GET /hosts/<host_id> — host outside parent workspace should be inaccessible
        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(resources.other_host)

        # Read-only user should NOT be able to edit a host in the child workspace
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                resources.child_hosts[0].id,
                display_name=generate_display_name(),
                wait_for_updated=False,
            )

        host_inventory.apis.hosts.verify_not_updated(
            resources.child_hosts[0], display_name=resources.child_hosts[0].display_name
        )

    def test_kessel_rbac_nested_workspace_groups_read(
        self,
        nested_workspace_resources: NestedWorkspaceResources,
        nested_workspace_read_rbac_setup,
        host_inventory: ApplicationHostInventory,
        host_inventory_non_org_admin: ApplicationHostInventory,
    ):
        """
        metadata:
            assignee: fstavela
            importance: high
            title: Test that groups:read permission on a parent workspace grants read access
              to the child workspace's group via GET /groups and GET /groups/<group_id>
        """
        resources = nested_workspace_resources
        expected_group_ids = {resources.parent_workspace.id, resources.child_workspace.id}

        # GET /groups — only parent and child workspace groups should be visible
        response = host_inventory_non_org_admin.apis.groups.get_groups_response()
        assert response.count == 2
        response_group_ids = {group.id for group in response.results}
        assert response_group_ids == expected_group_ids

        # GET /groups/<group_id> — child workspace's group should be accessible by ID
        response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(
            expected_group_ids
        )
        assert response.count == 2
        response_group_ids = {group.id for group in response.results}
        assert response_group_ids == expected_group_ids

        # GET /groups/<group_id> — group outside parent workspace should be inaccessible
        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(
                resources.other_group
            )

        # Read-only user should NOT be able to rename the child workspace's group
        with raises_apierror(403):
            host_inventory_non_org_admin.apis.groups.patch_group(
                resources.child_workspace.id,
                name=generate_display_name(),
                wait_for_updated=False,
            )

        host_inventory.apis.groups.verify_not_updated(
            resources.child_workspace.id, name=resources.child_workspace.name
        )


class TestNestedWorkspaceWritePermissions:
    def test_kessel_rbac_nested_workspace_hosts_write(
        self,
        nested_workspace_resources: NestedWorkspaceResources,
        nested_workspace_write_rbac_setup,
        host_inventory_non_org_admin: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        metadata:
            assignee: fstavela
            importance: high
            title: Test that hosts:write permission on a parent workspace grants write access
              to hosts in the child workspace
        """
        resources = nested_workspace_resources

        # The non-admin user should be able to edit a host in the child workspace
        host = resources.child_hosts[0]
        new_name = generate_display_name()
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
        host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_name)

        # The non-admin user should NOT be able to edit the host outside the parent workspace
        other_new_name = generate_display_name()
        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.hosts.patch_hosts(
                resources.other_host.id, display_name=other_new_name, wait_for_updated=False
            )
        host_inventory.apis.hosts.verify_not_updated(
            resources.other_host.id, display_name=resources.other_host.display_name
        )

    def test_kessel_rbac_nested_workspace_groups_write(
        self,
        nested_workspace_resources: NestedWorkspaceResources,
        nested_workspace_write_rbac_setup,
        host_inventory_non_org_admin: ApplicationHostInventory,
        host_inventory: ApplicationHostInventory,
    ):
        """
        metadata:
            assignee: fstavela
            importance: high
            title: Test that groups:write permission on a parent workspace grants write access
              to the child workspace's group
        """
        resources = nested_workspace_resources

        # The non-admin user should be able to rename the child workspace's group
        child_group = host_inventory.apis.groups.get_group_by_id(resources.child_workspace.id)
        new_name = generate_display_name()
        host_inventory_non_org_admin.apis.groups.patch_group(
            child_group, name=new_name, wait_for_updated=False
        )
        host_inventory.apis.groups.verify_updated(child_group, name=new_name)

        # The non-admin user should NOT be able to rename the group outside the parent workspace
        other_new_name = generate_display_name()
        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.groups.patch_group(
                resources.other_group, name=other_new_name, wait_for_updated=False
            )
        host_inventory.apis.groups.verify_not_updated(
            resources.other_group, name=resources.other_group.name
        )
