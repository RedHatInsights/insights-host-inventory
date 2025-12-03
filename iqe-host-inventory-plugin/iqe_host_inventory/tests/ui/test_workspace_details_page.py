# mypy: disallow-untyped-defs

import logging
from collections.abc import Generator

import fauxfactory
import pytest
from iqe.base.application import Application
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.workspaces import Workspace
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.views.workspaces import WorkspacePage
from iqe_host_inventory.views.workspaces import WorkspacesPage
from iqe_host_inventory.views.workspaces import WorkspaceSystemsTab
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui, pytest.mark.core]
logger = logging.getLogger(__name__)


@pytest.fixture
def systems_for_workspace(
    host_inventory_frontend: ApplicationHostInventory,
) -> tuple[list[HostOut], str]:
    unique_id = fauxfactory.gen_alpha()
    hosts_data = [HostData(display_name_prefix=unique_id) for _ in range(3)]
    systems = host_inventory_frontend.upload.create_hosts(hosts_data=hosts_data)

    return systems, unique_id


@pytest.mark.outage
def test_workspace_ui_navigation(
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    Test that we can navigate to the Workspace Details page
    https://issues.redhat.com/browse/ESSNTL-3872

    metadata:
        requirements: inv_ui-navigation
        importance: critical
        assignee: zabikeno
    """
    view = navigate_to(setup_ui_empty_workspace_module, "WorkspaceDetails")
    assert view.is_displayed
    assert view.title.text == setup_ui_empty_workspace_module.name


def test_workspace_ui_navigation_info_tab(
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    Test navigation to Workspace Info tab

    https://issues.redhat.com/browse/ESSNTL-3873

    metadata:
        requirements: inv_ui-navigation
        importance: critical
        assignee: zabikeno
    """
    view = navigate_to(setup_ui_empty_workspace_module, "InfoTab")
    assert view.is_displayed and view.workspace_actions.is_displayed


def test_workspace_ui_rename_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    Test that user able to rename workspace from Workspace details page

    https://issues.redhat.com/browse/ESSNTL-3878

    metadata:
        requirements: inv-groups-patch
        importance: high
        assignee: zabikeno
    """
    workspace = setup_ui_empty_workspace_module
    new_name = workspace.name + "edit"

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.rename(new_name, from_workspace_details=True)

    view = hbi_application_frontend.web_ui.create_view(WorkspacePage)
    assert view.title.text == new_name


def test_workspace_ui_delete_empty_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_empty_workspace_module: Generator[Workspace, None, None],
) -> None:
    """
    Test that user able to delete workspace
    https://issues.redhat.com/browse/ESSNTL-3879

    metadata:
        requirements: inv-groups-delete
        importance: critical
        assignee: zabikeno
    """
    workspace = setup_ui_empty_workspace_module
    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.delete(from_workspace_details=True)

    # when workspace is deleted from details it will redirect user to all workspaces page
    view = hbi_application_frontend.web_ui.create_view(WorkspacesPage)
    # check if exists
    view.search(workspace.name)
    assert view.results == 0, "Filters should return 0 result"


@pytest.mark.parametrize("single_system", [True, False], ids=["single-system", "multiple-systems"])
def test_workspace_ui_add_systems_to_empty_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_empty_workspace: Generator[tuple[Workspace, list[HostOut]], None, None],
    systems_for_workspace: tuple[list[HostOut], str],
    single_system: bool,
) -> None:
    """
    Test that we add systems to the empty workspace
    https://issues.redhat.com/browse/ESSNTL-3874

    metadata:
        requirements: inv-groups-add-hosts
        importance: high
        assignee: zabikeno
    """
    workspace = setup_ui_empty_workspace
    systems, unique_id = systems_for_workspace
    systems_to_add: list[str] = []
    if single_system:
        systems_to_add.append(systems[0].display_name)
    else:
        systems_to_add.append(unique_id)

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.add_systems(systems_to_add)

    view = hbi_application_frontend.web_ui.create_view(WorkspaceSystemsTab)
    # ensure systems now added in workspace
    view.browser.refresh()
    wait_for(lambda: view.top_paginator.is_displayed, timeout=20)
    view.name_search(systems_to_add[0])
    host_count = 1 if single_system else len(systems)
    row_count = list(view.table.rows())
    assert len(row_count) == host_count


def test_workspace_ui_global_tag_filter(
    host_inventory_frontend: ApplicationHostInventory,
    setup_ui_workspace_with_multiple_hosts: Generator[tuple[Workspace, list[HostOut]], None, None],
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that the global tag filter works as expected
    in workspace's details

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-tags
        importance: low
        assignee: zabikeno
    """
    workspace, systems = setup_ui_workspace_with_multiple_hosts
    response = host_inventory_frontend.apis.tags.get_tags(display_name=systems[0].display_name)
    tag = response[0].tag.to_dict()

    view = navigate_to(workspace, "SystemsTab")
    request.addfinalizer(view.clear_tags)
    row_count = list(view.table.rows())
    assert len(row_count) == len(systems), (
        f"Before filtering expecting {len(systems)} systems in workspace system table"
    )
    view.select_tags([tag])
    assert view.table.row_count == 1, (
        "After filtering expecting 1 system in workspace system table"
    )
    view.clear_tags()
    assert view.table.row_count


def test_workspace_ui_add_systems_to_not_empty_workspace(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_workspace_with_multiple_hosts: Generator[tuple[Workspace, list[HostOut]], None, None],
    systems_for_workspace: tuple[list[HostOut], str],
) -> None:
    """
    Test that we add systems to the workspace with systems

    metadata:
        requirements: inv-groups-add-hosts
        importance: high
        assignee: zabikeno
    """
    workspace, systems = setup_ui_workspace_with_multiple_hosts
    systems_to_add, unique_id = systems_for_workspace

    view = navigate_to(workspace, "SystemsTab")
    systems_before = [row.name.text.lower() for row in view.table.rows()]
    assert {system.display_name for system in list(systems)} == set(systems_before)

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.add_systems([unique_id])

    view.refresh_page()
    # ensure systems now added in workspace
    wait_for(lambda: view.top_paginator.is_displayed, timeout=20)
    systems_after = [row.name.text.lower() for row in view.table.rows()]

    assert {system.display_name for system in list(systems) + systems_to_add} == set(systems_after)


@pytest.mark.parametrize("single_system", [True, False], ids=("single-system", "multiple-systems"))
def test_workspace_ui_remove_systems(
    hbi_application_frontend: Generator[Application, None, None],
    setup_ui_workspace_with_multiple_hosts: Generator[tuple[Workspace, list[HostOut]], None, None],
    single_system: bool,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that user able to remove systems from workspace
    https://issues.redhat.com/browse/ESSNTL-3877

    metadata:
        requirements: inv-groups-remove-hosts
        importance: high
        assignee: zabikeno
    """
    workspace, _ = setup_ui_workspace_with_multiple_hosts

    view = navigate_to(workspace, "SystemsTab")
    assert view.table.is_displayed, "Workspace with systems always displays a table"
    systems_before = [row.name.text.lower() for row in view.table.rows()]

    systems_to_remove: list = []
    if single_system:
        systems_to_remove.append(systems_before.pop())
    else:
        systems_to_remove = systems_before[:2]

    with hbi_application_frontend.context.use(ViaWebUI):
        workspace.remove_systems(systems_to_remove, single_system=single_system)

    # ensure systems are removed from workspace
    view.reset_filters()
    view.refresh_page()

    if not view.table.is_displayed:
        logger.info("Workspace is empty. All systems are removed")
    else:
        systems_after = [row.name.text.lower() for row in view.table.rows()]
        assert all(system not in systems_after for system in systems_to_remove)
