from collections.abc import Generator
from datetime import datetime

import pytest
from distutils.version import StrictVersion
from iqe.base.application import Application
from iqe.base.application.implementations.rest import ViaREST
from iqe.base.application.implementations.web_ui import navigate_to
from iqe.utils.blockers import iqe_blocker
from pytest import Metafunc
from wait_for import wait_for

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.entities.systems import SystemCollection
from iqe_host_inventory.entities.workspaces import WorkspaceCollection
from iqe_host_inventory.utils.datagen_utils import get_default_os_centos
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory.utils.ui_utils import LAST_SEEN_FILTERS
from iqe_host_inventory.utils.ui_utils import UNIQUE_UI_ID
from iqe_host_inventory.utils.ui_utils import assert_last_seen_datetime
from iqe_host_inventory.utils.ui_utils import generate_workspace_name
from iqe_host_inventory.utils.ui_utils import get_last_seen_column_values
from iqe_host_inventory.utils.upload_utils import get_archive_and_collect_method
from iqe_host_inventory.views.systems import SystemsPage
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.ui]


def pytest_generate_tests(metafunc: Metafunc) -> None:
    """Parametrize tests with views that share same systems table"""
    if "destination" in metafunc.fixturenames:
        views = ["Systems", "SystemsTab", "AddSystemsToWorkspace"]
        metafunc.parametrize("destination", views, ids=views, scope="class")


@pytest.fixture(scope="module")
def step_obj(
    systems_collection: SystemCollection,
    hbi_application_frontend: Application,
    host_inventory_frontend: ApplicationHostInventory,
    workspaces_collection: WorkspaceCollection,
):
    systems = host_inventory_frontend.upload.create_hosts(10, cleanup_scope="session")
    with hbi_application_frontend.context.use(ViaREST):
        workspace = workspaces_collection.create(
            generate_workspace_name(UNIQUE_UI_ID), systems=systems, cleanup_scope="session"
        )

    return {
        "Systems": systems_collection,
        "SystemsTab": workspace,
        "AddSystemsToWorkspace": workspace,
    }


@pytest.fixture
def navigate_to_systems_page(
    systems_collection: SystemCollection, request: pytest.FixtureRequest
) -> Generator[SystemsPage, None, None]:
    view: SystemsPage = navigate_to(systems_collection, "Systems")  # type: ignore[assignment]
    wait_for(lambda: view.column_selector.is_displayed, timeout=10)  # type: ignore[attr-defined]

    yield view

    view.reset_filters()
    view.clear_tags()


@iqe_blocker(iqe_blocker.jira("RHINENG-16402", category=iqe_blocker.AUTOMATION_ISSUE))
@pytest.mark.core
class TestUIFilteringSystemsbyLastSeen:
    @pytest.mark.parametrize("last_seen", LAST_SEEN_FILTERS[:5])
    def test_inventory_table_filter_by_last_seen(
        self,
        host_inventory_secondary: ApplicationHostInventory,
        last_seen: str,
        request: pytest.FixtureRequest,
    ):
        """Test that filtering the hosts by last seen works correctly

        metadata:
            requirements: inv-hosts-filter-by-updated
            importance: medium
            assignee: zabikeno
            setup: Runnning in insight-qa account that has hosts with different last seen dates
        """
        ORDER = ["ascending", "descending"]
        view = navigate_to(host_inventory_secondary.collections.systems, "Systems")
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)  # type: ignore[attr-defined]
        request.addfinalizer(view.reset_filters)

        view.search(last_seen, column="Last seen")
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)
        assert last_seen in view.get_filters_list() and len(view.get_filters_list()) == 1

        if view.results == 0:
            view.reset_filters()
            pytest.xfail(f"No matching systems found for '{last_seen}' filter.")

        # ensure pre-difined last_seen filter works as expected
        if last_seen == "Within the last 24 hours":
            # apply ascending order to check that the first last seen host is within
            # the last 24 hours
            view.table.sort_by("Last seen", ORDER[0])
            date = get_last_seen_column_values(view, first_row=True)[0]
            assert_last_seen_datetime(filter=last_seen, filtered_date=date)
        else:
            # apply descending order to see that filtered host starts from expected last seen date
            view.table.sort_by("Last seen", ORDER[1])
            date = get_last_seen_column_values(view, first_row=True)[0]
            assert_last_seen_datetime(filter=last_seen, filtered_date=date)


