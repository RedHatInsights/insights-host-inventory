import datetime
import time
from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe.base.application.implementations.web_ui import ViaWebUI
from iqe.base.application.implementations.web_ui import navigate_to
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import System
from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.ui_utils import convert_system_profile_when_not_available
from iqe_host_inventory.utils.ui_utils import format_bytes
from iqe_host_inventory.utils.ui_utils import generate_workspace_name
from iqe_host_inventory.utils.ui_utils import get_status_indicator_based_on_stale_data
from iqe_host_inventory.utils.ui_utils import get_tags_from_tags_modal
from iqe_host_inventory.views.system_details import SystemAdvisor
from iqe_host_inventory.views.system_details import SystemInformationTab
from iqe_host_inventory.views.system_details import SystemPage
from iqe_host_inventory.views.system_details import SystemPatch
from iqe_host_inventory.views.system_details import SystemVulnerabilities
from iqe_host_inventory.views.workspaces import WorkspaceSystemsTab
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]

TAGS_COUNT = 12


@pytest.fixture(scope="module")
def system(
    host_inventory_frontend: ApplicationHostInventory,
    setup_ui_host_module: HostOut,
    systems_collection: SystemCollection,
) -> System:
    host_inventory_frontend.apis.groups.create_group(
        generate_workspace_name(), hosts=setup_ui_host_module, cleanup_scope="module"
    )
    return systems_collection.instantiate_with_id(setup_ui_host_module.id)


@pytest.fixture
def centos_system(
    setup_ui_centos_host: HostOut,
    systems_collection: SystemCollection,
) -> System:
    return systems_collection.instantiate_with_id(setup_ui_centos_host.id)


@pytest.fixture(scope="module")
def bootc_system(
    setup_ui_bootc_host: HostOut,
    systems_collection: SystemCollection,
) -> System:
    system = systems_collection.instantiate_with_id(setup_ui_bootc_host.id)
    system_profile = system.system_profile
    for key in system_profile["bootc_status"].keys():
        if system_profile["bootc_status"].get(key) is None:
            system_profile["bootc_status"][key] = {
                "image": "Not available",
                "image_digest": "Not available",
            }

    return system


@pytest.fixture
def immutable_system(
    setup_ui_edge_host: HostOut,
    systems_collection: SystemCollection,
) -> System:
    return systems_collection.instantiate_with_id(setup_ui_edge_host.id)


@pytest.fixture
def system_with_tags(
    host_inventory_frontend: ApplicationHostInventory, systems_collection: SystemCollection
) -> tuple[System, list[TagDict]]:
    tags = generate_tags(TAGS_COUNT)
    system_details = host_inventory_frontend.upload.create_host(tags=tags)
    system = systems_collection.instantiate_with_id(system_details.id)

    return system, tags


@pytest.mark.outage
@pytest.mark.smoke
def test_system_ui_navigation(system: System):
    """
    Test that we can navigate to the System Details page

    metadata:
        requirements: inv_ui-navigation, inv-hosts-get-by-id
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(system, "SystemDetails")
    assert view.is_displayed, "The System's details page was not visible after login"
    assert view.title.text == system.display_name


@pytest.mark.core
def test_system_ui_tag_count(system: System):
    """
    Test that we get the correct number of tags in the tag modal

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(system, "SystemDetails")
    tag_count = int(view.tags.read())
    view.tags.click()

    assert system.display_name in view.tags_modal.title
    assert view.tags_modal.tag_count == tag_count
    view.tags_modal.close()


