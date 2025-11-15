from __future__ import annotations

from functools import cached_property

import attr
from iqe.base.application.implementations.rest import ViaREST
from iqe.base.application.implementations.web_ui import IQENavigateStep
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.modeling import BaseCollection
from iqe.base.modeling import BaseEntity
from sentaku import ContextualMethod
from sentaku import Element as SentakuElement
from taretto.navigate import NavigateToAttribute
from taretto.navigate import NavigateToSibling

from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.ui_utils import CENTOS_LABEL
from iqe_host_inventory.views import InsightsDashboardPage
from iqe_host_inventory.views.system_details import SystemAdvisor
from iqe_host_inventory.views.system_details import SystemCompliance
from iqe_host_inventory.views.system_details import SystemInformationTab
from iqe_host_inventory.views.system_details import SystemPage
from iqe_host_inventory.views.system_details import SystemPatch
from iqe_host_inventory.views.system_details import SystemVulnerabilities
from iqe_host_inventory.views.systems import DeleteSystemModal
from iqe_host_inventory.views.systems import EditSystemNameModal
from iqe_host_inventory.views.systems import SystemsPage
from iqe_host_inventory.views.systems import SystemsPageEmptyState
from iqe_host_inventory.views.systems import SystemsPageZeroState
from iqe_host_inventory.widgetastic_host_inventory import TagsModal


@attr.s
class System(BaseEntity, SentakuElement):
    parent: SystemCollection

    id = attr.ib()
    display_name = attr.ib(default=None)
    ansible_host = attr.ib(default=None)
    stale_timestamp = attr.ib(default=None)
    account = attr.ib(default=None)
    bios_uuid = attr.ib(default=None)
    created = attr.ib(default=None)
    culled_timestamp = attr.ib(default=None)
    facts = attr.ib(default=None)
    fqdn = attr.ib(default=None)
    insights_id = attr.ib(default=None)
    ip_addresses = attr.ib(default=None)
    mac_addresses = attr.ib(default=None)
    provider_id = attr.ib(default=None)
    provider_type = attr.ib(default=None)
    reporter = attr.ib(default=None)
    per_reporter_staleness = attr.ib(default=None)
    satellite_id = attr.ib(default=None)
    stale_timestamp = attr.ib(default=None)
    stale_warning_timestamp = attr.ib(default=None)
    subscription_manager_id = attr.ib(default=None)
    updated = attr.ib(default=None)
    groups = attr.ib(default=None)

    delete = ContextualMethod()
    update = ContextualMethod()

    @property
    def system_ident(self):
        return self.display_name

    @property
    def exists(self):
        resp = self.parent.rest_api_entity.api_host_get_host_by_id([self.id])
        return resp.count == 1

    @cached_property
    def system_profile(self):
        return self.get_system_profile_data()

    def delete_if_exists(self):
        if self.exists:
            with self.context.use(ViaREST):
                self.delete()

    def get_system_profile_data(self):
        resp = self.parent.rest_api_entity.api_host_get_host_system_profile_by_id([self.id])
        if resp.count == 1:
            return resp.results[0].system_profile.to_dict()


@attr.s
class SystemCollection(BaseCollection, SentakuElement):
    ENTITY = System

    @property
    def rest_api_entity(self):
        return self.application.host_inventory.rest_client.hosts_api

    def _instantiate_with_rest_data(self, system_data):
        return self.instantiate(
            account=system_data.account,
            ansible_host=system_data.ansible_host,
            bios_uuid=system_data.bios_uuid,
            created=system_data.created,
            culled_timestamp=system_data.culled_timestamp,
            display_name=system_data.display_name,
            facts=system_data.facts,
            fqdn=system_data.fqdn,
            id=system_data.id,
            insights_id=system_data.insights_id,
            ip_addresses=system_data.ip_addresses,
            mac_addresses=system_data.mac_addresses,
            provider_id=system_data.provider_id,
            reporter=system_data.reporter,
            per_reporter_staleness=system_data.per_reporter_staleness,
            satellite_id=system_data.satellite_id,
            stale_timestamp=system_data.stale_timestamp,
            stale_warning_timestamp=system_data.stale_warning_timestamp,
            subscription_manager_id=system_data.subscription_manager_id,
            updated=system_data.updated,
            groups=system_data.groups,
        )

    def instantiate_with_id(self, uuid):
        resp = self.rest_api_entity.api_host_get_host_by_id([uuid])
        if resp.count == 1:
            host_data = HostWrapper(resp.results[0].to_dict())
            return self._instantiate_with_rest_data(host_data)


@ViaWebUI.register_destination_for(SystemCollection, "Systems")
class Systems(IQENavigateStep):
    """Inventory Systems page step - skip steps to /insights"""

    VIEW = SystemsPage
    prerequisite = NavigateToAttribute("application.platform_ui", "BasePage")

    def step(self, *args, **kwargs):
        self.application.web_ui.widgetastic_browser.url = (
            self.application.platform_ui.base_address + "insights/inventory"
        )

    def resetter(self, *args, **kwargs):
        """Reset filters"""
        self.view.reset_filters()


