from time import sleep

from iqe_platform_ui import BaseLoggedInPage
from iqe_platform_ui.utils.mixins import GlobalTags
from iqe_platform_ui.utils.mixins import SearchableTableMixin
from iqe_platform_ui.widgetastic_iqe import HoverText
from taretto.ui.core import Checkbox
from taretto.ui.core import Text
from taretto.ui.core import TextInput
from taretto.ui.core import View
from wait_for import wait_for
from widgetastic.exceptions import NoSuchElementException
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import Dropdown
from widgetastic_patternfly5 import Modal
from widgetastic_patternfly5 import Pagination
from widgetastic_patternfly5 import PatternflyTable
from widgetastic_patternfly5 import Tab
from widgetastic_patternfly5.ouia import Button as ButtonOUIA

from iqe_host_inventory.views.inventory_table import InventorySystemsTable
from iqe_host_inventory.widgetastic_host_inventory import BulkSelect
from iqe_host_inventory.widgetastic_host_inventory import InventoryLinks


class CreateWorkspaceModal(Modal):
    """Create workspace modal, triggered by clicking the "Create workspace" button"""

    _edit = TextInput(locator=".//input[@id='name']")
    _create = Button("Create")
    _cancel = Button("Cancel")

    @property
    def edit(self):
        if self._edit.is_displayed:
            return self._edit

    @property
    def create(self):
        if self._create.is_displayed:
            return self._create

    @property
    def cancel(self):
        if self._cancel.is_displayed:
            return self._cancel


class RenameWorkspaceModal(Modal):
    """Rename workspace modal, triggered by clicking the "Rename" button"""

    _edit = TextInput(locator=".//input[@type='text']")
    _save = Button("Save")
    _cancel = Button("Cancel")

    @property
    def edit(self):
        if self._edit.is_displayed:
            return self._edit

    @property
    def save(self):
        if self._save.is_displayed:
            return self._save

    @property
    def cancel(self):
        if self._cancel.is_displayed:
            return self._cancel


class DeleteWorkspaceModal(Modal):
    """Delete workspace modal, triggered by clicking the "Delete" button"""

    _content = Text(locator='.//div[contains(@class, "-c-content")]')
    _delete = Button("Delete")
    _cancel = Button("Cancel")

    @property
    def delete(self):
        if self._delete.is_displayed:
            return self._delete

    @property
    def cancel(self):
        if self._cancel.is_displayed:
            return self._cancel

    @property
    def content(self):
        if self._content.is_displayed:
            return self._content.text


class CannotDeleteWorkspaceModal(Modal):
    """
    Cannot delete workspace modal, triggered by clicking the "Delete" button
    when workspace has systems
    """

    _content = Text(locator='.//div[contains(@class, "-c-modal-box__body")]')
    _close = Button("Close")

    @property
    def close(self):
        if self._close.is_displayed:
            return self._close

    @property
    def content(self):
        if self._content.is_displayed:
            return self._content.text


class AddSystemsToWorkspaceModal(Modal, InventorySystemsTable):
    """Add systems modal, triggered by clicking the "Add systems" button
    on Workspace's Systems tab
    """

    _add_systems_button = Button("Add systems")
    _cancel = Button("Cancel")

    def add(self):
        if self._add_systems_button.is_displayed:
            self._add_systems_button.click()

    def cancel(self):
        if self._cancel.is_displayed:
            self._cancel.click()

    @property
    def is_displayed(self):
        return self.title == "Add systems"


class RemoveSystemFromWorkspaceModal(Modal):
    """Remove host from workspace modal, triggered by clicking the
    "Remove from workspace" button"""

    _content = Text(locator='.//div[contains(@class, "-c-content")]')
    _remove = Button("Remove")
    _cancel = Button("Cancel")

    @property
    def remove(self):
        if self._remove.is_displayed:
            return self._remove

    @property
    def cancel(self):
        if self._cancel.is_displayed:
            return self._cancel

    @property
    def content(self):
        if self._content.is_displayed:
            return self._content.text


