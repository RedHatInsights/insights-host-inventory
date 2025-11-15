from typing import ClassVar

from iqe_platform_ui import BaseLoggedInPage
from iqe_platform_ui.utils.mixins import GlobalTags
from iqe_platform_ui.widgetastic_iqe.tag_filter import TagFilter
from widgetastic_patternfly5 import Button

from iqe_host_inventory.widgetastic_host_inventory import InventoryLinks


class InsightsDashboardPage(BaseLoggedInPage, GlobalTags):
    """The Insights Dashboard page"""

    url_filters: ClassVar[dict[str, int]] = {
        "source=puptoo": 0,
        "status=stale&source=puptoo": 1,
        "status=stale_warning&source=puptoo": 2,
    }
    configure_integrations = Button(locator=".//a[contains(@href, 'settings/integrations')]")
    register_systems = Button(locator=".//div/a[contains(@href, 'insights/registration')]")
    inventory_links = InventoryLinks()

    filter_menu = TagFilter()

    @property
    def is_displayed(self):
        return self.configure_integrations.is_displayed and self.register_systems.is_displayed

    def redirect(self, url_filter):
        "Redirect to Inventory with given filter"
        links = self.inventory_links.read()
        return links[self.url_filters[url_filter]].click()

    def close_menu(self):
        if self.filter_menu.is_open:
            self.filter_menu.menu_toggle.click()