@ViaWebUI.register_destination_for(SystemCollection, "InsightsInventory")
class InsightsInventory(IQENavigateStep):
    """Inventory Systems page step via navbar"""

    VIEW = SystemsPage
    prerequisite = NavigateToAttribute("application.platform_ui", "Insights")

    def step(self, *args, **kwargs):
        self.prerequisite_view.navigation.select("Inventory", "Systems", force=True)

    def resetter(self, *args, **kwargs):
        """Reset filters"""
        self.view.reset_filters()


@ViaWebUI.register_destination_for(SystemCollection, "SystemsEmptyState")
class SystemsEmptyState(IQENavigateStep):
    """Inventory step when inventory is showing empty state"""

    VIEW = SystemsPageEmptyState
    prerequisite = NavigateToAttribute("application.platform_ui", "BasePage")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.application.web_ui.widgetastic_browser.url = (
            self.application.platform_ui.base_address + "insights/inventory"
        )


@ViaWebUI.register_destination_for(SystemCollection, "SystemsZeroState")
class SystemsZeroState(IQENavigateStep):
    """Inventory step when inventory is showing zero state"""

    VIEW = SystemsPageZeroState
    prerequisite = NavigateToAttribute("application.platform_ui", "BasePage")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.application.web_ui.widgetastic_browser.url = (
            self.application.platform_ui.base_address + "insights/inventory"
        )


@ViaWebUI.register_destination_for(System, "SystemDetails")
class SystemDetails(IQENavigateStep):
    """Step to a system details page"""

    VIEW = SystemPage
    prerequisite = NavigateToAttribute("application.host_inventory.collections.systems", "Systems")

    def step(self, *args, **kwargs):
        system_name = self.obj.system_ident

        self.prerequisite_view.search(system_name, column="Name")
        if CENTOS_LABEL in self.prerequisite_view.table.row().name.text:
            system_name += CENTOS_LABEL
        self.prerequisite_view.table.row(name=system_name).name.widget.click()


@ViaWebUI.register_destination_for(System, "SystemInformation")
class SystemInformation(IQENavigateStep):
    """Step to system details page, General information tab"""

    VIEW = SystemInformationTab
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.general_info.select()


@ViaWebUI.register_destination_for(System, "EditFromSystemsPage")
class EditFromSystemsPage(IQENavigateStep):
    """Step to inventory systems page and open edit system modal"""

    VIEW = EditSystemNameModal
    prerequisite = NavigateToAttribute("application.host_inventory.collections.systems", "Systems")

    def step(self, *args, **kwargs):
        row = self.prerequisite_view.find_row(search=self.obj.system_ident, column="Name")
        row[6].widget.item_select("Edit display name")


@ViaWebUI.register_destination_for(System, "Delete")
class Delete(IQENavigateStep):
    """Step to system details page and open delete modal"""

    VIEW = DeleteSystemModal
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.delete.click()


@ViaWebUI.register_destination_for(System, "DeleteFromSystemsPage")
class DeleteFromSystemsPage(IQENavigateStep):
    """Step to inventory systems page and open delete modal"""

    VIEW = DeleteSystemModal
    prerequisite = NavigateToAttribute("application.host_inventory.collections.systems", "Systems")

    def step(self, *args, **kwargs):
        row = self.prerequisite_view.find_row(search=self.obj.system_ident, column="Name")
        row[6].widget.item_select("Delete from inventory")


@ViaWebUI.register_destination_for(SystemCollection, "InsightsDashboard")
class InsightsDashboard(IQENavigateStep):
    """Insights Dashboard step"""

    VIEW = InsightsDashboardPage
    prerequisite = NavigateToAttribute("application.host_inventory.collections.systems", "Systems")

    def step(self, *args, **kwargs):
        """Go to the step view"""
        self.prerequisite_view.navigation.select("Dashboard", force=True)


@ViaWebUI.register_destination_for(System, "TagModal")
class Tags(IQENavigateStep):
    """Step to host detail page and open tags modal"""

    VIEW = TagsModal
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.tags.click()

    def am_i_here(self, *args, **kwargs):
        return self.view.is_displayed


@ViaWebUI.register_destination_for(System, "Advisor")
class AdvisorTab(IQENavigateStep):
    """Step to host detail page, Advisor tab"""

    VIEW = SystemAdvisor
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.advisor.select()


@ViaWebUI.register_destination_for(System, "Vulnerability")
class VulnerabilitiesTab(IQENavigateStep):
    """Step to host detail page, Vulnerability tab"""

    VIEW = SystemVulnerabilities
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.vulnerability.select()


@ViaWebUI.register_destination_for(System, "Compliance")
class ComplianceTab(IQENavigateStep):
    """Step to host detail page, Compliance tab"""

    VIEW = SystemCompliance
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.compliance.select()


@ViaWebUI.register_destination_for(System, "Patch")
class PatchTab(IQENavigateStep):
    """Step to host detail page, Patch tab"""

    VIEW = SystemPatch
    prerequisite = NavigateToSibling("SystemDetails")

    def step(self, *args, **kwargs):
        self.prerequisite_view.patch.select()
