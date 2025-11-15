from iqe_platform_ui import BaseLoggedInPage
from iqe_platform_ui.utils import SearchableTableMixin
from iqe_platform_ui.widgetastic_iqe import HoverText
from iqe_platform_ui.widgetastic_iqe import InsightsAnsibleSupport
from taretto.ui.core import Text
from taretto.ui.core import TextInput
from taretto.ui.core import View
from widgetastic.exceptions import NoSuchElementException
from widgetastic.widget import Checkbox
from widgetastic_patternfly5 import Alert
from widgetastic_patternfly5 import Button
from widgetastic_patternfly5 import Card
from widgetastic_patternfly5 import Dropdown
from widgetastic_patternfly5 import ExpandableTable
from widgetastic_patternfly5 import Tab
from widgetastic_patternfly5.ouia import Button as ButtonOUIA
from widgetastic_patternfly5.ouia import Pagination as PaginationOUIA

from iqe_host_inventory.views.systems import EditSystemNameModal
from iqe_host_inventory.widgetastic_host_inventory import DefinitionList
from iqe_host_inventory.widgetastic_host_inventory import InsightsClientReportingAlert
from iqe_host_inventory.widgetastic_host_inventory import TableFilterChipgroup
from iqe_host_inventory.widgetastic_host_inventory import TagsModal


class SystemPage(BaseLoggedInPage):
    """The details page of a system"""

    LABEL_LOCATORS = './/span[contains(@class, "-c-label__text")]'
    actions = Dropdown("Actions")
    edit_system_modal = EditSystemNameModal()
    title = Text('.//h1[contains(@class, "-c-title")]')
    uuid = Text(
        locator='.//div[contains(@class, "entity-facts")]//div[contains(text(), "UUID")]'
        "/following-sibling::div"
    )
    last_seen = Text(
        locator='.//div[contains(@class, "entity-facts")]//div[contains(text(), '
        '"Last seen")]/following-sibling::div'
    )

    tags = Button(locator='.//button[contains(@class, "buttonTagCount")]')
    tags_modal = TagsModal()
    delete = Button("Delete")
    centos_alert = Alert(locator='.//div[@data-ouia-component-id="OUIA-Generated-Alert-custom-1"]')
    alert = InsightsClientReportingAlert(
        locator='.//div[@data-ouia-component-id="OUIA-Generated-Alert-custom-1"]'
    )

    @property
    def title_is_correct(self):
        system_ident = self.context["object"].system_ident
        return self.title.is_displayed and self.title.text == system_ident

    @property
    def system_labels(self):
        try:
            return [el.text for el in self.browser.elements(self.LABEL_LOCATORS)]
        except NoSuchElementException:
            return []

    @property
    def is_displayed(self):
        return self.title_is_correct

    @View.nested
    class rbac(View):
        """System's details page with hosts:read/group:read permissions has
        disabled system's actions"""

        delete_button = Button(
            locator=".//button[contains(@class, '-c-button') and "
            "contains(@class, 'pf-m-aria-disabled') and contains(text(), 'Delete')]"
        )

        @property
        def delete_system_disabled(self):
            return self.delete_button.is_displayed

    @View.nested
    class vulnerability(Tab):
        TAB_NAME = "Vulnerability"

    @View.nested
    class advisor(Tab):
        TAB_NAME = "Advisor"

    @View.nested
    class patch(Tab):
        TAB_NAME = "Patch"

    @View.nested
    class compliance(Tab):
        TAB_NAME = "Compliance"

    @View.nested
    class general_info(Tab):
        TAB_NAME = "General information"


class SystemInformationSection(Card):
    """Represents card with system information"""

    title = Text(".//div[contains(@class, '-l-stack__item')]//h1")
    details = DefinitionList(locator=".//div[contains(@class, '-l-stack__item')]//dl")  # type: ignore[call-arg]


class SystemInformationTab(SystemPage):
    """The General information of system"""

    WORKSPACE_LINK_LOCATOR = ".//dd[contains(@data-ouia-component-id, 'Workspace value')]"
    EDIT_BUTTON_LOCATORS = ".//button[@aria-label='Edit']"
    system_properties = SystemInformationSection(
        ".//h1[contains(text(), 'System properties')]/../../.."
    )
    edit_name_input = TextInput(locator=".//input[@type='text']")
    cancel_editing = Button(locator=".//button[@aria-label='cancel']")
    save_editing = Button(locator=".//div/button[@aria-label='submit']")
    operating_system = SystemInformationSection(
        ".//h1[contains(text(), 'Operating system')]/../../.."
    )
    bios = SystemInformationSection(".//h1[contains(text(), 'BIOS')]/../../..")
    infrastructure = SystemInformationSection(".//h1[contains(text(), 'Infrastructure')]/../../..")
    configuration = SystemInformationSection(".//h1[contains(text(), 'Configuration')]/../../..")
    system_status = SystemInformationSection(".//h1[contains(text(), 'System status')]/../../..")
    subscriptions = SystemInformationSection(".//h1[contains(text(), 'Subscriptions')]/../../..")
    # section for image-mode systems
    bootc = SystemInformationSection(".//h1[contains(text(), 'BOOTC')]/../../..")

    class NestedRowId(View):
        ROOT = ".//div[contains(@class, '-c-table__expandable-row-content')]"
        id = Text(locator=".//div[@class='pf-m-grow']")

    table = ExpandableTable(
        locator='.//table[contains(@class, "-c-table")]',
        content_view=NestedRowId(),
        column_widgets={
            0: Button(locator=".//button[@aria-label='Details']"),
            "Name": Text(locator=".//td"),
            "Status": Text(locator=".//td"),
            "Last upload": Text(locator=".//td"),
        },
    )

    @property
    def is_image_based_system(self):
        return "Image-based" in self.system_labels and len(self.system_labels) == 1

    @property
    def is_package_based_system(self):
        return "Package-based" in self.system_labels

    @property
    def is_displayed(self):
        return super().is_displayed and self.general_info.is_active()

    def get_data_collector(self, source):
        if self.table.is_displayed:
            return self.table.row(("Name", source)).read()

    def navigate_to_workspace(self):
        """Redirect to workspace from host's details page"""
        if self.system_properties.details["Workspace"] != "Not available":
            el = self.browser.element(self.WORKSPACE_LINK_LOCATOR)
            el.click()

    def enable_edit(self, name: str):
        """Edit display or ansible name from Host's details page"""
        properties = {"Display name": 0, "Ansible name": 1}
        els = self.browser.elements(self.EDIT_BUTTON_LOCATORS)
        els[properties[name]].click()


