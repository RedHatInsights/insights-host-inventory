import pytest
from iqe.base.application.implementations.web_ui import navigate_to

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]


@pytest.mark.core
@pytest.mark.outage
@pytest.mark.smoke
def test_navigate_custom_staleness_page(
    setup_ui_host_module: HostOut, host_inventory_frontend: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-5026

    metadata:
        title: Test that we can navigate to the Staleness And Deletion page
        requirements: inv_ui-navigation, inv-staleness-get
        importance: high
        assignee: zabikeno
    """
    view = navigate_to(host_inventory_frontend, "CustomStaleness")
    assert view.organization_level_card.is_displayed


@pytest.mark.core
def test_custom_staleness_page_reset_to_default_setting(
    setup_ui_host_module: HostOut, host_inventory_frontend: ApplicationHostInventory
):
    """
    metadata:
        title: Test that user can reset staleness setting to default
        requirements: inv-staleness-get-defaults, inv-staleness-patch
        importance: high
        assignee: zabikeno
    """
    view = navigate_to(host_inventory_frontend, "CustomStaleness")
    view.organization_level_card.enable_edit()
    view.organization_level_card.stale_warning.item_select("150 days")
    assert not view.organization_level_card.default_setting_selected()

    view.organization_level_card.reset()
    view.organization_level_card.save()
    view.update_setting_modal.update.click()

    assert view.organization_level_card.default_setting_selected()