@pytest.mark.core
class TestUISortingSystems:
    def test_name_column(
        self, setup_ui_hosts_for_sorting: list[HostOut], navigate_to_systems_page
    ):
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: zabikeno
            importance: medium
            title: Inventory UI: Sorting systems by name
        """
        view = navigate_to_systems_page
        view.search(UNIQUE_UI_ID, column="Name")

        view.table.sort_by("Name", "ascending")
        # Get sorted systems from table
        actual_sorted_hosts = [row.name.text.lower() for row in view.table.rows()]
        expected_sorted_hosts = sorted(actual_sorted_hosts)

        assert actual_sorted_hosts == expected_sorted_hosts

    def test_workspace_column(
        self,
        navigate_to_systems_page,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: zabikeno
            importance: medium
            title: Inventory UI: Sorting systems by workspace
        """
        ungrouped_hosts = "Ungrouped Hosts"
        view = navigate_to_systems_page
        view.search(UNIQUE_UI_ID, column="Name")
        wait_for(lambda: view.top_paginator.is_displayed, timeout=20)

        view.table.sort_by("Workspace", "ascending")
        actual_sorted_workspaces = [
            row.workspace.text.lower()
            for row in view.table.rows()
            if row.workspace.text != ungrouped_hosts
        ]
        expected_sorted_workspaces = sorted(actual_sorted_workspaces)

        assert actual_sorted_workspaces == expected_sorted_workspaces

    def test_os_column(
        self, navigate_to_systems_page, setup_ui_hosts_with_different_os: list[str]
    ):
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: zabikeno
            importance: medium
            title: Inventory UI: Sorting systems by operating system
        """
        # Prepare hosts with reqire OS versions
        os_filter_options = setup_ui_hosts_with_different_os

        view = navigate_to_systems_page
        # refresh page to see new created OS RHEL versions in filter menu
        view.refresh_page()
        view.search(UNIQUE_UI_ID, column="Name")
        # filter by OS
        for os in os_filter_options:
            view.search({os: True}, column="Operating system")

        view.table.sort_by("OS", "ascending")
        actual_sorted_os = [row.os.widget.text for row in view.table.rows()]

        actual_sorted_os_version = [os.strip("RHEL ") for os in actual_sorted_os]
        expected_sorted_os_version = sorted(actual_sorted_os_version, key=StrictVersion)

        assert actual_sorted_os_version == expected_sorted_os_version

    @pytest.mark.parametrize("direction", ["ascending", "descending"])
    def test_last_seen_column(self, navigate_to_systems_page, direction: str):
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: zabikeno
            importance: medium
            title: Inventory UI: Sorting systems by last seen date
        """
        view = navigate_to_systems_page

        view.table.sort_by("Last seen", direction)
        actual_sorted_date = get_last_seen_column_values(view)
        expected_sorted_date = sorted(
            actual_sorted_date,
            reverse=(direction == "descending"),
            key=lambda date: datetime.strptime(date, "%d %b %Y %H:%M %Z"),
        )

        assert actual_sorted_date == expected_sorted_date


