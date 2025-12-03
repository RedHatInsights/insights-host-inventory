import contextlib

from iqe_platform_ui.utils.mixins import SearchableTableMixin
from taretto.ui.core import Checkbox
from taretto.ui.core import ParametrizedLocator
from taretto.ui.core import Text
from taretto.ui.core import TextInput
from taretto.ui.core import Widget
from widgetastic.exceptions import NoSuchElementException
from widgetastic.widget import ParametrizedView
from widgetastic_patternfly5 import Alert
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import Chip
from widgetastic_patternfly5 import ChipGroupToolbar
from widgetastic_patternfly5 import ChipGroupToolbarCategory
from widgetastic_patternfly5 import Menu
from widgetastic_patternfly5 import Modal
from widgetastic_patternfly5 import OptionsMenu
from widgetastic_patternfly5 import Pagination
from widgetastic_patternfly5 import PatternflyTable

GROUP_ROOT = ".//div[contains(@class, '-c-label-group__main')]"
NEW_TOOLBAR_GROUP_LABEL = ".//*[contains(@class, '-c-label-group__label')]"


class DefinitionList(Widget):
    ROOT = ParametrizedLocator("{@locator}")
    TERMS = ".//dt"
    TERM_BY_INDEX = ".//dt[{}]"
    DATAS = ".//dd"
    DATA_BY_INDEX = ".//dd[{}]"
    ACTION = ".//a[contains(@class, 'c-inventory__detail--action')]"

    def __init__(self, parent, locator, logger=None):
        Widget.__init__(self, parent, logger=logger)
        self.locator = locator

    def __locator__(self):
        return self.locator

    def __getitem__(self, key):
        return self.get_data_element(key).text

    @property
    def terms(self):
        term_list = []
        try:
            for elem in self.browser.elements(self.TERMS):
                term_list.append(elem.text.strip())
        except NoSuchElementException:
            pass
        return term_list

    @property
    def data(self):
        data_list = []
        try:
            for elem in self.browser.elements(self.DATAS):
                data_list.append(elem.text.strip())
        except NoSuchElementException:
            pass
        return data_list

    def get_data_element(self, term_name):
        for index, term in enumerate(self.terms):
            if term.lower().strip() == term_name.lower().strip():
                return self.browser.element(self.DATA_BY_INDEX.format(index + 1))
        raise KeyError(term_name)

    def get_action_element(self, term_name):
        data_element = self.get_data_element(term_name)
        return self.browser.element(self.ACTION, parent=data_element)

    def has_action(self, term_name):
        try:
            self.get_action_element(term_name)
            return True
        except (KeyError, NoSuchElementException):
            return False

    def click_action(self, term_name):
        element = self.get_action_element(term_name)
        element.click()


class InventoryLinks(Widget):
    """Widget for link to inventory"""

    ITEMS_LOCATOR = ".//div/a[contains(@href, 'inventory')]"

    def read(self):
        result = {}
        for index, el in enumerate(self.browser.elements(self.ITEMS_LOCATOR)):
            result[index] = el
        return result


