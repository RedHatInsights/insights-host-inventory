"""UI RBAC tests for RHEL roles that grant access to RHEL Insights.

Testing only basic UI RBAC Inventory requiremnts to make sure
RHEL role has inventory permissions as expected (Inventory permissions have own separted tests).
RHEL operator and RHEL admin roles have same set of hbi permissions (read/write), RHEL viewer has
only read permsission.

https://issues.redhat.com/browse/RHINENG-16109
"""

# mypy: disallow-untyped-defs

from collections.abc import Generator

import pytest
from iqe.base.application.implementations.web_ui import navigate_to
from iqe.utils.blockers import iqe_blocker
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui, pytest.mark.rbac_dependent]


@iqe_blocker(iqe_blocker.jira("RHCLOUD-35891", category=iqe_blocker.PRODUCT_ISSUE, env=["prod"]))
@pytest.mark.parametrize(
    "role",
    [
        lf("setup_ui_user_with_rhel_admin_role"),
        lf("setup_ui_user_with_rhel_operator_role"),
        lf("setup_ui_user_with_rhel_viewer_role"),
    ],
    scope="function",
)
def test_rbac_inventory_ui_with_rhel_roles(
    host_inventory_frontend_non_org_admin: ApplicationHostInventory,
    systems_collection_non_org_admin: SystemCollection,
    workspaces_collection_non_org_admin: WorkspaceCollection,
    setup_ui_workspaces_with_hosts_for_sorting: Generator[list[GroupOutWithHostCount], None, None],
    setup_ui_host_module: HostOut,
    role: str,
) -> None:
    """
    Test that user with RHEL roles has required inventory permissions.
    RHEL admin and RHEL operator roles have inventory read and wrrite permissions.
    RHEL viewer has only inventory read permissions.

    https://issues.redhat.com/browse/RHINENG-16109

    metadata:
        importance: high
        requirements: inv-rbac
        assignee: zabikeno
        title: Test that user with RHEL roles has required inventory permissions
    """
    viewer = role == "RHEL viewer"

    # Systems page
    view = navigate_to(systems_collection_non_org_admin, "Systems")
    view.refresh_page()
    assert view.results != 0, "User should be able to see system with RHEL roles"

    # System's details page
    host = systems_collection_non_org_admin.instantiate_with_id(setup_ui_host_module.id)
    view = navigate_to(host, "SystemDetails")
    # check at least one hosts CRUD action to make sure user got all inventory persmissions

    if viewer:
        assert view.rbac.delete_system_disabled, (
            "Delete button should be disabled with RHEL viewer role"
        )
    else:
        assert not view.rbac.delete_system_disabled, (
            "Delete button should be enabled with RHEL admin/operator role"
        )

    # Workspaces page
    workspace, _, _ = setup_ui_workspaces_with_hosts_for_sorting
    view = navigate_to(workspaces_collection_non_org_admin, "All")
    # check at least one workspace CRUD action to make sure user got all inventory persmissions
    if viewer:
        assert view.rbac.create_disabled, (
            "'Create workspace' button should be disabled with RHEL viewer role"
        )
    else:
        assert not view.rbac.create_disabled, (
            "'Create workspace' button should be enabled with RHEL admin/operator role"
        )

    # Workspace's details page
    workspace = workspaces_collection_non_org_admin.instantiate_with_name(workspace.name)
    view = navigate_to(workspace, "SystemsTab")
    assert view.table.is_displayed, (
        "Workspace with systems table should be displayed with RHEL roles"
    )

    # Custom Staleness and Deletion page
    view = navigate_to(host_inventory_frontend_non_org_admin, "CustomStaleness")
    # check at least one staleness CRUD action to make sure user got all inventory persmissions
    if viewer:
        assert view.organization_level_card.rbac.edit_disabled, (
            "Edit button should be disabled with RHEL viewer role"
        )
    else:
        assert not view.organization_level_card.rbac.edit_disabled, (
            "Edit button should be enabled with RHEL admin/operator role"
        )
