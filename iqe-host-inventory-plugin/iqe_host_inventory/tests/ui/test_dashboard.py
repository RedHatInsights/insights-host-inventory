import urllib

import pytest
from iqe.base.application.implementations.web_ui import navigate_to
from wait_for import wait_for

from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.utils.ui_utils import DASHBOARD_FILTERS
from iqe_host_inventory.utils.ui_utils import URL_FILTERS
from iqe_host_inventory.views.systems import SystemsPage
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]


@pytest.mark.core
@pytest.mark.parametrize("link", ["insights_systems", "stale_systems", "systems_to_remove"])
def test_navigate_to_inventory_via_dashboard_link(
    hbi_application_frontend,
    systems_collection: SystemCollection,
    link: str,
    setup_ui_host_module: HostOut,
):
    """
    Test that we can navigate to the Inventory Systems page via links on Dashboard page

    metadata:
        requirements:
            - inv-hosts-filter-by-registered_with
            - inv_ui-dashboard
            - inv_ui-navigation
        importance: high
        assignee: zabikeno
    """
    application = hbi_application_frontend
    dashboard_view = navigate_to(systems_collection, "InsightsDashboard")
    assert dashboard_view.is_displayed
    # redirect to inventory systems based on clicked link
    dashboard_view.redirect(URL_FILTERS[link])
    inventory_view = application.web_ui.create_view(SystemsPage)
    assert wait_for(lambda: inventory_view.top_paginator.is_displayed, timeout=20)


@pytest.mark.core
@pytest.mark.parametrize("link", ["insights_systems", "stale_systems", "systems_to_remove"])
def test_dashboard_filters_consistency(
    hbi_application_frontend,
    systems_collection: SystemCollection,
    link: str,
    setup_ui_host_module: HostOut,
):
    """
    Test that link on Dashboard page applies right filters

    metadata:
        requirements:
            - inv-hosts-filter-by-registered_with
            - inv_ui-dashboard
            - inv-hosts-filter-by-staleness
        importance: medium
        assignee: zabikeno
    """
    application = hbi_application_frontend
    dashboard_view = navigate_to(systems_collection, "InsightsDashboard")
    dashboard_view.redirect(URL_FILTERS[link])

    inventory_view = application.web_ui.create_view(SystemsPage)
    assert wait_for(lambda: inventory_view.top_paginator.is_displayed, timeout=20)

    url = urllib.parse.unquote(inventory_view.browser.url)
    assert URL_FILTERS[link] in url, "URL contains different filters."
    assert sorted(inventory_view.get_filters_list()) == sorted(DASHBOARD_FILTERS[link])


@pytest.mark.core
def test_dashboard_global_filter_consistency(
    hbi_application_frontend,
    systems_collection: SystemCollection,
    request,
    setup_ui_host_module: HostOut,
):
    """
    Test that global filter is not reset while navigating from Dashboard page

    metadata:
        requirements:
            - inv-hosts-filter-by-registered_with
            - inv_ui-dashboard
        importance: medium
        assignee: zabikeno
    """
    application = hbi_application_frontend
    workload = "SAP"
    dashboard_view = navigate_to(systems_collection, "InsightsDashboard")
    request.addfinalizer(dashboard_view.clear_tags)

    dashboard_view.select_tags({workload: True})
    dashboard_view.close_menu()
    assert workload in dashboard_view.workloads

    dashboard_view.redirect(URL_FILTERS["insights_systems"])
    inventory_view = application.web_ui.create_view(SystemsPage)
    assert wait_for(lambda: inventory_view.top_paginator.is_displayed, timeout=20)

    assert workload in inventory_view.workloads, "Global filter is reset."
