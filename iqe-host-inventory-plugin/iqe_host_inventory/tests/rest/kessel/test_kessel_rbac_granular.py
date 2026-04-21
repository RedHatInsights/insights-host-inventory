import logging
from collections.abc import Generator
from typing import NamedTuple

import pytest
from iqe_rbac_v2_api import WorkspacesCreateWorkspaceResponse

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.rbac_fixtures import RBacResources
from iqe_host_inventory.utils import flatten
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


# These are essentially the same null group tests that live in test_rbac_granular_hosts.py
# and test_rbac_granular_groups.py.  The only difference is that we use the ungrouped
# group in the attributeFilter.  Continuing the theme of isolating kessel-specific
# tests under the kessel directory.  Once the migration is complete (Prod-deployed)
# and we no longer need the feature flag, we should integrate these tests into the
# proper modules.


def test_kessel_rbac_granular_hosts_read_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped group permissions can
          only access ungrouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[ungrouped_group]
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac[0])
    correct_hosts_ids = {host.id for host in rbac_setup_resources_for_granular_rbac[0][3]}
    other_hosts_ids = {host.id for host in hosts if host.id not in correct_hosts_ids}

    with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
        host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(correct_hosts_ids)
    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids

    if host_inventory.unleash.is_rbac_workspaces_enabled:
        for host_id in other_hosts_ids:
            with raises_apierror(403):
                host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(host_id)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped group can edit ungrouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][3][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host.id, display_name=new_name)

    # Teardown
    host_inventory.apis.hosts.patch_hosts(host.id, display_name=host.display_name)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped group can't edit grouped hosts
    """
    # Setup
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)


def test_kessel_rbac_granular_hosts_read_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can
          access correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac.groups
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_READ], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    hosts = flatten(rbac_setup_resources_for_granular_rbac.host_groups)
    correct_hosts_ids = {
        host.id
        for host in rbac_setup_resources_for_granular_rbac[0][0]
        + rbac_setup_resources_for_granular_rbac[0][3]
    }
    other_hosts_ids = {host.id for host in hosts if host.id not in correct_hosts_ids}

    with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
        host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(hosts)

    response = host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(correct_hosts_ids)

    response_hosts_ids = {host.id for host in response.results}
    assert response.count == len(correct_hosts_ids)
    assert response.total == len(correct_hosts_ids)
    assert response_hosts_ids == correct_hosts_ids

    if host_inventory.unleash.is_rbac_workspaces_enabled:
        for host_id in other_hosts_ids:
            with raises_apierror(403):
                host_inventory_non_org_admin.apis.hosts.get_hosts_by_id_response(host_id)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can edit
          correct hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    host1 = rbac_setup_resources_for_granular_rbac[0][0][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host1.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host1.id, display_name=new_name)

    host2 = rbac_setup_resources_for_granular_rbac[0][3][0]
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.hosts.patch_hosts(
        host2.id, display_name=new_name, wait_for_updated=False
    )
    host_inventory.apis.hosts.wait_for_updated(host2.id, display_name=new_name)

    # Teardown
    host_inventory.apis.hosts.patch_hosts(host1.id, display_name=host1.display_name)
    host_inventory.apis.hosts.patch_hosts(host2.id, display_name=host2.display_name)


def test_kessel_rbac_granular_hosts_write_permission_ungrouped_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped and normal groups can't edit
          incorrect hosts
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    host = rbac_setup_resources_for_granular_rbac[0][2][0]
    new_name = generate_display_name()
    with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
        host_inventory_non_org_admin.apis.hosts.patch_hosts(
            host.id, display_name=new_name, wait_for_updated=False
        )
    host_inventory.apis.hosts.verify_not_updated(host.id, display_name=host.display_name)


def test_rbac_granular_groups_read_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: fstavela
        importance: medium
        negative: true
        title: Test that users with granular RBAC ungrouped group can't access groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[ungrouped_group]
    )

    # Test
    with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
        host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups)


def test_rbac_granular_groups_write_permission_ungrouped_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: medium
        negative: true
        title: Test that users with granular RBAC ungrouped group can't edit groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[ungrouped_group]
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)


def test_rbac_granular_groups_read_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can access
          correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    response = host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(groups[0])
    assert response.count == 1
    assert response.total == 1
    assert len(response.results) == 1
    assert response.results[0].id == groups[0].id

    for group in groups[1:]:
        with raises_apierror(FORBIDDEN_OR_NOT_FOUND):
            host_inventory_non_org_admin.apis.groups.get_groups_by_id_response(group)


def test_rbac_granular_groups_write_permission_ungrouped_and_normal_group(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        title: Test that users with granular RBAC ungrouped and normal groups can edit
          correct groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_READ, RBACInventoryPermission.GROUPS_WRITE],
        hbi_groups=[groups[0], ungrouped_group],
    )

    # Test
    new_name = generate_display_name()
    host_inventory_non_org_admin.apis.groups.patch_group(
        groups[0], name=new_name, wait_for_updated=False
    )
    host_inventory.apis.groups.verify_updated(groups[0], name=new_name)

    # Teardown
    host_inventory.apis.groups.patch_group(groups[0], name=groups[0].name)


def test_rbac_granular_groups_write_permission_ungrouped_and_normal_group_wrong(
    rbac_setup_resources_for_granular_rbac: RBacResources,
    hbi_non_org_admin_user_rbac_setup,
    host_inventory_non_org_admin,
    host_inventory,
):
    """
    metadata:
        requirements: inv-kessel-rbac-ungrouped
        assignee: msager
        importance: high
        negative: true
        title: Test that users with granular RBAC ungrouped and normal groups can't edit
          incorrect groups
    """
    # Setup
    groups = rbac_setup_resources_for_granular_rbac[1]
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.GROUPS_WRITE], hbi_groups=[groups[0], ungrouped_group]
    )

    # Test
    new_name = generate_display_name()
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_non_org_admin.apis.groups.patch_group(
            groups[2], name=new_name, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(groups[2], name=groups[2].name)


# --- Nested workspace permission inheritance tests ---


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
            requirements: inv-kessel-rbac-nested-workspaces
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
            requirements: inv-kessel-rbac-nested-workspaces
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
            requirements: inv-kessel-rbac-nested-workspaces
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
            requirements: inv-kessel-rbac-nested-workspaces
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