@pytest.mark.outage
@pytest.mark.parametrize(
    "tab",
    ["Advisor", "Vulnerability", "Compliance", "Patch"],
)
def test_system_ui_navigate_to_system_tabs(system: System, tab):
    """
    Test that user able to navigate to every tab in System's details page

    metadata:
        requirements: inv_ui-navigation, inv-hosts-get-by-id
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(system, tab)
    if tab == "Compliance":
        assert wait_for(lambda: view.new_policy.is_displayed, timeout=15)
    else:
        assert wait_for(lambda: view.table.is_displayed, timeout=15)


@pytest.mark.core
def test_system_ui_information_tab(
    host_inventory_frontend: ApplicationHostInventory, system: System
):
    """
    Test that navigating to the System information tab works, and the data on there is correct.

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    system_profile = convert_system_profile_when_not_available(system.system_profile)
    system.ansible_host = system.fqdn

    view: SystemInformationTab = navigate_to(system, "SystemInformation")  # type: ignore[assignment]
    assert view.is_package_based_system
    assert view.is_displayed
    assert view.title.text == system.display_name
    assert view.uuid.text == system.id
    assert view.last_seen.text == system.updated.strftime("%d %b %Y %H:%M %Z")

    # test System properties
    assert view.system_properties.details["Host name"] == system.fqdn
    assert view.system_properties.details["Display name"] == system.display_name
    assert view.system_properties.details["Ansible hostname"] == system.ansible_host
    assert view.system_properties.details["Workspace"] == system.groups[0]["name"]
    assert view.system_properties.details["System purpose"] == system_profile["system_purpose"]
    assert view.system_properties.details["Number of CPUs"] == str(
        system_profile["number_of_cpus"]
    )
    assert view.system_properties.details["Sockets"] == str(system_profile["number_of_sockets"])
    assert view.system_properties.details["Cores per socket"] == str(
        system_profile["cores_per_socket"]
    )
    assert (
        view.system_properties.details["CPU flags"] == f"{len(system_profile['cpu_flags'])} flags"
    )
    assert view.system_properties.details["RAM"] == format_bytes(
        system_profile["system_memory_bytes"]
    )

    # test Operating system
    assert view.operating_system.details["Release"] == (
        f"{system_profile['operating_system']['name']} "
        f"{system_profile['operating_system']['major']}."
        f"{system_profile['operating_system']['minor']}"
    )
    assert view.operating_system.details["Kernel release"] == system_profile["os_kernel_version"]
    assert view.operating_system.details["Architecture"] == system_profile["arch"]
    assert view.operating_system.details["Last boot time"] == system_profile[
        "last_boot_time"
    ].strftime("%d %b %Y")
    assert (
        view.operating_system.details["Kernel modules"]
        == f"{len(system_profile['kernel_modules'])} modules"
    )
    assert view.operating_system.details["Update method"] == system_profile["system_update_method"]

    # test BIOS
    assert view.bios.details["Vendor"] == system_profile["bios_vendor"]
    assert view.bios.details["Version"] == system_profile["bios_version"]
    bios_date = datetime.datetime.strptime(system_profile["bios_release_date"], "%m/%d/%Y")
    assert view.bios.details["Release date"] == bios_date.strftime("%d %b %Y")

    # test Infrastructure
    assert view.infrastructure.details["Type"] == system_profile["infrastructure_type"]
    assert view.infrastructure.details["Vendor"] == system_profile["infrastructure_vendor"]
    assert view.infrastructure.details["Public IP"] == system_profile["public_ipv4_addresses"]

    interfaces = system_profile["network_interfaces"]
    ipv4 = [len(ip["ipv4_addresses"]) for ip in interfaces if ip["ipv4_addresses"] is not None]
    ipv6 = [len(ip["ipv6_addresses"]) for ip in interfaces if ip["ipv6_addresses"] is not None]
    assert view.infrastructure.details["IPv4 addresses"] == f"{sum(ipv4)} addresses"
    assert view.infrastructure.details["IPv6 addresses"] == f"{sum(ipv6)} addresses"
    assert view.infrastructure.details["FQDN"] == system_profile["public_dns"]
    assert view.infrastructure.details["Interfaces/NICs"] == f"{len(interfaces)} NICs"

    # test Configuration
    assert (
        view.configuration.details["Installed packages"]
        == f"{len(system_profile['installed_packages'])} packages"
    )
    assert (
        view.configuration.details["Services"]
        == f"{len(system_profile['enabled_services'])} services"
    )
    assert (
        view.configuration.details["Running processes"]
        == f"{len(system_profile['running_processes'])} processes"
    )

    if system_profile["yum_repos"] != "Not available":
        repos = [
            val for d in system_profile["yum_repos"] for key, val in d.items() if key == "enabled"
        ]
        if repos.count(False) == 0:
            system_profile["yum_repos"] = f"{repos.count(True)} enabled"
        else:
            system_profile["yum_repos"] = (
                f"{repos.count(True)} enabled / {repos.count(False)} disabled"
            )
    assert view.configuration.details["Repositories"] == system_profile["yum_repos"]

    # test System status
    stale_info = get_status_indicator_based_on_stale_data({
        "Stale_warning": system.stale_warning_timestamp,
        "Created": system.created,
        "Stale": system.stale_timestamp,
    })
    state = "Active" if stale_info == "" else "Stale"
    assert view.system_status.details["Current state"] == state
    assert view.system_status.details["Registered"] == system.created.strftime("%d %b %Y %H:%M %Z")
    assert view.system_status.details["Last seen"] == system.updated.strftime("%d %b %Y %H:%M %Z")
    assert view.system_status.details["Last updated"] == system.updated.strftime(
        "%d %b %Y %H:%M %Z"
    )
    assert view.system_status.details["RHC"] == system_profile["rhc_client_id"]

    # Subscriptions, with current archive facts are not available
    assert view.subscriptions.details["Usage"] == "Not available"
    assert view.subscriptions.details["SLA"] == "Not available"
    assert view.subscriptions.details["Role"] == "Not available"

    # test Data Collectors
    # insights-client
    view.table.row(("Name", "insights-client")).expand()
    assert view.table.row(("Name", "insights-client")).is_expanded
    insights_id = view.table.row(("Name", "insights-client")).content.id.text
    assert insights_id == system.insights_id if system.insights_id is not None else "N/A"
    # subscription-manager
    view.table.row(("Name", "subscription-manager")).expand()
    assert view.table.row(("Name", "subscription-manager")).is_expanded
    sub_manager_id = view.table.row(("Name", "subscription-manager")).content.id.text
    assert (
        sub_manager_id == system.subscription_manager_id
        if system.subscription_manager_id is not None
        else "N/A"
    )
    # Satellite/Discovery, current archive has only puptoo reporter
    satellite_ui = view.table.row(("Name", "Satellite")).read()
    assert satellite_ui["Status"] == "N/A" and satellite_ui["Last upload"] == "N/A"
    discovery_ui = view.table.row(("Name", "Discovery")).read()
    assert discovery_ui["Status"] == "N/A" and discovery_ui["Last upload"] == "N/A"


