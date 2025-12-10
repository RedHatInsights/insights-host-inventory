import logging

import pytest
from iqe_rbac_v2_api import ApiException as rbac_v2_exception
from iqe_rbac_v2_api import WorkspacesCreateWorkspaceResponse

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name

"""
REVISIT: Kessel still requires a special setup for the EE (see below).

To run in the EE:

1. Run insights-service-deployer:
    - Clone https://github.com/project-kessel/insights-service-deployer
    - Run deploy.sh deploy_with_hbi_demo

2. Run the tests with --kessel option
"""

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_kessel_get_ungrouped_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Verify the "ungrouped" group and workspace exist
    """
    groups = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")
    assert len(groups) == 1
    assert groups[0].name == "Ungrouped Hosts"
    assert groups[0].ungrouped is True

    # Verify it's retrievable by id as well
    groups = host_inventory.apis.groups.get_groups_by_id(groups[0].id)
    assert len(groups) == 1
    assert groups[0].name == "Ungrouped Hosts"

    workspaces = host_inventory.apis.workspaces.get_workspaces_by_id(groups[0].id)
    assert len(workspaces) == 1
    assert workspaces[0].name == groups[0].name


def test_kessel_create_empty_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Create an empty group and verify that a corresponding workspace is created
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    assert group.id
    assert group.name == group_name
    assert group.ungrouped is False

    host_inventory.apis.workspaces.wait_for_created(group.id)
    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace
    assert workspace.name == group_name


@pytest.mark.ephemeral
def test_kessel_get_groups_by_type(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Verify the GET /groups type param works correctly
    """
    group = host_inventory.apis.groups.create_group(generate_display_name())

    ungrouped_groups = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")
    assert len(ungrouped_groups) == 1
    assert ungrouped_groups[0].ungrouped is True

    standard_groups = host_inventory.apis.groups.get_groups(group_type="standard")
    assert len(standard_groups) == 1
    assert standard_groups[0].id == group.id
    assert standard_groups[0].ungrouped is False

    groups = host_inventory.apis.groups.get_groups(group_type="all")
    assert len(groups) == 2
    assert {groups[0].id, groups[1].id} == {ungrouped_groups[0].id, standard_groups[0].id}

    # default is "standard"
    groups = host_inventory.apis.groups.get_groups()
    assert len(groups) == 1
    assert groups[0].id == standard_groups[0].id


def test_kessel_create_group_with_hosts(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Create a group with hosts and verify that the corresponding workspace is correct
    """
    hosts = host_inventory.upload.create_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    assert group.id
    assert group.name == group_name
    assert group.host_count == 3
    assert group.ungrouped is False

    # Currently, there's no workspace host count.  I believe that will be a
    # phase 1 addition using kessel-inventory.
    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace.name == group_name


def test_kessel_rename_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Rename a group and verify that the corresponding workspace is renamed
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    assert group.id
    assert group.name == group_name

    host_inventory.apis.workspaces.wait_for_created(group.id)

    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace.name == group_name
    assert workspace.id == group.id

    updated_name = generate_display_name()
    group = host_inventory.apis.groups.patch_group(group, name=updated_name)
    assert group.name == updated_name

    workspace = host_inventory.apis.workspaces.get_workspace_by_id(workspace.id)
    assert workspace.name == updated_name


def test_kessel_delete_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Delete a group and verify that the corresponding workspace is deleted
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, register_for_cleanup=False)
    assert group.id
    assert group.name == group_name

    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace.name == group_name

    host_inventory.apis.groups.delete_groups(group)

    with pytest.raises(rbac_v2_exception) as err:
        host_inventory.apis.workspaces.get_workspace_by_id(workspace.id)
    assert err.value.status == 404
    assert "No Workspace matches the given query" in err.value.body


def test_kessel_add_hosts_to_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Test that a host is moved from ungrouped to grouped
    """
    initial_ungrouped_count = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[
        0
    ].host_count

    hosts = host_inventory.upload.create_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    assert group.id
    assert group.name == group_name

    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace.name == group_name

    group = host_inventory.apis.groups.add_hosts_to_group(group, hosts[:2])
    assert group.host_count == 2

    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response_hosts) == 2

    for host in response_hosts:
        assert host.groups[0].name == group.name
        assert host.groups[0].id == group.id

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    assert ungrouped_group.host_count == initial_ungrouped_count + 1

    response_host = host_inventory.apis.hosts.get_host_by_id(hosts[2])
    assert response_host.groups[0].name == ungrouped_group.name
    assert response_host.groups[0].id == ungrouped_group.id


