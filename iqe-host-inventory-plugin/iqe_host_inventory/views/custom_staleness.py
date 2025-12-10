from iqe_platform_ui import BaseLoggedInPage
from taretto.ui.core import Text
from taretto.ui.core import View
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import Card
from widgetastic_patternfly5 import Modal
from widgetastic_patternfly5 import OptionsMenu
from widgetastic_patternfly5.ouia import Button as ButtonOUIA


class UpdateSettingModal(Modal):
    """Update organization level setting Modal"""

    _update = Button("Update")
    _cancel = Button("Cancel")

    @property
    def update(self):
        if self._update.is_displayed:
            return self._update

    @property
    def cancel(self):
        if self._cancel.is_displayed:
            return self._cancel


class OrganizationLevelSettings(Card):
    """Organization level system staleness and deletion settings card"""

    title = Text('.//h4[@id="HostTitle"]')
    edit = ButtonOUIA("edit-staleness-setting")
    save_button = Button("Save")
    cancel_button = Button("Cancel")
    reset_setting = Button(locator=".//button[@data-ouia-component-id='reset-to-default']")
    stale = OptionsMenu(locator='.//button[@data-ouia-component-id="SystemStalenessDropdown"]/..')
    stale_warning = OptionsMenu(
        locator='.//button[@data-ouia-component-id="SystemStaleWarningDropdown"]/..'
    )
    deletion = OptionsMenu(
        locator='.//button[@data-ouia-component-id="SystemDeletionDropdown"]/..'
    )

    @property
    def _is_enabled(self):
        """Check is account settings are enabled"""
        return self.save_button.is_displayed and self.cancel_button.is_displayed

    def enable_edit(self):
        """Enable edit for account settings"""
        if not self._is_enabled:
            self.edit.click()

    def disable_edit(self):
        """Disable edit for account settings"""
        if self._is_enabled:
            self.edit.click()

    def save(self):
        if self.save_button.is_displayed:
            self.save_button.click()

    def cancel(self):
        if self.cancel_button.is_displayed:
            self.cancel_button.click()

    def default_setting_selected(self):
        """Check if default settings are selected"""
        return (
            self.stale.read() == "1 day"
            and self.stale_warning.read() == "7 days"
            and self.deletion.read() == "30 days"
        )

    def reset(self):
        return self.reset_setting.click()

    @View.nested
    class rbac(View):
        """Custom staleness page with staleness:read permission"""

        edit_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-disabled')]"
        )

        @property
        def edit_disabled(self):
            return self.edit_button.is_displayed

    @property
    def is_displayed(self):
        return self.title.text == "Organization level system staleness and deletion"


class StalenessAndDeletionPage(BaseLoggedInPage):
    """The Staleness and Deletion page"""

    title = Text('.//h1[@widget-type="InsightsPageHeaderTitle"]')
    organization_level_card = OrganizationLevelSettings()
    update_setting_modal = UpdateSettingModal()

    @View.nested
    class no_access(View):
        """The Staleness and Deletion page without staleness:read permission"""

        _old_title = Text(locator=".//h5[contains(@class, '-c-title')]")
        _title = Text(locator=".//h5[contains(@class, '-c-empty-state__title-text')]")

        @property
        def title(self):
            if self._old_title.is_displayed:
                return self._old_title
            elif self._title.is_displayed:
                return self._title

        @property
        def is_displayed(self):
            return "Access permissions needed" in self.title.text

    @property
    def is_displayed(self):
        """Is this view being displayed?"""
        return self.title.text == "Staleness and Deletion"