@pytest.mark.core
def test_system_ui_navigate_to_workspace_from_system_details(
    system: System,
    hbi_application_frontend: Generator[Application, None, None],
    host_inventory_frontend: ApplicationHostInventory,
) -> None:
    """
    Test user able to navigate to workspace from system's details

    metadata:
        requirements: inv-hosts-get-by-id, inv_ui-navigation
        assignee: zabikeno
        importance: high
    """
    system_details_view = navigate_to(system, "SystemInformation")
    expected_workspace = system_details_view.system_properties.details["Workspace"]

    system_details_view.navigate_to_workspace()
    workspace_details_view = hbi_application_frontend.web_ui.create_view(WorkspaceSystemsTab)
    wait_for(lambda: workspace_details_view.table.is_displayed, timeout=15)

    assert workspace_details_view.title.text == expected_workspace
    workspace_systems = [row.name.text.lower() for row in workspace_details_view.table.rows()]
    assert system.display_name in workspace_systems


@pytest.mark.parametrize(
    "edit_name",
    ["display_name", "ansible_host"],
    ids=["display-name", "ansible-host"],
)
@pytest.mark.core
def test_system_ui_edit_name(
    hbi_application_frontend: Generator[Application, None, None], system: System, edit_name: str
):
    """
    Test that the system's display name/ansible hostname can be edited from the information page

    metadata:
        requirements: inv-hosts-get-system_profile, inv-hosts-patch
        assignee: zabikeno
        importance: high
    """
    update_details = {edit_name: system.display_name + "edit"}

    with hbi_application_frontend.context.use(ViaWebUI):
        system.update(**update_details)

    # test that the actual system details page reflects the changes
    view = hbi_application_frontend.web_ui.create_view(SystemInformationTab)
    assert getattr(system, edit_name) == update_details[edit_name]
    if edit_name == "display_name":
        assert view.system_properties.details["Display name"] == system.display_name
    else:
        assert view.system_properties.details["Ansible hostname"] == system.ansible_host


