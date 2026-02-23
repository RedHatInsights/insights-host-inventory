import locale
import logging
from contextlib import contextmanager

import pytest
from dateutil import parser

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils import rand_start_end
from iqe_host_inventory.utils.api_utils import acceptance
from iqe_host_inventory.utils.api_utils import criterion_count_eq
from iqe_host_inventory.utils.api_utils import criterion_total_gte
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory_api import GroupOutWithHostCount

logger = logging.getLogger(__name__)
pytestmark = [pytest.mark.backend]


@contextmanager
def _changed_locale(new_locale):
    old_locale = locale.getlocale(locale.LC_COLLATE)
    try:
        locale.setlocale(locale.LC_COLLATE, new_locale)
        yield locale.strxfrm
    finally:
        locale.setlocale(locale.LC_COLLATE, old_locale)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_pagination(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Pagination.

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-637

    Create hosts and paginate through the results.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Pagination
    """

    def _getpage(page):
        page_content = host_inventory.apis.hosts.get_hosts_response(per_page=10, page=page)
        return page_content.results

    page1_content = _getpage(1)
    page2_content = _getpage(2)

    assert page1_content != page2_content


def test_pagination_invalid_page_index(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Pagination with Invalid Page Index.

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-637

    Try to navigate by specifying invalid page indexes.

    1. first page -1
    2. last page +1

    metadata:
        requirements: inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: Test Pagination with Invalid Page Index
    """
    pg = host_inventory.apis.hosts.get_host_pagination_info()

    # last page +1
    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts(per_page=pg.per_page, page=pg.total_pages + 1)

    # first page -1
    with raises_apierror(400):
        host_inventory.apis.hosts.get_hosts(per_page=pg.per_page, page=0)


@pytest.mark.parametrize(
    "invalid_page_number",
    [
        "?",
        "-1",
        ".",
        "1.",
        "x",
    ],
)
def test_pagination_invalid_pages(
    invalid_page_number, host_inventory, hbi_setup_hosts_for_pagination
):
    """
    Test Pagination with Invalid Page Number Values.

    JIRA: https://projects.engineering.redhat.com/browse/RHIPLAT1-637

    Try to navigate by specifying invalid values for page number. Expect 400 status code.

    metadata:
        requirements: inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: Test Pagination with Invalid Page Number Values
    """
    pg = host_inventory.apis.hosts.get_host_pagination_info()

    with raises_apierror(400):
        host_inventory.apis.hosts.get_hosts_response(
            per_page=pg.per_page, page=invalid_page_number
        )


@pytest.mark.smoke
@pytest.mark.qa
def test_unique_results_by_id(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Pagination Uniqueness of Results.

    Confirm that each page contains a unique set of results according to the host id.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Paginated Results Are Unique
    """
    pg = host_inventory.apis.hosts.get_host_pagination_info()
    total_page = pg.total_pages
    per_page = pg.per_page

    assert total_page > 1
    assert per_page == 10

    total_hosts = 0
    random_start, end = rand_start_end(total_page, 10)

    logger.info("Probing starting with page %d", random_start)
    set_of_all_hosts: set[str] = set()
    last_result = None
    for i in range(random_start, end):
        response = host_inventory.apis.hosts.get_hosts_response(page=i, per_page=per_page)
        assert response is not None
        total_hosts = total_hosts + len(response.results)
        these_hosts = [x.id for x in response.results]
        overlap = set_of_all_hosts & set(these_hosts)
        if len(overlap) == 0:
            assert in_order(last_result, response.results, ascending=False)

        set_of_all_hosts = set_of_all_hosts.union(these_hosts)
        count = response.count
        last_result = response.results[count - 1]
    logger.info(f"Number of unique host IDs: {len(set_of_all_hosts)}")
    # Putting a tolerance of 3 duplicate hosts here because the account is shared and tests from
    # other plugins can affect this test
    assert len(set_of_all_hosts) + 3 >= total_hosts


def compare_display_names(prev_name, next_name, case_sensitive=False):
    """Compare two display names with an option for case sensitivity."""
    if prev_name is None and next_name is None:
        return 1

    if not case_sensitive:
        prev_name = prev_name.lower()
        next_name = next_name.lower()

    # All results should now come from x-join, which sorts using the default `C` collation,
    # so I'm commenting the next 4 lines
    # # Changing locale to match with PostgreSQL sort
    # with _changed_locale("en_US.utf8") as strxfrm:
    #     prev_name = strxfrm(prev_name)
    #     next_name = strxfrm(next_name)

    if prev_name < next_name:
        return -1
    elif prev_name > next_name:
        return 1
    elif prev_name == next_name:
        return 0


def compare_dates(date1, date2):
    """Compare two dates, presented as datetime."""

    if isinstance(date1, str):
        date1 = parser.parse(date1)
    if isinstance(date2, str):
        date2 = parser.parse(date2)
    if date1 == date2:
        return 0

    assert bool(date1) and bool(date2)

    return -1 if date1 < date2 else 1


def compare_operating_systems(os1: dict, os2: dict):
    """Compare two operating systems, presented as dictionaries."""
    if not os1:
        return 0 if not os2 else -1
    if not os2:
        return 1
    if os1 == os2:
        return 0

    os_keys_by_priority = ("name", "major", "minor")
    for os_key in os_keys_by_priority:
        os1_key = getattr(os1, os_key)
        os2_key = getattr(os2, os_key)
        if os1_key != os2_key:
            if os2_key is None:
                return 1
            return -1 if os1_key is None or os1_key < os2_key else 1


def compare_groups(
    groups1: list[GroupOutWithHostCount],
    groups2: list[GroupOutWithHostCount],
    case_sensitive: bool = False,
) -> int:
    """Compare two groups lists."""
    if not groups1:
        return 0 if not groups2 else -1
    if not groups2:
        return 1

    assert len(groups1) == len(groups2) == 1  # A host can only be part of 1 group

    name1 = (
        ""
        if groups1[0].ungrouped is True
        else groups1[0].name
        if case_sensitive
        else groups1[0].name.lower()
    )
    name2 = (
        ""
        if groups2[0].ungrouped is True
        else groups2[0].name
        if case_sensitive
        else groups2[0].name.lower()
    )

    if name1 < name2:
        return -1
    if name1 > name2:
        return 1
    return 0


def in_order(last_result, current_results, sort_field="updated", ascending=True):  # NOQA: C901
    """Confirm this set of results is in sorted ascending order by created_date and id."""

    def _get_field(host, field_name):
        if field_name == "operating_system":
            return host.system_profile.operating_system
        if field_name == "group_name":
            return host.groups
        return getattr(host, field_name)

    if ascending:
        comparator_value = -1
        order_description = f"{sort_field} - Ascending"
    else:
        comparator_value = 1
        order_description = f"{sort_field} - Descending"

    if sort_field in ["updated", "last_check_in"]:
        comparator_func = compare_dates
    elif sort_field == "display_name":
        comparator_func = compare_display_names
    elif sort_field == "operating_system":
        comparator_func = compare_operating_systems
    elif sort_field == "group_name":
        comparator_func = compare_groups
    else:
        raise ValueError(f"Unsupported sort_field: {sort_field}")

    if last_result is not None:
        lr = _get_field(last_result, sort_field)
        cr = _get_field(current_results[0], sort_field)
        comparison_result = comparator_func(lr, cr)
        if comparison_result not in (comparator_value, 0):
            out_of_order(order_description, lr, cr, current_results)
            return False

    prev_result = None
    for cur_result in current_results:
        if prev_result is not None:
            pr = _get_field(prev_result, sort_field)
            cr = _get_field(cur_result, sort_field)
            comparison_result = comparator_func(pr, cr)
            if comparison_result not in (comparator_value, 0):
                out_of_order(order_description, pr, cr, current_results)
                return False
        prev_result = cur_result

    return True


def out_of_order(sort_order, result1, result2, results_page):
    logger.error("When sort order is %s", sort_order)
    logger.error("Out of order: %s should not come before %s", result1, result2)
    logger.error("Page with out-of-order data: %s", results_page)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_unique_results_by_display_name(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Paginated Results By display_name are Unique.

    Confirm paginated results are unique when filtered by display_name.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Paginated Results By display_name are Unique
    """
    response = host_inventory.apis.hosts.get_hosts_response(display_name="pagination")
    assert response is not None

    total_matching_hosts = response.total

    assert total_matching_hosts > 0

    random_start, end = rand_start_end(total_matching_hosts, 10)

    all_hosts: set[str] = set()
    total_paged_hosts = 0
    for i in range(random_start, end):
        response = host_inventory.apis.hosts.get_hosts_response(
            per_page=1, page=i, display_name="pagination"
        )

        assert response is not None

        all_hosts.update(x.id for x in response.results)
        total_paged_hosts = total_paged_hosts + len(response.results)

    assert total_paged_hosts == len(all_hosts)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_unique_results_for_id_list(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Pagination of Multi-Host Request Contains Unique Results.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Pagination of Multi-Host Request Contains Unique Results
    """
    all_hosts: list[str] = [host.id for host in hbi_setup_hosts_for_pagination]
    total_results = len(all_hosts)
    all_paginated_results: set[str] = set()
    num_iterations = 10

    assert total_results > num_iterations, "This shouldn't fail unless something big has changed"

    rand_start, end = rand_start_end(total_results, num_iterations)
    for i in range(rand_start, end):
        # order by display name to prevent mid test updates
        # changing the id order from the updated column
        # todo: order by id or given id list in host inventory supported
        response = host_inventory.apis.hosts.get_hosts_by_id_response(
            all_hosts, per_page=1, page=i, order_by="display_name"
        )

        assert len(response.results)

        old_len = len(all_paginated_results)
        all_paginated_results.add(response.results[0].id)
        new_len = len(all_paginated_results)
        if old_len + 1 != new_len:
            pytest.fail("Duplicate found with id: " + response.results[0].id)

    assert len(all_paginated_results) == num_iterations


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_unique_results_by_hostname_or_id(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Paginated Results when filtered by hostname_or_id are unique.

    Confirm results of a GET filtered by hostname_or_id parameter are unique.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Pagination of Multi-Host Request Contains Unique Results
    """
    search_str = "pagination"
    paged_hosts = set()
    total_hosts = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=search_str).total
    num_iterations = 10

    assert total_hosts > num_iterations, "This shouldn't fail unless something big has changed"

    rand_start, end = rand_start_end(total_hosts, num_iterations)
    for i in range(rand_start, end):
        response = host_inventory.apis.hosts.get_hosts_response(
            hostname_or_id=search_str, per_page=1, page=i
        )

        assert hasattr(response, "results")
        assert len(response.results) == 1

        paged_hosts.add(response.results[0].id)

    """
    Sometimes the number of hosts changes in the middle of the test due
    concurrent jobs/tests running at the same time. So it is normal to see a
    "race condition" situation affecting the number of hosts.

    This is not a BUG though but it may affect the test result.

    The try/except below checks if the total number of hosts has
    changed if the test fail due the situation described above.
    """
    try:
        assert num_iterations == len(paged_hosts)
    except AssertionError:
        new_total_hosts = host_inventory.apis.hosts.get_hosts_response(
            hostname_or_id=search_str
        ).total

        assert new_total_hosts != total_hosts


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_pagination_of_system_profile_fetching(host_inventory, hbi_setup_hosts_for_pagination):
    """
    Test Paginated Results of GET for system_profile details are unique.

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: critical
        title: Inventory: Paginated Results of GET for system_profile are unique
    """
    all_hosts = [host.id for host in hbi_setup_hosts_for_pagination]
    paged_hosts = set()
    num_hosts = len(all_hosts)
    num_iterations = 10

    assert num_hosts > num_iterations, "This shouldn't fail unless something big has changed"

    rand_start, end = rand_start_end(num_hosts, num_iterations)
    for i in range(rand_start, end):
        response = host_inventory.apis.hosts.get_hosts_system_profile_response(
            all_hosts, per_page=1, page=i
        )

        assert hasattr(response, "results"), f"Response for page {i} was not good"

        paged_hosts.add(response.results[0].id)

    assert num_iterations == len(paged_hosts), str(paged_hosts)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_pagination_of_tags(
    hbi_setup_hosts_for_pagination, host_inventory: ApplicationHostInventory
):
    """
    Test Paginated Results of GET for tags are unique.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5676

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: high
        title: Inventory: Paginated Results of GET for tags are unique
    """
    all_tags = acceptance(
        host_inventory.apis.tags.get_tags_response,
        display_name="pagination",
        criteria=[(criterion_total_gte, 40)],
    )
    paged_tags = set()
    num_tags = all_tags.total
    num_iterations = 10
    rand_start, end = rand_start_end(num_tags, num_iterations)
    for i in range(rand_start, end):
        response = acceptance(
            host_inventory.apis.tags.get_tags_response,
            per_page=1,
            page=i,
            display_name="pagination",
            criteria=[(criterion_count_eq, 1)],
        )

        assert hasattr(response, "results"), f"Response for page {i} was not good"

        paged_tags.add(convert_tag_to_string(response.results[0].tag.to_dict()))

    assert num_iterations == len(paged_tags), str(paged_tags)


@pytest.mark.parametrize("tags_per_page", [5, 10, 15, 25, 50, 100])
def test_pagination_tags_number_of_records(
    hbi_setup_hosts_for_pagination, host_inventory: ApplicationHostInventory, tags_per_page
):
    """
    Test Paginated Results of GET for tags return the correct amount of tags.

    JIRA: https://projects.engineering.redhat.com/browse/RHCLOUD-5676

    metadata:
        requirements: inv-pagination
        assignee: fstavela
        importance: high
        title: Inventory: Paginated Results of GET for tags return
            the correct amount of tags
    """
    response = acceptance(
        host_inventory.apis.tags.get_tags_response,
        per_page=tags_per_page,
        criteria=[(criterion_count_eq, tags_per_page)],
    )

    assert hasattr(response, "results"), "Response for page {} was not good"
    assert response.count == tags_per_page
