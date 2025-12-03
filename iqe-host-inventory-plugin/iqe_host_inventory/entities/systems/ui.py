from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to

from iqe_host_inventory.entities.systems import System


@ViaWebUI.register_method_for(System.delete, ViaWebUI)
def delete(self, from_systems_page=False):
    """Delete a host via UI"""
    if from_systems_page:
        view = navigate_to(self, "DeleteFromSystemsPage")
        view.delete.click()
    else:
        view = navigate_to(self, "Delete")
        view.delete.click()


def _update_from_systems_page(self, **update_details):
    """Helper method for 'update'"""
    view = navigate_to(self, "EditFromSystemsPage")
    view.edit.fill(update_details.get("display_name"))
    view.save.click()
    self.display_name = update_details["display_name"]


@ViaWebUI.register_method_for(System.update, ViaWebUI)
def update(self, from_systems_page=False, **update_details):
    """Update a host via UI"""
    if from_systems_page and update_details.get("display_name"):
        _update_from_systems_page(self, **update_details)
    else:
        if update_details.get("display_name"):
            view = navigate_to(self, "SystemInformation")
            view.enable_edit("Display name")
            view.save_editing.wait_displayed()
            view.edit_name_input.fill(update_details.get("display_name"))
            view.save_editing.click()
            self.display_name = update_details["display_name"]

        if update_details.get("ansible_host"):
            view = navigate_to(self, "SystemInformation")
            view.enable_edit("Ansible name")
            view.save_editing.wait_displayed()
            view.edit_name_input.fill(update_details.get("ansible_host"))
            view.save_editing.click()
            self.ansible_host = update_details["ansible_host"]