@pytest.mark.outage
@pytest.mark.core
@pytest.mark.smoke
def test_system_ui_bootc_system_info(bootc_system: System):
    """
    Test bootc image-based system has correct data

    https://issues.redhat.com/browse/RHINENG-8959

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    system_profile = bootc_system.system_profile
    view = navigate_to(bootc_system, "SystemInformation")
    assert view.is_image_based_system

    assert view.bootc.details["Booted Image"] == system_profile["bootc_status"]["booted"]["image"]
    assert (
        view.bootc.details["Booted Image Digest"]
        == system_profile["bootc_status"]["booted"]["image_digest"]
    )
    assert view.bootc.details["Staged Image"] == system_profile["bootc_status"]["staged"]["image"]
    assert (
        view.bootc.details["Staged Image Digest"]
        == system_profile["bootc_status"]["staged"]["image_digest"]
    )
    assert (
        view.bootc.details["Rollback Image"] == system_profile["bootc_status"]["rollback"]["image"]
    )
    assert (
        view.bootc.details["Rollback Image Digest"]
        == system_profile["bootc_status"]["rollback"]["image_digest"]
    )


@pytest.mark.outage
@pytest.mark.core
@pytest.mark.smoke
def test_system_ui_immutable_system_info(immutable_system: System):
    """
    Test immutable image-based system has correct data

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    view = navigate_to(immutable_system, "SystemInformation")
    assert view.is_image_based_system
    assert not view.bootc.is_displayed


@pytest.mark.core
def test_system_ui_centos_system_info(centos_system: System):
    """
    Test that navigating to the System CentOS information tab works,
    and the data on there is correct.

    https://issues.redhat.com/browse/RHINENG-984

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    expected_labels = ["CentOS Linux", "Package-based"]
    system_profile = centos_system.system_profile

    view = navigate_to(centos_system, "SystemDetails")
    assert view.general_info.is_displayed and not view.advisor.is_displayed
    assert view.centos_alert.is_displayed
    assert all(label in expected_labels for label in view.system_labels) and len(
        view.system_labels
    ) == len(expected_labels)

    view = navigate_to(centos_system, "SystemInformation")
    assert view.is_displayed
    assert view.system_properties.details["Display name"] == centos_system.display_name
    assert view.operating_system.details["Release"] == (
        f"{system_profile['operating_system']['name']} "
        f"{system_profile['operating_system']['major']}."
        f"{system_profile['operating_system']['minor']}"
    )


@pytest.mark.stage
def test_system_ui_tags_modal_pagination(system_with_tags):
    """
    Test that pagination within the tags modal works as expected.

    metadata:
        requirements: inv_ui-navigation, inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    per_page = 10
    system, expected_tags = system_with_tags
    # navigate to host view with tags modal displayed
    view_modal = navigate_to(system, "TagModal")
    assert view_modal.is_displayed
    assert view_modal.top_paginator.total_items == TAGS_COUNT

    view_modal.top_paginator.set_per_page(per_page)
    # grab tags from modal table
    modal_tags = get_tags_from_tags_modal(view=view_modal, expected_tags=TAGS_COUNT)
    modal_tags_sorted = sorted(modal_tags, key=lambda k: k["Name"] + k["Value"])
    # compare the tags displayed with what was returned from upload fixture
    tags_sorted = sorted(expected_tags, key=lambda k: k["key"] + k["value"])
    for i, tag in enumerate(modal_tags_sorted):
        assert tag["Name"] == tags_sorted[i]["key"] and tag["Value"] == tags_sorted[i]["value"]
    view_modal.close()