@pytest.mark.core
class TestUIFilteringSystems:
    def test_filter_by_name(self, navigate_to_systems_page, setup_ui_host_module: HostOut):
        """
        metadata:
            requirements: inv-hosts-filter-by-hostname_or_id
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by name
        """
        view = navigate_to_systems_page

        view.search(setup_ui_host_module.display_name, column="Name")
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)
        row = view.table.row(name=setup_ui_host_module.display_name)

        assert row is not None
        assert view.results == 1, "Filters should return 1 result"

    @iqe_blocker(iqe_blocker.jira("RHINENG-21518", category=iqe_blocker.AUTOMATION_ISSUE))
    def test_filter_by_workspace(
        self,
        navigate_to_systems_page,
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        metadata:
            requirements: inv-hosts-filter-by-group_name
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by workspace
        """
        workspaces = setup_ui_workspaces_with_hosts_for_sorting
        view = navigate_to_systems_page
        view.refresh_page()

        # view.search({workspaces[0].name: True}, column="Workspace")
        view.column_selector.item_select("Workspace")
        view.find_input_box.fill(workspaces[0].name)

        workspace_in_column = view.table.row().workspace.text
        assert workspaces[0].name == workspace_in_column
        assert workspaces[0].name in view.get_filters_list()

    def test_filter_by_ungrouped_hosts(
        self,
        navigate_to_systems_page,
        setup_ui_hosts_for_sorting: list[HostOut],
        setup_ui_workspaces_with_hosts_for_sorting,
    ):
        """
        metadata:
            requirements: inv-hosts-filter-by-group_name, inv-kessel-ungrouped
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by "Ungrouped hosts"
        """
        workspace_filter, ungrouped_hosts = "Ungrouped hosts", "Ungrouped Hosts"

        view = navigate_to_systems_page
        view.search(UNIQUE_UI_ID, column="Name")

        view.search({workspace_filter: True}, column="Workspace")
        workspaces_column = [row.workspace.text for row in view.table.rows()]
        assert all(ungrouped_hosts in row for row in workspaces_column)

    def test_filter_by_tag(
        self,
        host_inventory_frontend: ApplicationHostInventory,
        navigate_to_systems_page,
        setup_ui_host_module: HostOut,
    ):
        """
        metadata:
            requirements: inv-hosts-filter-by-tags
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by tags
        """
        display_name = setup_ui_host_module.display_name
        response = host_inventory_frontend.apis.tags.get_tags(display_name=display_name)
        tag = convert_tag_to_string(response[0].tag.to_dict())
        view = navigate_to_systems_page

        view.search({tag: True}, column="Tags")
        assert view.table.row().name.text == display_name
        assert int(view.table.row().tags.widget.read()) == len(response)

    @pytest.mark.parametrize("system_type", ["Package-based system", "Image-based system"])
    def test_filter_by_system_type(
        self,
        navigate_to_systems_page,
        system_type: str,
        setup_ui_bootc_host: HostOut,
        setup_ui_host_module: HostOut,
    ):
        """JIRA: https://issues.redhat.com/browse/RHINENG-8957

        metadata:
            requirements: inv-hosts-filter-by-system_profile-bootc_status
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by system type
        """
        not_expected_type = (
            "Image-based system"
            if "Package-based system" in system_type
            else "Package-based system"
        )
        view = navigate_to_systems_page
        # to see fresh uploaded image mode system and filter "Systems type"
        # in UI user need to refresh page
        view.refresh_page()

        view.search({system_type: True}, column="System type")
        wait_for(lambda: view.top_paginator.is_displayed, timeout=20)
        filtered_systems = view.get_systems_count_by_type()

        assert filtered_systems[system_type] > 0
        assert filtered_systems[not_expected_type] == 0

    @pytest.mark.smoke
    @pytest.mark.parametrize("operating_system", ["RHEL", "CentOS Linux"])
    def test_filter_by_os(
        self,
        navigate_to_systems_page,
        setup_ui_hosts_with_different_os: list[str],
        host_inventory_frontend: ApplicationHostInventory,
        operating_system: str,
    ):
        """
        metadata:
            requirements: inv-hosts-filter-by-sp-operating_system
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by OS
        """
        # setup hosts with different OS
        centos_label = "Convert system to RHEL"
        per_page_default = 50

        if operating_system == "RHEL":
            os_version = setup_ui_hosts_with_different_os[0]
        else:
            base_archive, core_collect = get_archive_and_collect_method(operating_system)
            os = get_default_os_centos()
            host_inventory_frontend.upload.create_host(
                operating_system=os,
                base_archive=base_archive,
                core_collect=core_collect,
            )
            os = get_default_os_centos()
            os_version = f"{os['name']} {os['major']}.{os['minor']}"

        view = navigate_to_systems_page
        view.refresh_page()
        view.search({os_version: True}, column="Operating system")
        if view.results > per_page_default:
            view.top_paginator.last_page()

        for row in view.table.rows():
            assert os_version == row.os.widget.text
            if operating_system == "CentOS Linux":
                assert centos_label in row.name.text, "CentOS system should have label"

    def test_filter_by_os_major_version(
        self, navigate_to_systems_page, setup_ui_hosts_with_different_os: list[str]
    ):
        """JIRA: https://issues.redhat.com/browse/ESSNTL-3341

        metadata:
            requirements: inv-hosts-filter-by-sp-operating_system
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Filtering systems by OS: major version
        """
        # setup_ui_hosts_with_different_os fixture prepare 2 hosts
        # with diffrent RHEL 7 minor versions
        major = 7
        major_os = f"RHEL {major}"
        view = navigate_to_systems_page
        view.search({major_os: True}, column="Operating system")
        row_count = list(view.table.rows())
        assert len(row_count) >= 2

        for row in view.table.rows():
            assert major == int(row.os.widget.text[5]), (
                "Filter with wrong OS major version was applied."
            )

        # reset multiple OS via deselecting OS with major os version
        view.search({major_os: False}, column="Operating system")
        assert len(view.get_filters_list()) == 0


@pytest.mark.core
class TestUITagsHosts:
    def test_tag_modal_count(self, setup_ui_host_module: HostOut, navigate_to_systems_page):
        """Test that we get the correct number of tags in the tag modal

        metadata:
            requirements: inv-hosts-get-tags
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Tags modal
        """
        view = navigate_to_systems_page
        row = view.find_row(search=setup_ui_host_module.display_name, column="Name")
        try:
            tag_count = int(row.tags.widget.read())
        except ValueError:
            tag_count = 0
        # archive upload host with 5 tags
        assert tag_count == 5

        row.tags.widget.click()
        assert setup_ui_host_module.display_name in view.tags_modal.title
        assert view.tags_modal.tag_count == tag_count
        view.tags_modal.close()

    @pytest.mark.parametrize("apply_via_modal", [True, False])
    def test_global_tag_filter(
        self,
        host_inventory_frontend: ApplicationHostInventory,
        setup_ui_host_module: HostOut,
        navigate_to_systems_page,
        apply_via_modal: bool,
        request,
    ):
        """
        metadata:
            requirements: inv-tags-get-list, inv-hosts-filter-by-tags
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Global tag filter
        """
        response = host_inventory_frontend.apis.tags.get_tags(
            display_name=setup_ui_host_module.display_name
        )
        tag = response[0].tag.to_dict()

        view = navigate_to_systems_page

        view.select_tags([tag], view_all=apply_via_modal)
        assert view.table.row().name.text == setup_ui_host_module.display_name
        assert view.results == 1, f"Only 1 host exists with tag: {tag}"

        view.clear_tags()
        assert view.table.row_count > 1

    def test_global_tag_workload_count(self, navigate_to_systems_page, request):
        """
        Test that the global tag filter menu displays right amount of systems
        for workload

        metadata:
            requirements:
                - inv-hosts-filter-by-sp-sap_sids
                - inv-hosts-filter-by-system_profile-ansible
                - inv-hosts-filter-by-system_profile-mssql
            assignee: zabikeno
            importance: critical
            title: Inventory UI: Global tag filter
        """
        view = navigate_to_systems_page

        counts = view.tag_filter.workloads_counts
        for workload, count in counts.items():
            view.select_tags({workload: True})
            assert view.top_paginator.total_items == int(count)
            view.select_tags({workload: False})


@pytest.mark.usefixtures("destination")
class TestSystemsTableConsistency:
    @pytest.mark.ephemeral
    def test_systems_table_consistency_sorting(self, destination: str, step_obj) -> None:
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: zabikeno
            importance: medium
            title: Test that the table layout remains the same after column sorting
        """
        view = navigate_to(step_obj[destination], destination)
        if destination == "Systems":
            view.refresh_page()
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)

        # Grab the initial state the table
        initial_headers = view.table.headers
        initial_systems = view.results
        initial_per_page = view.top_paginator.current_per_page

        # Sort the sortable columns in both direction
        for direction in ["ascending", "descending"]:
            for column in view.table.headers:
                if column and column != "Tags":
                    view.table.sort_by(column, direction)
                    assert view.compare_table_headers(initial_headers)
                    assert view.results == initial_systems
                    assert view.top_paginator.current_per_page == initial_per_page

    def test_systems_table_sort_by_os_withstands_refresh(
        self, destination: str, step_obj, setup_ui_hosts_with_different_os: list[str]
    ) -> None:
        """
        metadata:
            requirements: inv-hosts-sorting
            assignee: fstavela
            importance: medium
            title: Inventory UI: Sorting systems withstands page refresh
        """
        if destination in ["SystemsTab", "AddSystemsToWorkspace"]:
            pytest.xfail(f"Test is expected for Systems page, not for {destination}.")

        # Prepare hosts with required OS versions
        os_filter_options = setup_ui_hosts_with_different_os

        view = navigate_to(step_obj[destination], destination)
        # refresh is required to see new OS in filter menu for uploaded hosts
        view.refresh_page()
        view.name_search(UNIQUE_UI_ID)

        view.search(
            dict.fromkeys(os_filter_options, True), column="Operating system", is_checkbox=True
        )

        view.table.sort_by("OS", "ascending")
        sorted_os_before_refresh = [row.os.widget.text for row in view.table.rows()]

        sorted_os_versions_before_refresh = [os.strip("RHEL ") for os in sorted_os_before_refresh]
        expected_sorted_os_versions = sorted(sorted_os_versions_before_refresh, key=StrictVersion)

        assert sorted_os_versions_before_refresh == expected_sorted_os_versions

        view.refresh_page()
        sorted_os_after_refresh = [row.os.widget.text for row in view.table.rows()]
        sorted_os_versions_after_refresh = [os.strip("RHEL ") for os in sorted_os_after_refresh]

        assert sorted_os_versions_after_refresh == sorted_os_versions_before_refresh

    @pytest.mark.ephemeral
    @pytest.mark.parametrize("per_page", [10, 100])
    def test_systems_table_pagination(
        self,
        destination: str,
        step_obj,
        per_page: int,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        metadata:
            requirements: inv-pagination
            assignee: zabikeno
            importance: medium
            title: Test that the table layout remains after applying pagination
        """
        view = navigate_to(step_obj[destination], destination)
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)
        request.addfinalizer(view.pagination_go_to_first_page)
        wait_for(lambda: view.column_selector.is_displayed, timeout=10)
        # Grab the initial state of the table
        initial_headers = view.table.headers
        initial_systems = view.results

        view.top_paginator.set_per_page(per_page)
        wait_for(lambda: view.top_paginator.is_displayed, timeout=10)
        initial_page = view.bottom_paginator.current_page
        initial_pages = view.bottom_paginator.total_pages
        # Run through all the actions for pagination in the top and bottom paginators
        for paginator in [view.top_paginator, view.bottom_paginator]:
            view.paginator.next_page()
            wait_for(lambda: view.top_paginator.is_displayed, timeout=10)

            assert view.compare_table_headers(initial_headers)
            assert view.bottom_paginator.current_page == initial_page + 1
            assert view.results == initial_systems
            assert view.bottom_paginator.total_pages == initial_pages

            paginator.previous_page()
            wait_for(lambda: view.top_paginator.is_displayed, timeout=10)

            assert view.compare_table_headers(initial_headers)
            assert view.bottom_paginator.current_page == initial_page
            assert view.results == initial_systems
            assert view.bottom_paginator.total_pages == initial_pages
