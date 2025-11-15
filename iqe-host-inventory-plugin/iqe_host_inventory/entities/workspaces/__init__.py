from __future__ import annotations

import attr
import attrs
import sentaku
from iqe.base.application.implementations.rest import ViaREST
from iqe.base.application.implementations.web_ui import IQENavigateStep
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.modeling import BaseCollection
from iqe.base.modeling import BaseEntity
from sentaku import Element as SentakuElement
from taretto.navigate import NavigateToAttribute
from taretto.navigate import NavigateToSibling

from iqe_host_inventory.views.workspaces import AddSystemsToWorkspaceModal
from iqe_host_inventory.views.workspaces import CreateWorkspaceModal
from iqe_host_inventory.views.workspaces import DeleteWorkspaceModal
from iqe_host_inventory.views.workspaces import RenameWorkspaceModal
from iqe_host_inventory.views.workspaces import WorkspaceInfoTab
from iqe_host_inventory.views.workspaces import WorkspacePage
from iqe_host_inventory.views.workspaces import WorkspacesPage
from iqe_host_inventory.views.workspaces import WorkspacesPageEmptyState
from iqe_host_inventory.views.workspaces import WorkspaceSystemsTab


@attrs.define(slots=False)
class Workspace(BaseEntity, SentakuElement):
    """Workspace representation object"""

    parent: WorkspaceCollection
    name: str = attr.ib()
    id: str | None = attr.ib(default=None)
    account: str | None = attr.ib(default=None)
    org_id = attr.ib(default=None)
    host_count: int | None = attr.ib(default=None)
    created = attr.ib(default=None)
    updated = attr.ib(default=None)

    delete = sentaku.ContextualMethod()
    rename = sentaku.ContextualMethod()
    add_systems = sentaku.ContextualMethod()
    remove_systems = sentaku.ContextualMethod()

    @property
    def data(self):
        return self.parent.groups_api_entity.get_group_by_id(self.id)

    @property
    def workspace_ident(self):
        return self.name

    def fetch_info(self, name=True, host_count=True, updated=True):
        if name and self.data.name:
            self.name = self.data.name
        if host_count and self.data.host_count:
            self.host_count = self.data.host_count
        if updated and self.data.updated:
            self.updated = self.data.updated

    @property
    def exists(self):
        resp = self.parent.groups_api_entity.get_groups_by_id([self.id])
        return len(resp) == 1

    def delete_if_exists(self):
        if self.exists:
            with self.context.use(ViaREST):
                self.delete()


@attr.s
class WorkspaceCollection(BaseCollection, SentakuElement):
    ENTITY = Workspace

    create = sentaku.ContextualMethod()

    @property
    def groups_api_entity(self):
        return self.application.host_inventory.apis.groups

    def _instantiate_with_rest_data(self, group_data):
        return self.instantiate(
            id=group_data.id,
            name=group_data.name,
            account=group_data.account,
            org_id=group_data.org_id,
            host_count=group_data.host_count,
            created=group_data.created,
            updated=group_data.updated,
        )

    def instantiate_with_name(self, name):
        resp = self.groups_api_entity.get_groups_response(name=name, group_type="all")
        if resp.count == 1:
            group_data = resp.results[0]
            return self._instantiate_with_rest_data(group_data)


@ViaWebUI.register_destination_for(WorkspaceCollection, "All")
@ViaWebUI.register_destination_for(WorkspaceCollection, "Workspaces")
class Workspaces(IQENavigateStep):
    """Inventory Workspaces page step - skip steps to /insights"""

    VIEW = WorkspacesPage
    prerequisite = NavigateToAttribute("application.platform_ui", "BasePage")

    def step(self, *args, **kwargs):
        self.application.web_ui.widgetastic_browser.url = (
            self.application.platform_ui.base_address + "insights/inventory/workspaces"
        )


@ViaWebUI.register_destination_for(WorkspaceCollection, "InsightsWorkspaces")
class InsightsWorkspaces(IQENavigateStep):
    """Inventory Workspaces step via insights navbar"""

    VIEW = WorkspacesPage
    prerequisite = NavigateToAttribute("application.platform_ui", "Insights")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.prerequisite_view.navigation.select("Inventory", "Workspaces", force=True)


