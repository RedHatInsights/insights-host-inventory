"""Sentaku Contextual Methods for Systems"""

from iqe.base.application.implementations.rest import ViaREST

from iqe_host_inventory.entities.systems import System


@ViaREST.register_method_for(System.delete, ViaREST)
def delete(self):
    """Delete a host."""
    self.parent.rest_api_entity.api_host_delete_host_by_id([self.id])


@ViaREST.register_method_for(System.update, ViaREST)
def update(self, **update_details):
    """
    Update a host via the REST interface (HostsApi).

    For example,
    .. code:: python
        host = app.host_inventory.collections.systems.instantiate_with_id(uuid)
        host.update(
            display_name="A testing host",
            ansible_host="A testing host"
        )

    """

    if update_details.get("display_name"):
        self.parent.rest_api_entity.api_host_patch_host_by_id(
            [self.id], {"display_name": update_details.get("display_name")}
        )

    if update_details.get("ansible_host"):
        self.parent.rest_api_entity.api_host_patch_host_by_id(
            [self.id], {"ansible_host": update_details.get("ansible_host")}
        )

    # update the attrs of the host
    for attrib, value in update_details.items():
        setattr(self, attrib, value)