class Toolbar(View):
    ROOT = ".//div[contains(@data-ouia-component-id, 'PrimaryToolbar')]"

    select = Dropdown(locator=".//div[contains(@class,'c-bulk-select')]")
    find_cve = TextInput(locator=".//input[contains(@id, 'search-cve')]")
    filters = Dropdown("Filters")
    remediate = Button("Plan remediation")
    expand_collapse = ButtonOUIA("ExpandCollapseAll")
    pagination = PaginationOUIA("pagination-top")


class RuleContent(View):
    ROOT = ".//article[contains(@class, '-c-card')]"
    ITEM = (
        ".//div[@class='pf-l-stack__item']"
        "[.//article/div[contains(@class, '-c-card__header') and contains(., '{}')]]"
        "/article/div[@class='-c-card__body']"
    )

    detected_issues = Text(ITEM.format("Detected issues"))
    steps_to_resolve = Text(ITEM.format("Steps to resolve"))
    kb_article = Text(ITEM.format("Related Knowledgebase article"))
    additional_info = Text(ITEM.format("Additional info"))


class SystemAdvisor(SystemPage, SearchableTableMixin):
    toolbar = Toolbar()
    table = ExpandableTable(
        locator='.//table[@id="system-advisor-report-table"]',
        content_view=RuleContent(),
        column_widgets={
            1: Checkbox(locator=".//input[@type='checkbox']"),
            "Description": Text(".//td[@data-label='Description']"),
            "Modified": Text(".//td[@data-label='Modified']"),
            "First impacted": HoverText(".//td[@data-label='First impacted']"),
            "Total risk": Text(".//td[@data-label='Total risk']"),
            "Remediation": InsightsAnsibleSupport(),
        },
    )
    toolbar = Toolbar()
    _not_connected = Text(
        '//div[contains(@class, "-c-empty-state__content")]//h5[contains(text(), '
        '"This system isn`t connected to Insights yet")]'
    )

    @property
    def not_connected(self):
        return self._not_connected.is_displayed

    @property
    def is_displayed(self):
        return self.toolbar.is_displayed and self.advisor.is_active()


class SystemVulnerabilities(SystemPage):
    toolbar = Toolbar()
    table = ExpandableTable(
        locator=".//table[@aria-label='Vulnerability CVE table']",
        column_widgets={
            1: Checkbox(locator=".//input[@type='checkbox']"),
        },
    )
    applied_filters = TableFilterChipgroup(locator='.//span[contains(@class, "c-chip-filters")]')

    # need to define separate _remediate button for this view because of exception.
    remediate_vul = Text('.//button[text()="Remediate"]')
    _not_connected = Text(
        '//div[contains(@class, "-c-empty-state__content")]//h5[contains(text(), '
        '"This system isn`t connected to Insights yet")]'
    )

    @property
    def not_connected(self):
        return self._not_connected.is_displayed

    @property
    def is_displayed(self):
        return self.toolbar.is_displayed and self.vulnerability.is_active()

    def get_filters(self):
        """Grab a dict of the current filters, if any are applied"""
        try:
            return self.applied_filters.read()
        except NoSuchElementException:
            return {}


class SystemCompliance(SystemPage):
    toolbar = Toolbar()
    table = ExpandableTable(
        locator=".//table[@aria-label='Rules Table']",
        column_widgets={
            1: Checkbox(locator=".//input[@type='checkbox']"),
        },
    )
    _create_new_policy_ouia = ButtonOUIA("CreateNewPolicyButton")
    _create_new_policy = Button("Create new policy")

    _not_connected = Text(
        '//div[contains(@class, "-c-empty-state__content")]//h1[contains(text(), '
        '"No policies are reporting for this system")]'
    )

    @property
    def new_policy(self):
        if self._create_new_policy_ouia.is_displayed:
            return self._create_new_policy_ouia
        else:
            return self._create_new_policy

    @property
    def not_connected(self):
        return self._not_connected.is_displayed

    @property
    def is_displayed(self):
        return self.new_policy.is_displayed and self.compliance.is_active()


class SystemPatch(SystemPage, SearchableTableMixin):
    toolbar = Toolbar()
    table = ExpandableTable(
        locator=".//table[@aria-label='Patch table view']",
        column_widgets={
            1: Checkbox(locator=".//input[@type='checkbox']"),
        },
    )
    _not_connected = Text(
        '//div[contains(@class, "-c-empty-state__content")]//h5[contains(text(), '
        '"This system isn`t connected to Insights yet")]'
    )

    @property
    def not_connected(self):
        return self._not_connected.is_displayed

    @property
    def is_displayed(self):
        return self.toolbar.is_displayed and self.patch.is_active()