@ViaWebUI.register_destination_for(WorkspaceCollection, "WorkspacesEmptyState")
class WorkspacesEmptyState(IQENavigateStep):
    """Inventory step when Workspaces page is showing empty state"""

    VIEW = WorkspacesPageEmptyState
    prerequisite = NavigateToAttribute("application.platform_ui", "BasePage")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.application.web_ui.widgetastic_browser.url = (
            self.application.platform_ui.base_address + "insights/inventory/workspaces"
        )


@ViaWebUI.register_destination_for(Workspace, "WorkspaceDetails")
class WorkspaceDetails(IQENavigateStep):
    """Inventory Workspace Details step"""

    VIEW = WorkspacePage
    prerequisite = NavigateToAttribute(
        "application.host_inventory.collections.workspaces", "Workspaces"
    )

    def step(self, *args, **kwargs):
        self.prerequisite_view.search(self.obj.name)
        self.prerequisite_view.table.row().name.widget.click()


@ViaWebUI.register_destination_for(Workspace, "InfoTab")
class InfoTab(IQENavigateStep):
    """Inventory Workspace Info tab step"""

    VIEW = WorkspaceInfoTab
    prerequisite = NavigateToSibling("WorkspaceDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.workspace_info.select()


@ViaWebUI.register_destination_for(Workspace, "DeleteWorkspace")
class DeleteWorkspace(IQENavigateStep):
    """Step to Workspaces page and open delete modal for specific workspace"""

    VIEW = DeleteWorkspaceModal
    prerequisite = NavigateToAttribute(
        "application.host_inventory.collections.workspaces", "Workspaces"
    )

    def step(self, *args, **kwargs):
        self.prerequisite_view.search(self.obj.name)
        self.prerequisite_view.table.row()[4].widget.item_select("Delete workspace")


@ViaWebUI.register_destination_for(Workspace, "DeleteFromWorkspaceDetails")
class DeleteFromWorkspaceDetails(IQENavigateStep):
    """Step to Workspace Details page and open delete modal"""

    VIEW = DeleteWorkspaceModal
    prerequisite = NavigateToSibling("WorkspaceDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.workspace_actions.item_select("Delete workspace")


@ViaWebUI.register_destination_for(WorkspaceCollection, "CreateWorkspace")
class CreateWorkspace(IQENavigateStep):
    """Step to Workspaces page and open create modal"""

    VIEW = CreateWorkspaceModal
    prerequisite = NavigateToAttribute(
        "application.host_inventory.collections.workspaces", "Workspaces"
    )

    def step(self, *args, **kwargs):
        self.prerequisite_view.create_workspace.click()


@ViaWebUI.register_destination_for(Workspace, "RenameWorkspace")
class RenameWorkspace(IQENavigateStep):
    """Step to Workspaces page and open rename workspace modal for specific workspace"""

    VIEW = RenameWorkspaceModal
    prerequisite = NavigateToAttribute(
        "application.host_inventory.collections.workspaces", "Workspaces"
    )

    def step(self, *args, **kwargs):
        self.prerequisite_view.search(self.obj.name)
        self.prerequisite_view.table.row()[4].widget.item_select("Rename workspace")


@ViaWebUI.register_destination_for(Workspace, "RenameFromWorkspaceDetails")
class RenameFromWorkspaceDetails(IQENavigateStep):
    """Step to Workspace Details page and open rename workspace modal"""

    VIEW = RenameWorkspaceModal
    prerequisite = NavigateToSibling("WorkspaceDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.workspace_actions.item_select("Rename workspace")


@ViaWebUI.register_destination_for(Workspace, "SystemsTab")
class SystemsTab(IQENavigateStep):
    """Inventory Workspace with systems tab step"""

    VIEW = WorkspaceSystemsTab
    prerequisite = NavigateToSibling("WorkspaceDetails")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.prerequisite_view.systems.select()


@ViaWebUI.register_destination_for(Workspace, "AddSystemsToWorkspace")
class AddSystemsToWorkspace(IQENavigateStep):
    """Step to open Add systems modal in Workspace Details page"""

    VIEW = AddSystemsToWorkspaceModal
    prerequisite = NavigateToSibling("WorkspaceDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.add_systems_button.click()