class WorkspacesPage(BaseLoggedInPage, SearchableTableMixin, GlobalTags):
    """The inventory workspaces page"""

    EMPTY_STATE = './/div[contains(@class, "-c-empty-state__body")]'
    title = Text('.//h1[@widget-type="InsightsPageHeaderTitle"]')
    no_access = Text(locator=".//h5[contains(@class, '-c-title')]")
    learn_about_system_workspaces_link = Button("Learn more about system workspaces")
    create_workspace_ouia = ButtonOUIA("CreateGroupButton")
    _reset_filter_ouia = ButtonOUIA("ClearFilters")
    workspace_actions = Dropdown(locator=".//button[@aria-label='kebab dropdown toggle']/..")
    bulk_select = BulkSelect()
    bottom_paginator = Pagination(
        locator=".//div[contains(@class, '-c-pagination') and contains(@class, 'pf-m-bottom')]"
    )
    top_paginator = Pagination(
        locator=".//div[contains(@class, '-c-pagination') and contains(@class, 'pf-m-compact')]"
    )
    find_input_box = TextInput(locator='.//input[@placeholder="Filter by name"]')
    table = PatternflyTable(
        locator=".//table[@data-ouia-component-id='groups-table']",
        column_widgets={
            0: Checkbox(locator=".//input[@type='checkbox']"),
            "Name": Text(locator=".//a"),
            "Total systems": Text(locator=".//td[@data-label='Total systems']"),
            "Last modified": Text(locator=".//span"),
            4: Dropdown(locator=".//button[@type='button']/.."),
        },
    )

    delete_workspace_modal = DeleteWorkspaceModal()
    cannot_delete_workspace_modal = CannotDeleteWorkspaceModal()
    rename_workspace_modal = RenameWorkspaceModal()
    create_workspace_modal = CreateWorkspaceModal()

    @View.nested
    class rbac(View):
        """Workspaces page with groups:read permission has disabled workspaces's actions"""

        create_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled')]"
        )
        delete_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), 'Delete workspace')]"
        )
        rename_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), 'Rename workspace')]"
        )

        @property
        def rename_disabled(self):
            return self.rename_button.is_displayed

        @property
        def delete_disabled(self):
            return self.delete_button.is_displayed

        @property
        def create_disabled(self):
            return self.create_button.is_displayed

        @property
        def workspace_actions_disabled(self):
            return self.rename_button.is_displayed and self.delete_button.is_displayed

    @property
    def is_empty_state(self):
        """Check if workspaces page is empty"""
        if self.title.text == "Workspaces":
            try:
                return bool(self.browser.element(self.EMPTY_STATE))
            except NoSuchElementException:
                return False

    def search(self, name):
        if self.find_input_box.is_displayed:
            self.find_input_box.fill(name)
            wait_for(lambda: self.bottom_paginator.is_displayed, timeout=20)

    @property
    def create_workspace(self):
        if self.create_workspace_ouia.is_displayed:
            return self.create_workspace_ouia

    def reset_filters(self):
        if self._reset_filter_ouia.is_displayed:
            return self._reset_filter_ouia.click()

    def refresh_page(self):
        if self.is_displayed:
            self.browser.refresh()
            sleep(4)

    @property
    def is_displayed(self):
        return self.title.text == "Workspaces"


class WorkspacesPageEmptyState(BaseLoggedInPage):
    """Basic page for the empty state when user doesn't have groups permissions"""

    title = Text('.//h1[@widget-type="InsightsPageHeaderTitle"]')
    no_access = Text(locator=".//h5[contains(@class, '-c-empty-state__title-text')]")

    @property
    def is_displayed(self):
        return (
            "Workspace access permissions needed" in self.no_access.text
            and self.title.text == "Workspaces"
        )

    def refresh_page(self):
        if self.is_displayed:
            self.browser.refresh()
            sleep(4)


