# mypy: disallow-untyped-defs


import pytest
from iqe.base.application.implementations.web_ui import navigate_to

from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]


@pytest.fixture(scope="session")
def skip_kessel_if_disabled(enabled_ui_kessel: bool) -> None:
    if not enabled_ui_kessel:
        pytest.xfail("Kessel is not yet present in stage/prod enviroments")


@pytest.mark.core
@pytest.mark.usefixtures("skip_kessel_if_disabled")
def test_ungrouped_hosts_workspace_actions(
    workspaces_collection: WorkspaceCollection,
    setup_ui_host: HostOut,
    request: pytest.FixtureRequest,
) -> None:
    """Test 'Ungrouped Hosts' workspace

    metadata:
        requirements: inv-kessel-ungrouped
        importance: medium
        assignee: zabikeno
    """
    view = navigate_to(workspaces_collection, "All")
    request.addfinalizer(view.reset_filters)

    view.search("Ungrouped Hosts")
    assert view.results == 1, "Filter should return 1 result"

    view.table.row()[4].widget.open()
    assert view.rbac.workspace_actions_disabled, (
        "User shouldn't be able to delete/rename this workspace in Phase 0"
    )

    view.bulk_select.select()
    view.workspace_actions.open()
    assert view.rbac.delete_disabled, "User shouldn't be able to delete this workspace"


@pytest.mark.core
@pytest.mark.usefixtures("skip_kessel_if_disabled")
def test_ungrouped_hosts_workspace_details(
    workspaces_collection: WorkspaceCollection,
    setup_ui_host: HostOut,
    request: pytest.FixtureRequest,
) -> None:
    """Test 'Ungrouped Hosts' workspace

    metadata:
        requirements: inv-kessel-ungrouped
        importance: medium
        assignee: zabikeno
    """
    ungrouped_workspace = workspaces_collection.instantiate_with_name("Ungrouped Hosts")
    view = navigate_to(ungrouped_workspace, "SystemsTab")

    assert view.title.text == ungrouped_workspace.name, (
        "Title of workpsace should be 'Ungrouped Hosts'"
    )
    assert view.rbac.add_systems_disabled, "User shouldn't be able to rename workspace in Phase 0"
    assert view.table.is_displayed

    view.table.row()[5].widget.open()
    assert view.rbac.remove_from_workspace_disabled, (
        "User shouldn't be able to remove hosts from this workspace."
    )
    assert view.rbac.add_systems_disabled, (
        "User shouldn't be able to add hosts to this workspace.."
    )
