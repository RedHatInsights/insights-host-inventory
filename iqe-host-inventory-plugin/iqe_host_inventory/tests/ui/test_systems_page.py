# mypy: disallow-untyped-defs

from collections.abc import Generator

import pytest
from fauxfactory import gen_alphanumeric
from iqe.base.application import Application
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.views.systems import FailedExportAlert
from iqe_host_inventory.views.systems import SystemsPage
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]


@pytest.mark.smoke
def test_navigate(systems_collection: SystemCollection, setup_ui_host_module: HostOut) -> None:
    """
    Test that we can navigate to the Inventory page

    metadata:
        requirements: inv_ui-navigation
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(systems_collection, "Systems")
    assert view.is_displayed, "The Systems page was not visible after login"


@pytest.mark.outage
@pytest.mark.core
def test_navigate_between_image_and_systems_views(
    systems_collection: SystemCollection,
    setup_ui_bootc_host: HostOut,
    request: pytest.FixtureRequest,
) -> None:
    """
    Test that we can switch between Image View and Systems View

    metadata:
        requirements: inv_ui-navigation, inv-hosts-filter-by-system_profile-bootc_status
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(systems_collection, "Systems")
    request.addfinalizer(view.switch_to_systems_view)
    view.refresh_page()
    view.switch_to_images_view()
    assert view.image_view.is_displayed, "The Images view was not visible after swithing views"
    view.switch_to_systems_view()
    assert view.is_displayed, "The Systems view was not visible after swithing views"


@pytest.mark.core
def test_systems_ui_delete_single_system(
    hbi_application_frontend: Generator[Application, None, None],
    systems_collection: SystemCollection,
    setup_ui_host: HostOut,
) -> None:
    """
    Test that deleting a single system using the per-row action works as expected.

    metadata:
        requirements: inv-hosts-delete-by-id
        assignee: zabikeno
        importance: high
    """
    system = systems_collection.instantiate_with_id(setup_ui_host.id)
    with hbi_application_frontend.context.use(ViaWebUI):
        system.delete(from_systems_page=True)

    # check that the delete modal closes and a deletion alert appears
    view = hbi_application_frontend.web_ui.create_view(SystemsPage)
    alert_title = "Delete operation finished"
    assert view.has_notification(title=alert_title)
    # make sure the host doesn't still exist via REST
    assert not system.exists


@pytest.mark.core
def test_systems_ui_bulk_delete_system(
    host_inventory_frontend: ApplicationHostInventory,
    systems_collection: SystemCollection,
    setup_ui_hosts_to_delete: str,
) -> None:
    """
    Test that deleting multiple systems using bulk delete button works as expected.

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: zabikeno
        importance: high
    """
    unique_id = setup_ui_hosts_to_delete
    expected_systems_to_delete = host_inventory_frontend.apis.hosts.get_hosts(
        display_name=unique_id
    )
    view = navigate_to(systems_collection, "Systems")

    view.name_search(unique_id)
    assert all(unique_id.lower() in row.name.text for row in view.table.rows()), (
        f"Only systems with unique_id: '{unique_id}' should be in the first page."
    )
    view.bulk_select.select()
    assert view.bulk_select.count == len(expected_systems_to_delete), (
        "Number of selected systems should be same as expected uploaded systems "
        f"for deletion, currently selected {view.bulk_select.count} systems."
    )
    view.delete_button.click()
    assert view.delete_system_modal.is_displayed
    view.delete_system_modal.delete.click()
    # verify that systems are no longer exist ininventory
    expected_systems = host_inventory_frontend.apis.hosts.get_hosts(display_name=unique_id)
    assert len(expected_systems) == 0


@pytest.mark.core
def test_systems_ui_edit_display_name(
    hbi_application_frontend: Generator[Application, None, None],
    systems_collection: SystemCollection,
    setup_ui_host_module: HostOut,
) -> None:
    """
    Test that the system's display name updates correctly after being
    edited from the systems page.

    metadata:
        requirements: inv-hosts-patch
        assignee: zabikeno
        importance: high
    """
    system = systems_collection.instantiate_with_id(setup_ui_host_module.id)
    edit_name = gen_alphanumeric(8)

    with hbi_application_frontend.context.use(ViaWebUI):
        system.update(from_systems_page=True, **{"display_name": edit_name})

    view = hbi_application_frontend.web_ui.create_view(SystemsPage)
    # the modal should close after saving
    assert not view.edit_system_modal.is_displayed
    # check that the success alert shows up and provides relevant information
    alert_title = f"Display name has been changed to {edit_name}"
    assert view.has_notification(title=alert_title)
    # confirm that the system's name has updated in the table
    view.name_search(edit_name)
    assert view.results == 1


@pytest.mark.core
@pytest.mark.parametrize("export", ["CSV", "JSON"])
def test_export_service_ui_alert(
    host_inventory_secondary: ApplicationHostInventory, export: str
) -> None:
    """
    Test that user able to export systems.
    Test run in insights-qa account to have big amount of hosts

    https://issues.redhat.com/browse/RHINENG-10495

    metadata:
        requirements: inv-export-hosts
        assignee: zabikeno
        importance: high
    """
    error_alert = "Export cannot be generated."
    succesfull_alert = "The requested export is being downloaded."
    pending_alert = (
        "The requested export is being prepared. When ready, "
        "the download will start automatically."
    )

    view = navigate_to(host_inventory_secondary.collections.systems, "Systems")
    wait_for(lambda: view.column_selector.is_displayed, timeout=10)

    if export == "CSV":
        view.export_to_csv()
    else:
        view.export_to_json()
    # check that the success alert shows up and provides relevant information
    # failed export request
    if view.has_notification(title=error_alert):
        raise FailedExportAlert(error_alert)
    # succesfull export request
    assert wait_for(lambda: view.has_notification(title=pending_alert), timeout=30)
    assert wait_for(lambda: view.has_notification(title=succesfull_alert), timeout=30)
