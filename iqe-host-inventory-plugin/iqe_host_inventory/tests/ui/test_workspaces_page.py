# mypy: disallow-untyped-defs

from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe.base.application.implementations.rest import ViaREST
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to

from iqe_host_inventory.entities.workspaces import Workspace
from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory.utils.ui_utils import UNIQUE_UI_ID
from iqe_host_inventory.utils.ui_utils import generate_workspace_name
from iqe_host_inventory.views.workspaces import WorkspacesPage
from iqe_host_inventory_api import GroupOutWithHostCount

pytestmark = [pytest.mark.ui]


@pytest.mark.core
def test_navigate_to_workspaces(
    workspaces_collection: WorkspaceCollection,
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    metadata:
        requirements: inv_ui-navigation
        importance: critical
        assignee: zabikeno
        title: Test that we can navigate to the Inventory Workspaces page
    """
    view = navigate_to(workspaces_collection, "All")
    assert view.is_displayed, "The Inventory Workspaces page was not visible after login"
    if view.is_empty_state:
        assert view.learn_about_system_workspaces_link.is_displayed
        assert view.create_workspace_button.is_displayed


@pytest.mark.core
def test_workspaces_ui_filter_by_name(
    workspaces_collection: WorkspaceCollection,
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
    request: pytest.FixtureRequest,
) -> None:
    """Test that we can filter the workspace table by name
    https://issues.redhat.com/browse/ESSNTL-4239
    metadata:
        requirements: inv-groups-get-list
        importance: critical
        assignee: zabikeno
    """
    view = navigate_to(workspaces_collection, "All")
    request.addfinalizer(view.reset_filters)

    view.search(setup_ui_empty_workspace_module.name)
    assert view.results == 1, "Filter should return 1 result"


@pytest.mark.core
@pytest.mark.parametrize("order", ["ascending", "descending"])
def test_workspaces_ui_sort_by_name(
    workspaces_collection: WorkspaceCollection,
    setup_ui_workspaces_with_hosts_for_sorting: Generator[list[GroupOutWithHostCount], None, None],
    order: str,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that sorting workspaces by Name column is working
    https://issues.redhat.com/browse/ESSNTL-4239
    metadata:
        requirements: inv-groups-get-by-id
        importance: high
        assignee: zabikeno
    """
    view = navigate_to(workspaces_collection, "All")
    request.addfinalizer(view.reset_filters)

    view.search(UNIQUE_UI_ID)
    view.table.sort_by(column="Name", order=order)
    sorted_names = [row.name.text.lower() for row in view.table.rows()]
    expected_sorted_names = sorted(sorted_names, reverse=(order == "descending"))

    assert len(sorted_names) == len(expected_sorted_names)
    assert sorted_names == expected_sorted_names, "Column 'Name' was not sorted as expected"


@pytest.mark.core
@pytest.mark.parametrize("order", ["ascending", "descending"])
def test_workspaces_ui_sort_by_total_systems(
    workspaces_collection: WorkspaceCollection,
    setup_ui_workspaces_with_hosts_for_sorting: Generator[list[GroupOutWithHostCount], None, None],
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
    order: str,
    request: pytest.FixtureRequest,
) -> None:
    """Test that sorting workspaces by Total systems column is working
    https://issues.redhat.com/browse/ESSNTL-4239
    metadata:
        requirements: inv-groups-get-by-id
        importance: medium
        assignee: zabikeno
    """
    view = navigate_to(workspaces_collection, "All")
    view.table.sort_by(column="Total systems", order=order)

    sorted_total_systems = [int(row.total_systems.text) for row in view.table.rows()]
    expected_sorted_total_systems = sorted(sorted_total_systems, reverse=(order == "descending"))

    assert len(sorted_total_systems) == len(expected_sorted_total_systems)
    assert sorted_total_systems == expected_sorted_total_systems, (
        "Column 'Total systems' was not sorted as expected"
    )


@pytest.mark.core
def test_workspaces_ui_rename_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    Test that user able to rename a workspace

    https://issues.redhat.com/browse/ESSNTL-4370

    metadata:
        requirements: inv-groups-patch
        importance: high
        assignee: zabikeno
    """
    workspace = setup_ui_empty_workspace_module
    new_name = workspace.name + "edit"

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.rename(new_name)

    view = hbi_application_frontend.web_ui.create_view(WorkspacesPage)
    view.search(new_name)
    filtered_workspace = [row.name.text for row in view.table.rows()]
    assert view.results == 1, "Filters should return 1 result"
    assert filtered_workspace[0] == new_name


@pytest.mark.core
def test_workspaces_ui_delete_single_empty_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that user able to delete workspace

    https://issues.redhat.com/browse/ESSNTL-4370

    metadata:
        requirements: inv-groups-delete
        importance: critical
        assignee: zabikeno
    """
    workspace = setup_ui_empty_workspace_module

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.delete()

    view = hbi_application_frontend.web_ui.create_view(WorkspacesPage)
    view.reset_filters()
    # check if exists
    view.search(workspace.name)
    assert view.results == 0, "Filters should return 0 result"


@pytest.mark.core
def test_workspaces_ui_bulk_delete_empty_workspaces(
    workspaces_collection: WorkspaceCollection,
    setup_ui_empty_workspaces: Generator[tuple[list[GroupOutWithHostCount], str], None, None],
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that user able to bulk delete workspaces

    https://issues.redhat.com/browse/ESSNTL-4367

    metadata:
        requirements: inv-groups-delete
        importance: critical
        assignee: zabikeno
    """
    workspaces, unique_id = setup_ui_empty_workspaces
    view = navigate_to(workspaces_collection, "All")
    request.addfinalizer(view.reset_filters)

    view.search(unique_id)
    view.bulk_select.select()
    assert view.bulk_select.count == len(workspaces)

    view.workspace_actions.item_select("Delete workspaces")
    assert (
        view.delete_workspace_modal.is_displayed
        and "Delete workspaces" in view.delete_workspace_modal.title
        and str(len(workspaces)) in view.delete_workspace_modal.content
    )
    view.delete_workspace_modal.delete.click()
    assert not view.delete_workspace_modal.is_displayed
    view.reset_filters()

    # check if exists
    view.search(unique_id)
    assert view.results == 0, "Filters should return 0 result"


@pytest.mark.core
def test_workspaces_ui_create_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    workspaces_collection: WorkspaceCollection,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that user able to create a workspace

     https://issues.redhat.com/browse/ESSNTL-3871

     metadata:
         requirements: inv-groups-post
         importance: critical
         assignee: zabikeno
    """
    with hbi_application_frontend.context.use(ViaWebUI):
        workspace = workspaces_collection.create(generate_workspace_name())

    def _cleanup() -> None:
        with hbi_application_frontend.context.use(ViaREST):
            workspace.delete()

    request.addfinalizer(_cleanup)

    view = hbi_application_frontend.web_ui.create_view(WorkspacesPage)
    # check if exists
    view.search(workspace.name)
    assert view.results == 1, "Filters should return 1 result"