def test_kessel_remove_hosts_from_group(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Test that a host is moved properly from grouped to ungrouped
    """
    initial_ungrouped_count = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[
        0
    ].host_count

    hosts = host_inventory.upload.create_hosts(3)
    host_ids = {host.id for host in hosts}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    assert group.id
    assert group.name == group_name

    workspace = host_inventory.apis.workspaces.get_workspace_by_id(group.id)
    assert workspace.name == group_name

    host_inventory.apis.groups.remove_hosts_from_group(group, hosts[:2])
    group = host_inventory.apis.groups.get_groups(name=group_name)[0]
    assert group.host_count == 1

    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response_hosts) == 1
    assert {response_hosts[0].id} == host_ids - {hosts[0].id, hosts[1].id}
    assert response_hosts[0].groups[0].name == group.name
    assert response_hosts[0].groups[0].id == group.id

    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]
    assert ungrouped_group.host_count == initial_ungrouped_count + 2

    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=["Ungrouped Hosts"])
    assert len(response_hosts) == initial_ungrouped_count + 2
    assert {response_hosts[0].id, response_hosts[1].id} == host_ids - {hosts[2].id}

    for host in response_hosts:
        assert host.groups[0].name == ungrouped_group.name
        assert host.groups[0].id == ungrouped_group.id


def test_kessel_create_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: low
      title: Attempt to create a group named Ungrouped Hosts
    """
    # This test makes more sense pre-migration when this group doesn't necessarily
    # exist.  Post-migration it's more of a group exists negative test.  We
    # can probably delete it once Kessel tests are integrated with groups' tests.
    with raises_apierror(
        400,
        "RBAC client error: Can't create workspace with same name within same parent workspace",
    ):
        host_inventory.apis.groups.create_group(name="Ungrouped Hosts")


def test_kessel_rename_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: low
      title: Attempt to rename the ungrouped group
    """
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    with raises_apierror(400, "The 'ungrouped' group can not be modified."):
        host_inventory.apis.groups.patch_group(group=ungrouped_group, name=generate_display_name())


def test_kessel_delete_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: low
      title: Attempt to delete the ungrouped group
    """
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    with raises_apierror(400, f"Ungrouped workspace {ungrouped_group.id} can not be deleted."):
        host_inventory.apis.groups.delete_groups_raw(ungrouped_group)


def test_kessel_remove_host_from_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: low
      title: Attempt to remove a host from the ungrouped group
    """
    host = host_inventory.upload.create_host()
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    with raises_apierror(
        400, f"Cannot remove hosts from ungrouped workspace {ungrouped_group.id}"
    ):
        host_inventory.apis.groups.remove_hosts_from_group(
            ungrouped_group, host.id, wait_for_removed=False
        )


def test_kessel_get_multiple_groups_with_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Get a list of groups that includes the ungrouped group
    """
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    assert group.id
    assert group.name == group_name

    # Get group plus the ungrouped group
    groups = host_inventory.apis.groups.get_groups_by_id([ungrouped_group.id, group.id])
    assert len(groups) == 2
    assert {groups[0].name, groups[1].name} == {"Ungrouped Hosts", group_name}


def test_kessel_delete_multiple_groups_with_ungrouped(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-groups
      assignee: msager
      importance: high
      title: Attempt to delete a list of groups that includes the ungrouped group
    """
    ungrouped_group = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")[0]

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    assert group.id
    assert group.name == group_name

    groups = [ungrouped_group, group]

    with raises_apierror(400, f"Ungrouped workspace {ungrouped_group.id} can not be deleted."):
        host_inventory.apis.groups.delete_groups_raw(groups)

    host_inventory.apis.groups.verify_not_deleted(groups)


def test_kessel_create_workspace(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-workspaces
      assignee: msager
      importance: high
      title: Verify that a new HBI group is created when I create a new workspace
    """
    workspace_name = generate_display_name()

    workspace = host_inventory.apis.workspaces.create_workspace(workspace_name)
    assert workspace

    host_inventory.apis.groups.wait_for_created(workspace.id)
    groups = host_inventory.apis.groups.get_groups(name=workspace_name)
    assert len(groups) == 1
    assert groups[0].ungrouped is False
    assert groups[0].name == workspace_name
    assert groups[0].id == workspace.id

    group = host_inventory.apis.groups.get_group_by_id(workspace.id)
    assert group.id == workspace.id
    assert group.name == workspace.name


def test_kessel_rename_workspace(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-workspaces
      assignee: msager
      importance: high
      title: Rename a workspace and verify the name change propagates to HBI
    """
    workspace_name = generate_display_name()

    workspace = host_inventory.apis.workspaces.create_workspace(workspace_name)
    assert workspace

    host_inventory.apis.groups.wait_for_created(workspace.id)
    groups = host_inventory.apis.groups.get_groups(name=workspace_name)
    assert len(groups) == 1
    assert groups[0].name == workspace_name
    assert groups[0].id == workspace.id

    updated_name = generate_display_name()

    updated_workspace = host_inventory.apis.workspaces.patch_workspace(
        workspace, name=updated_name
    )

    host_inventory.apis.groups.wait_for_updated(workspace.id, name=updated_name)
    groups = host_inventory.apis.groups.get_groups(name=updated_workspace.name)
    assert len(groups) == 1
    assert groups[0].name == updated_name
    assert groups[0].id == workspace.id


def test_kessel_delete_workspace(host_inventory: ApplicationHostInventory):
    """
    metadata:
      requirements: inv-kessel-workspaces
      assignee: msager
      importance: high
      title: Delete a workspace and verify the corresponding HBI group is deleted
    """
    workspace_name = generate_display_name()

    workspace = host_inventory.apis.workspaces.create_workspace(workspace_name)
    assert workspace

    host_inventory.apis.groups.wait_for_created(workspace.id)

    groups = host_inventory.apis.groups.get_groups(name=workspace_name)
    assert len(groups) == 1
    assert groups[0].name == workspace_name
    assert groups[0].id == workspace.id

    host_inventory.apis.workspaces.delete_workspaces(workspace)
    host_inventory.apis.groups.wait_for_deleted(groups[0].id)


@pytest.fixture(scope="module")
def setup_parent_workspaces(
    host_inventory: ApplicationHostInventory,
) -> list[WorkspacesCreateWorkspaceResponse]:
    workspaces = []

    for _ in range(2):
        workspace = host_inventory.apis.workspaces.create_workspace(
            generate_display_name(), cleanup_scope="module"
        )
        workspaces.append(workspace)

    host_inventory.apis.groups.wait_for_created([ws.id for ws in workspaces])

    return workspaces


def test_kessel_create_workspace_same_name(
    host_inventory: ApplicationHostInventory,
    setup_parent_workspaces: list[WorkspacesCreateWorkspaceResponse],
):
    """
    https://issues.redhat.com/browse/RHINENG-17234

    metadata:
      requirements: inv-kessel-workspaces, inv-kessel-groups
      assignee: msager
      importance: high
      title: Verify that creating groups with the same name, different parent is allowed
    """
    parent_workspaces = setup_parent_workspaces

    workspace_name = generate_display_name()

    # Create same-named child workspaces via the Kessel side.
    workspace = host_inventory.apis.workspaces.create_workspace(
        workspace_name, parent_id=parent_workspaces[0].id
    )
    assert workspace
    host_inventory.apis.groups.wait_for_created(workspace.id)

    # This will test kessel->hbi same named group, different parent acceptance
    workspace = host_inventory.apis.workspaces.create_workspace(
        workspace_name, parent_id=parent_workspaces[1].id
    )
    assert workspace
    host_inventory.apis.groups.wait_for_created(workspace.id)

    # We're doing a similar thing here, but from the HBI side.  Since HBI doesn't
    # have any notion of hierarchy, the parent in this case will be the Default
    # Workspace and this should succeed.
    group = host_inventory.apis.groups.create_group(workspace_name)
    assert group
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # At this point, we have 3 groups with the same name, but different
    # parents.
    groups = host_inventory.apis.groups.get_groups(name=workspace_name)
    assert len(groups) == 3
    assert all(group.name == workspace_name for group in groups)

    # Finally, we should get a duplicate name error here since we're attempting
    # to create a group with the same name within the Default Workspace
    with raises_apierror(
        400,
        "RBAC client error: Can't create workspace with same name within same parent workspace",
    ):
        host_inventory.apis.groups.create_group(workspace_name)


def test_kessel_update_workspace_same_name(
    host_inventory: ApplicationHostInventory,
    setup_parent_workspaces: list[WorkspacesCreateWorkspaceResponse],
):
    """
    https://issues.redhat.com/browse/RHINENG-17234

    metadata:
      requirements: inv-kessel-workspaces, inv-kessel-groups
      assignee: msager
      importance: high
      title: Verify that updating a group to the same name, different parent is allowed
    """
    parent_workspaces = setup_parent_workspaces

    workspace_1_name = generate_display_name()

    # Create same-named child workspaces via the Kessel side.
    workspace_1 = host_inventory.apis.workspaces.create_workspace(
        workspace_1_name, parent_id=parent_workspaces[0].id
    )
    assert workspace_1
    host_inventory.apis.groups.wait_for_created(workspace_1.id)

    workspace_2 = host_inventory.apis.workspaces.create_workspace(
        generate_display_name(), parent_id=parent_workspaces[1].id
    )
    assert workspace_2
    host_inventory.apis.groups.wait_for_created(workspace_2.id)

    # This will test kessel->hbi same named group, different parent acceptance
    updated_workspace = host_inventory.apis.workspaces.update_workspace(
        workspace_2, name=workspace_1_name, parent_id=parent_workspaces[1].id
    )
    assert updated_workspace
    host_inventory.apis.groups.wait_for_updated(workspace_2.id, name=workspace_1_name)

    # We're doing a similar thing here, but from the HBI side.  Since HBI doesn't
    # have any notion of hierarchy, the parent in this case will be the Default
    # Workspace and this should succeed.
    group_1 = host_inventory.apis.groups.create_group(generate_display_name())
    assert group_1
    host_inventory.apis.workspaces.wait_for_created(group_1.id)

    updated_group = host_inventory.apis.groups.patch_group(group_1, name=workspace_1_name)
    assert updated_group
    host_inventory.apis.workspaces.wait_for_updated(group_1.id, name=workspace_1_name)

    # At this point, we have 3 groups with the same name, but different
    # parents.
    groups = host_inventory.apis.groups.get_groups(name=workspace_1_name)
    assert len(groups) == 3
    assert all(group.name == workspace_1_name for group in groups)

    # Finally, we should get a duplicate name error here since we're attempting
    # to update a group with the same name within the Default Workspace

    group_2 = host_inventory.apis.groups.create_group(generate_display_name())
    assert group_2
    host_inventory.apis.workspaces.wait_for_created(group_2.id)

    with raises_apierror(
        400,
        f"RBAC client error: A workspace with the name '{workspace_1_name}' "
        "already exists under same parent.",
    ):
        host_inventory.apis.groups.patch_group(group_2, name=workspace_1_name)


def test_kessel_delete_parent_with_sub_workspaces(
    host_inventory: ApplicationHostInventory,
    setup_parent_workspaces: list[WorkspacesCreateWorkspaceResponse],
):
    """
    metadata:
      requirements: inv-kessel-workspaces, inv-kessel-groups
      assignee: msager
      importance: medium
      title: Verify that deleting a workspace with sub-workspaces isn't allowed
    """
    parent_workspaces = setup_parent_workspaces

    workspace = host_inventory.apis.workspaces.create_workspace(
        generate_display_name(), parent_id=parent_workspaces[0].id
    )
    assert workspace
    host_inventory.apis.groups.wait_for_created(workspace.id)

    with raises_apierror(400, "RBAC client error: Unable to delete due to workspace dependencies"):
        host_inventory.apis.groups.delete_groups_raw(parent_workspaces[0].id)
