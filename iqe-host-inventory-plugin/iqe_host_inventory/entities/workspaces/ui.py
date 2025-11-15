import time

from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to

from iqe_host_inventory.entities.workspaces import Workspace
from iqe_host_inventory.entities.workspaces import WorkspaceCollection


@ViaWebUI.register_method_for(WorkspaceCollection.create, ViaWebUI)
def create(self, name: str):
    """Create a Workspace via UI"""
    modal_view = navigate_to(self, "CreateWorkspace")
    time.sleep(3)
    modal_view.edit.fill(name)
    modal_view.create.click()
    workspace = self.instantiate_with_name(name)

    return workspace


@ViaWebUI.register_method_for(Workspace.delete, ViaWebUI)
def delete(self, from_workspace_details=False):
    """Delete a Workspace via UI"""
    if from_workspace_details:
        modal_view = navigate_to(self, "DeleteFromWorkspaceDetails")
    else:
        modal_view = navigate_to(self, "DeleteWorkspace")
    assert self.name in modal_view.content
    modal_view.delete.click()


@ViaWebUI.register_method_for(Workspace.rename, ViaWebUI)
def rename(self, name: str, from_workspace_details=False):
    """Rename a Workspace via UI"""
    if from_workspace_details:
        modal_view = navigate_to(self, "RenameFromWorkspaceDetails")
    else:
        modal_view = navigate_to(self, "RenameWorkspace")
    modal_view.edit.fill(name)
    modal_view.save.click()
    self.name = name


@ViaWebUI.register_method_for(Workspace.add_systems, ViaWebUI)
def add_systems(self, systems: list[str]):
    """
    Add systems to workspace via UI

    .. code:: python
        workspace.add_systems([host1.display_name, host2.display_name])
    """
    modal_view = navigate_to(self, "AddSystemsToWorkspace")
    for system in systems:
        modal_view.search(system, column="Name")
        time.sleep(0.5)
        modal_view.bulk_select.select()
    modal_view.add()


@ViaWebUI.register_method_for(Workspace.remove_systems, ViaWebUI)
def remove_systems(self, systems: list[str], single_system=False):
    """
    Remove systems from workspace via UI

    .. code:: python
        workspace.remove_systems([host1.display_name, host2.display_name])

    """
    view = navigate_to(self, "SystemsTab")
    for system in systems:
        view.search(system, column="Name")
        if single_system:
            view.table.row()[5].widget.item_select("Remove from workspace")
        else:
            view.bulk_select.select()

    if not single_system:
        view.system_actions.item_select("Remove from workspace")

    view.remove_systems_modal.remove.click()