@pytest.mark.stage
def test_system_ui_not_connected_system(
    host_inventory_secondary: ApplicationHostInventory, hbi_application_secondary: Application
):
    """
    Test consistent state of a system that is not connected.
    Test run in insights-qa account to have systems not connected with insights-client

    metadata:
        requirements: inv-hosts-get-system_profile
        importance: high
        assignee: zabikeno
        title: Inventory UI: Consistent state of a host that is not connected
        test_steps:
            1. Navigate to Inventory application view.
            2. Filter table by Data Collector "insights-client not connected"
            3. Instantiate host and navigate to host's details page
            4. Confirm that host has alert is not connected
            5. Confirm on another tabs that host is not connected
    """
    view = navigate_to(host_inventory_secondary.collections.systems, "Systems")
    view.search({"insights-client not connected": True}, column="Data collector")
    time.sleep(1)
    host_name = view.table[0].name.text
    view.table.row().name.widget.click()
    system_details_view = hbi_application_secondary.web_ui.create_view(SystemPage)
    assert system_details_view.title.text == host_name
    assert system_details_view.alert.is_displayed

    system_details_view.advisor.select()
    view = hbi_application_secondary.web_ui.create_view(SystemAdvisor)
    assert view.not_connected

    system_details_view.patch.select()
    view = hbi_application_secondary.web_ui.create_view(SystemPatch)
    assert view.not_connected

    system_details_view.vulnerability.select()
    view = hbi_application_secondary.web_ui.create_view(SystemVulnerabilities)
    assert view.not_connected


@pytest.mark.ephemeral
@pytest.mark.smoke
def test_system_ui_subscription_facts(
    host_inventory: ApplicationHostInventory, systems_collection: SystemCollection
):
    """
    Test subscription facts in Systems details page
    TODO: move test upstream

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: high
    """
    subscription_facts = [
        {
            "namespace": "rhsm",
            "facts": {
                "SYSPURPOSE_SLA": "Self-Support",
                "SYSPURPOSE_ROLE": "Red Hat Enterprise Linux Server",
                "SYSPURPOSE_USAGE": "Production",
            },
        }
    ]
    host_data = host_inventory.datagen.create_host_data(facts=subscription_facts)
    system_details = host_inventory.kafka.create_host(host_data=host_data)
    system = systems_collection.instantiate_with_id(system_details.id)

    view = navigate_to(system, "SystemInformation")
    assert view.is_displayed

    assert view.subscriptions.details["Usage"] == system.facts[0]["facts"]["SYSPURPOSE_USAGE"]
    assert view.subscriptions.details["SLA"] == system.facts[0]["facts"]["SYSPURPOSE_SLA"]
    assert view.subscriptions.details["Role"] == system.facts[0]["facts"]["SYSPURPOSE_ROLE"]


@pytest.mark.ephemeral
def test_system_ui_system_without_tags(
    host_inventory: ApplicationHostInventory, systems_collection: SystemCollection
):
    """
    Test that system withou tags has disabled tag button
    TODO: move test upstream

    metadata:
        requirements: inv-hosts-get-system_profile
        assignee: zabikeno
        importance: medium
    """
    host_data = host_inventory.datagen.create_host_data(tags=[])
    system_without_tags = host_inventory.kafka.create_host(host_data=host_data)
    system = systems_collection.instantiate_with_id(system_without_tags.id)

    view = navigate_to(system, "SystemDetails")
    assert view.tags.disabled