class BulkSelect(Widget):
    """Widget to bulk select systems or groups"""

    SELECTED = ".//span[contains(@class,'-c-check__label')]"
    select_checkbox_groups = Checkbox(
        locator=".//input[@data-ouia-component-id='BulkSelectCheckbox']"
    )
    select_checkbox_systems = Checkbox(
        locator=".//input[@data-ouia-component-id='BulkSelectCheckbox']"
    )
    menu_systems_page = OptionsMenu(locator=".//button[@data-ouia-component-id='BulkSelect']/..")
    menu_groups_page = OptionsMenu(locator=".//button[@aria-label='groups-selector']/..")
    # TODO: Remove when issue OUIA are back https://issues.redhat.com/browse/RHINENG-15591
    menu_systems_page_new = Menu(
        locator="(.//div[contains(@class, 'ins-c-inventory__table--toolbar')]//button)[1]"
    )
    menu_groups_page_new = Menu(
        locator="(.//div[contains(@class, 'ins-c-primary-toolbar')]//button)[1]"
    )

    @property
    def menu(self):
        if self.menu_systems_page.is_displayed:
            return self.menu_systems_page
        elif self.menu_groups_page.is_displayed:
            return self.menu_groups_page
        elif self.menu_groups_page_new.is_displayed:
            return self.menu_groups_page_new
        elif self.menu_systems_page_new.is_displayed:
            return self.menu_systems_page_new

    @property
    def select_checkbox(self):
        if self.select_checkbox_groups.is_displayed:
            return self.select_checkbox_groups
        elif self.select_checkbox_systems.is_displayed:
            return self.select_checkbox_systems

    @property
    def count(self):
        selected = 0
        try:
            el_str = self.browser.element(self.SELECTED).text
            selected = int(el_str.split()[0])
        except NoSuchElementException:
            pass

        return selected

    def select(self):
        """Select page via checkbox"""
        self.select_checkbox.fill(True)

    def unselect(self):
        """Unselect page via checkbox"""
        self.select_checkbox.fill(False)

    def select_none(self):
        """Select none via menu"""
        self.menu.item_select("Select none (0 items)")

    def select_page(self, per_page):
        """Select page via menu"""
        items = "item" if per_page == 1 else "items"
        self.menu.item_select(f"Select page ({per_page} {items})")

    def select_all(self, all_systems):
        """Select all items via menu"""
        items = "item" if all_systems == 1 else "items"
        self.menu.item_select(f"Select all ({all_systems} {items})")


class TagsModal(Modal, SearchableTableMixin):
    """Class for tags modal in inventory"""

    COMPACT_PAGINATION = True
    table = PatternflyTable(
        locator='.//table[contains(@class, "c-tag-modal__table")]',
        column_widgets={
            "Name": Text(locator=".//a[@data-key='0']"),
            "Value": Text(locator=".//a[@data-key='1']"),
            "Tag Sources": Text(locator=".//a[@data-key='2']"),
        },
    )
    find_input_box = TextInput(locator='//input[@widget-type="InsightsInput"]')
    top_paginator = Pagination(
        locator=".//div[contains(@class, '-c-pagination') and contains(@class, 'pf-m-compact')]"
    )

    @property
    def is_displayed(self):
        return (
            super().is_displayed
            and self.find_input_box.__element__().get_attribute("placeholder") == "Filter tags"
        )

    @property
    def tag_count(self):
        return self.table.row_count


class TableFilterChipgroupCategory(ChipGroupToolbarCategory):
    """overridden ChipGroupToolbarCategory to work with inventory table filters"""

    ROOT = ParametrizedLocator(
        f"{GROUP_ROOT}[{NEW_TOOLBAR_GROUP_LABEL}[normalize-space(.)={{label|quote}}]]"
    )

    chips = ParametrizedView.nested(Chip)

    @classmethod
    def all(cls, browser):
        elements = []
        with contextlib.suppress(NoSuchElementException):
            elements = [
                (browser.text(el),)
                for el in browser.elements(f"{GROUP_ROOT}/{NEW_TOOLBAR_GROUP_LABEL}")
            ]

        return elements


class TableFilterChipgroup(ChipGroupToolbar):
    """overridden ChipGroupToolbar to work with inventory table chip filters"""

    groups = ParametrizedView.nested(TableFilterChipgroupCategory)
    TOOLBAR_LOCATOR = './/span[contains(@class, "c-chip-filters")]/div'


class InsightsClientReportingAlert(Alert):
    """Represents alert on the details page when system's insights-client is not reporting"""

    COMMAND = './/div[contains(@class, "-c-clipboard-copy__expandable-conten")]'
    show_content = Button(locator='//button[@aria-label="Show content"]')

    def is_open(self):
        try:
            self.browser.element(self.COMMAND)
        except NoSuchElementException:
            return False
        return True

    @property
    def client_setup(self) -> str:
        if not self.is_open():
            self.show_content.click()
        el = self.browser.element(self.COMMAND)
        return self.browser.text(el)

    @property
    def is_displayed(self):
        return super().is_displayed and super().title == "Your insights-client is not reporting"


class CustomMenu(Menu):
    IS_ALWAYS_OPEN = False


class LastSeenMenu(CustomMenu):
    ROOT = ".//button[@aria-label='Options menu']/.."
