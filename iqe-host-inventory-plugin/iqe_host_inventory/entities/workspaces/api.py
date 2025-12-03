from __future__ import annotations

from iqe.base.application.implementations.rest import ViaREST

from iqe_host_inventory.entities.workspaces import Workspace
from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory.modeling.hosts_api import HOST_OR_HOSTS


@ViaREST.register_method_for(Workspace.delete, ViaREST)
def delete(self):
    """Delete a workspace."""
    self.parent.groups_api_entity.delete_groups(self.id)


@ViaREST.register_method_for(Workspace.rename, ViaREST)
def rename(self: Workspace, name: str | None = None) -> None:
    """Rename a workspace."""
    if name is not None:
        self.parent.groups_api_entity.patch_group(self.id, name=name)
        self.name = name


@ViaREST.register_method_for(Workspace.add_systems, ViaREST)
def add_systems(self, systems: HOST_OR_HOSTS):
    """Add systems to a workspace."""
    self.parent.groups_api_entity.add_hosts_to_group(self.id, hosts=systems)


@ViaREST.register_method_for(Workspace.remove_systems, ViaREST)
def remove_systems(self, systems: HOST_OR_HOSTS):
    """Remove systems from a workspace."""
    self.parent.groups_api_entity.remove_hosts_from_group(self.id, hosts=systems)


@ViaREST.register_method_for(WorkspaceCollection.create, ViaREST)
def create(self, name: str, systems: HOST_OR_HOSTS | None = None, cleanup_scope: str = "function"):
    """
    Create a workspace via the REST interface (GroupApi).

    For example,
    .. code:: python
        workspace = application.host_inventory.collections.workspaces.create(
            "test-workspace-hbi",
            systems=[application.host_inventory.collections.workspaces.instantiate_with_id("uuid")],
        )
    """
    self.groups_api_entity.create_group(name, hosts=systems, cleanup_scope=cleanup_scope)
    workspace = self.instantiate_with_name(name)

    return workspace