class WorkspacePage(BaseLoggedInPage):
    """The details page of a workspace"""

    title = Text('.//h1[@widget-type="InsightsPageHeaderTitle"]')
    add_systems_button = Button("Add systems")
    workspace_actions = Dropdown(locator=".//button[@id='group-dropdown-toggle']/..")
    no_access = Text(locator=".//h5[contains(@class, '-c-empty-state__title-text')]")

    delete_workspace_modal = DeleteWorkspaceModal()
    rename_workspace_modal = RenameWorkspaceModal()
    cannot_delete_workspace_modal = CannotDeleteWorkspaceModal()

    @View.nested
    class systems(Tab):
        TAB_NAME = "Systems"

    @View.nested
    class workspace_info(Tab):
        TAB_NAME = "Workspace info"

    @View.nested
    class rbac(View):
        """Workspace page with groups:read permissions has disabled workspace's actions"""

        add_systems_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled')]"
        )

        manage_access_button = Button(
            locator=".//a[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled') and contains(text(), 'Manage access')]"
        )
        _workspace_actions = Button(
            locator=".//button[contains(@data-ouia-component-id, 'group-actions-dropdown-toggle')"
            " and contains(@class, 'pf-m-disabled')]"
        )

        @property
        def add_systems_disabled(self):
            return self.add_systems_button.is_displayed

        @property
        def manage_access_disabled(self):
            return self.manage_access_button.is_displayed

        @property
        def workspace_actions_disabled(self):
            return self._workspace_actions.is_displayed

    @property
    def hosts_perms_exist(self):
        """Check if uesr has access to systems table"""
        return self.add_systems_button.is_displayed

    @property
    def title_is_correct(self):
        workspace_name = self.context["object"].name
        return self.title.is_displayed and self.title.text == workspace_name

    @property
    def is_displayed(self):
        return (
            self.workspace_info.is_displayed
            and self.systems.is_displayed
            and self.title_is_correct
        )

    def refresh_page(self):
        if self.is_displayed:
            self.browser.refresh()
            sleep(4)


class WorkspaceUserAccessLink(InventoryLinks):
    """Widget for link to User Access from workspace Info tab"""

    ITEMS_LOCATOR = ".//a[contains(@href, '/iam/user-access')]"


class WorkspaceInfoTab(WorkspacePage):
    """The Infor tab for workspace details page"""

    manage_access = Button("Manage access")
    user_access_links = WorkspaceUserAccessLink()

    @property
    def is_displayed(self):
        return (
            super().is_displayed
            and self.workspace_info.is_active()
            and self.manage_access.is_displayed
        )


class WorkspaceSystemsTab(WorkspacePage, InventorySystemsTable, GlobalTags):
    system_actions = Dropdown(locator=".//button[@aria-label='kebab dropdown toggle']/..")
    bulk_select = BulkSelect()
    add_systems_modal = AddSystemsToWorkspaceModal()
    remove_systems_modal = RemoveSystemFromWorkspaceModal()

    table = PatternflyTable(
        locator='.//div[contains(@class, "inventory-list")]//table',
        column_widgets={
            0: Checkbox(locator=".//input[@type='checkbox']"),
            "Name": Text(locator=".//a"),
            "Tags": Button(locator=".//button[@type='button']"),
            "OS": Text(locator=".//span"),
            "Last seen": HoverText(locator=".//span"),
            5: Dropdown(locator=".//button[@type='button']/.."),
        },
    )

    @View.nested
    class rbac(View):
        """Systems tab with groups:read permissions has disabled workspace's actions"""

        add_systems_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled')]"
        )

        _remove_from_workspace_button = Button(
            locator=".//li[contains(@class, 'c-menu__list-item') and "
            "contains(@class, 'pf-m-aria-disabled')]//span[contains(text(), "
            "'Remove from workspace')]"
        )

        @property
        def add_systems_disabled(self):
            return self.add_systems_button.is_displayed

        @property
        def remove_from_workspace_disabled(self):
            return self._remove_from_workspace_button.is_displayed

    @property
    def is_displayed(self):
        return super().is_displayed and self.systems.is_active()
