import time

from iqe_platform_ui.utils.mixins import SearchableTableMixin
from iqe_platform_ui.widgetastic_iqe import HoverText
from iqe_platform_ui.widgetastic_iqe.checkbox_select import OSCheckboxMenu
from iqe_platform_ui.widgetastic_iqe.checkbox_select import SystemsGroupCheckboxSelect
from iqe_platform_ui.widgetastic_iqe.checkbox_select import SystemTagsCheckboxSelect
from taretto.ui.core import Checkbox
from taretto.ui.core import Text
from taretto.ui.core import TextInput
from wait_for import wait_for
from widgetastic.exceptions import NoSuchElementException
from widgetastic.widget import ConditionalSwitchableView
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import CheckboxSelect
from widgetastic_patternfly5 import Dropdown
from widgetastic_patternfly5 import PatternflyTable
from widgetastic_patternfly5.ouia import Button as ButtonOUIA
from widgetastic_patternfly5.ouia import Pagination as PaginationOUIA

from iqe_host_inventory.widgetastic_host_inventory import BulkSelect
from iqe_host_inventory.widgetastic_host_inventory import LastSeenMenu
from iqe_host_inventory.widgetastic_host_inventory import TableFilterChipgroup
from iqe_host_inventory.widgetastic_host_inventory import TagsModal


class InventorySystemsTable(SearchableTableMixin):
    """Class represents table with systems"""

    SEARCH_RELOADS_TABLE = True
    COMPACT_PAGINATION = True

    CHECKBOX_INDEX = 0
    ACTIONS_INDEX = 6
    PACKAGE_ICON_LOCATOR = ".//span[@aria-label='Package mode icon']"
    IMAGE_ICON_LOCATOR = ".//span[@aria-label='Image mode icon']"

    bulk_select = BulkSelect()
    tags_modal = TagsModal()

    system_actions = Dropdown(locator=".//button[@aria-label='kebab dropdown toggle']/..")
    export_button = Dropdown(locator=".//button[@aria-label='Export']/..")
    reset_filters_button = ButtonOUIA("ClearFilters")
    bottom_paginator = PaginationOUIA("bottom-pagination")
    delete_button = ButtonOUIA("bulk-delete-button")
    top_paginator = PaginationOUIA("CompactPagination")
    applied_filters = TableFilterChipgroup(locator='.//span[contains(@class, "c-chip-filters")]')
    text_input = TextInput(locator='//input[@widget-type="InsightsInput"]')
    # locators for last seen filter
    updated_start = TextInput(locator='.//input[@aria-label="Start date"]')
    updated_end = TextInput(locator='.//input[@aria-label="End date"]')
    filter_error = Text('.//div[contains(@class, "pf-m-error")]')

    table = PatternflyTable(
        locator=".//table[@aria-label='Host inventory']",
        column_widgets={
            CHECKBOX_INDEX: Checkbox(locator=".//input[@type='checkbox']"),
            "Name": Text(locator=".//a"),
            "Workspace": Text(locator=".//td"),
            "Tags": Button(locator=".//button[@type='button']"),
            "OS": Text(locator=".//span"),
            "Last seen": HoverText(locator=".//span"),
            ACTIONS_INDEX: Dropdown(locator=".//button[@type='button']/.."),
        },
    )
    checkbox_select_tag = SystemTagsCheckboxSelect(
        locator=(".//div[contains(@class, 'ins-c-tagfilter')]")
    )
    checkbox_select_workspace = SystemsGroupCheckboxSelect(
        locator="(.//div[contains(@class, 'ins-c-conditional-filter')]/div)[2]"
    )
    checkbox_select = CheckboxSelect(
        locator="(.//div[contains(@class, 'ins-c-conditional-filter')]/div)[2]"
    )
    # Various widgets defined based on column to filter on
    find_input_box = ConditionalSwitchableView(reference="column_selector")
    find_input_box.register(
        "Name", default=True, widget=TextInput(locator='//input[@widget-type="InsightsInput"]')
    )
    find_input_box.register("Status", widget=checkbox_select)
    find_input_box.register("Tags", widget=checkbox_select_tag)
    find_input_box.register("Operating system", widget=OSCheckboxMenu())
    find_input_box.register("Data collector", widget=checkbox_select)
    find_input_box.register("RHC status", widget=checkbox_select)
    find_input_box.register("System type", widget=checkbox_select)
    find_input_box.register("Workspace", widget=checkbox_select)
    find_input_box.register("Last seen", widget=LastSeenMenu())

    def export_to_csv(self):
        self.export_button.item_select("Export all systems to CSV")

    def export_to_json(self):
        self.export_button.item_select("Export all systems to JSON")

    def reset_filters(self):
        if self.reset_filters_button.is_displayed:
            self.reset_filters_button.click()

    def get_filters(self):
        """Grab a dict of the current filters, if any are applied"""
        try:
            return self.applied_filters.read()
        except NoSuchElementException:
            return {}

    def get_filters_list(self):
        """Turns the filter dict into list of filters"""
        tmp_filters = self.get_filters()
        return [val for sublist in tmp_filters.values() for val in sublist]

    def compare_table_headers(self, comparison_headers):
        """To compare state of table columns"""
        self.table.clear_cache()
        return self.table.headers == comparison_headers

    def refresh_page(self):
        if self.is_displayed:
            self.browser.refresh()
            wait_for(lambda: self.top_paginator.is_displayed, timeout=40)

    def get_systems_count_by_type(self) -> dict:
        """Get count of image and package type systems by veryfing number
        of image and package icons on current page.
        """
        result = {}
        system_types = {
            "Package-based system": self.PACKAGE_ICON_LOCATOR,
            "Image-based system": self.IMAGE_ICON_LOCATOR,
        }
        for mode, locator in system_types.items():
            try:
                result[mode] = len(list(self.browser.elements(locator)))
            except NoSuchElementException:
                result[mode] = 0

        return result

    def name_search(self, unique_id: str):
        """Help method when searching by unique id"""
        if self.text_input.is_displayed:
            self.text_input.fill(unique_id)
            time.sleep(2)

    def pagination_go_to_first_page(self):
        if not self.bottom_paginator.is_first_disabled and self.bottom_paginator.current_page != 1:
            self.bottom_paginator.first_page()
