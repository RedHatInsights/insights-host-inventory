from iqe_platform_ui import BaseLoggedInPage
from iqe_platform_ui.utils.mixins import GlobalTags
from taretto.ui.core import Text
from taretto.ui.core import TextInput
from taretto.ui.core import View
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import ExpandableTable
from widgetastic_patternfly5 import Modal
from widgetastic_patternfly5.ouia import Button as ButtonOUIA
from widgetastic_patternfly5.ouia import TextInput as TextInputOUIA
from widgetastic_patternfly5.ouia import Title as TitleOUIA

from iqe_host_inventory.views.inventory_table import InventorySystemsTable


class DeleteSystemModal(Modal):
    """Delete modal, triggered by clicking the "Delete" button"""

    delete = ButtonOUIA("confirm-inventory-delete")
    cancel = ButtonOUIA("cancel-inventory-delete")

    @property
    def is_displayed(self):
        return super().is_displayed and self.title in [
            "Warning alert: Delete system from inventory?",
            "Warning alert: Delete systems from inventory?",
        ]


class EditSystemNameModal(Modal):
    """Edit system name modal, triggered by clicking the "Edit" button"""

    title = Text(locator=".//h1[contains(@class, '-c-modal-box__title')]")
    _edit_ouia = TextInputOUIA("input-edit-display-name")
    _edit = TextInput(locator=".//input[@aria-label='input text']")
    _cancel_ouia = ButtonOUIA("cancel-edit-display-name")
    _cancel = Button(".//button[@type='cancel']")
    _save_ouia = ButtonOUIA("confirm-edit-display-name")
    _save = Button("Save")

    @property
    def edit(self):
        if self._edit_ouia.is_displayed:
            return self._edit_ouia
        else:
            return self._edit

    @property
    def cancel(self):
        if self._cancel_ouia.is_displayed:
            return self._cancel_ouia
        else:
            return self._cancel

    @property
    def save(self):
        if self._save_ouia.is_displayed:
            return self._save_ouia
        else:
            return self._save

    @property
    def is_displayed(self):
        return self.title.is_displayed


class SystemsPage(BaseLoggedInPage, GlobalTags, InventorySystemsTable):
    """The inventory systems page"""

    title = Text('.//h1[@widget-type="InsightsPageHeaderTitle"]')
    package_systems_view_button = Button(locator=".//button[@aria-label='View by systems']")
    images_view_button = Button(locator=".//button[@aria-label='View by images']")
    delete_system_modal = DeleteSystemModal()
    edit_system_modal = EditSystemNameModal()

    @View.nested
    class rbac(View):
        """Systems page with hosts:read/group:read permissions has
        disabled group's and system's actions"""

        bulk_delete_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled') and contains(text(), 'Delete')]"
        )
        delete_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), "
            "'Delete from inventory')]"
        )

        edit_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), 'Edit display name')]"
        )

        remove_from_workspace_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), "
            "'Remove from workspace')]"
        )

        add_to_workspace_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), 'Add to workspace')]"
        )

        @property
        def bulk_delete_disabled(self):
            return self.bulk_delete_button.is_displayed

        @property
        def workspace_actions_disabled(self):
            return (
                self.add_to_workspace_button.is_displayed
                and self.remove_from_workspace_button.is_displayed
            )

        @property
        def add_to_workspace_disabled(self):
            return self.add_to_workspace_button.is_displayed

        @property
        def remove_from_workspace_disabled(self):
            return self.remove_from_workspace_button.is_displayed

        @property
        def system_actions_disabled(self):
            return self.delete_button.is_displayed and self.edit_button.is_displayed

    @View.nested
    class image_view(View):
        table = ExpandableTable(
            locator=".//table[@aria-label='Bootc image table']",
            column_widgets={
                "Image name": Text(locator=".//td"),
                "Hash commits": Text(locator=".//td"),
                "Systems": Text(locator=".//td"),
            },
        )

        @property
        def is_displayed(self):
            return self.table.is_displayed

    @property
    def image_based_systems_are_present(self):
        """Account has image-based system"""
        return self.images_view_button.is_displayed

    def switch_to_images_view(self):
        """Switch to table with images"""
        if self.image_based_systems_are_present:
            self.images_view_button.click()

    def switch_to_systems_view(self):
        """Switch to table with systems"""
        if self.image_based_systems_are_present:
            self.package_systems_view_button.click()

    @property
    def is_displayed(self):
        """Is this view being displayed?"""
        return self.title.text == "Systems"


class SystemsPageEmptyState(BaseLoggedInPage):
    """Basic page for the empty state when user doesn't have inventory permissions"""

    no_access = Text(locator=".//h5[contains(@class, '-c-empty-state__title-text')]")

    @property
    def is_displayed(self):
        return "This application requires Inventory permissions" in self.no_access.text


class SystemsPageZeroState(BaseLoggedInPage):
    """Basic page for the zero state when user doesn't have any systems in an account"""

    title = TitleOUIA("ZeroStateCustomAppTitle")

    @property
    def is_displayed(self):
        return self.title.is_displayed


class FailedExportAlert(Exception):
    """Indicates that a export request was not succeed"""

    pass
