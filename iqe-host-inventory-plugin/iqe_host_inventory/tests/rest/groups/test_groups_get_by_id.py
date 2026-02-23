from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.tests.rest.validation.test_system_profile import EMPTY_BASICS
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def compare_names(prev_name: str, next_name: str) -> int:
    prev_name = prev_name.lower()
    next_name = next_name.lower()

    if prev_name == next_name:
        return 0

    return -1 if prev_name < next_name else 1


def compare_hosts_counts(prev_count: int, next_count: int) -> int:
    if prev_count == next_count:
        return 0

    return -1 if prev_count < next_count else 1


def compare_dates(date1: datetime, date2: datetime) -> int:
    if date1 == date2:
        return 0

    return -1 if date1 < date2 else 1


def in_order(
    current_results: list[GroupOutWithHostCount],
    last_result: GroupOutWithHostCount | None = None,
    sort_field: str = "name",
    ascending: bool = True,
) -> bool:
    """Confirm this set of results is sorted in correct order"""

    def _get_field(group: GroupOutWithHostCount, field_name: str):
        if field_name == "host_count":
            return group.host_count
        return getattr(group, field_name)

    expected_compare_result = -1 if ascending else 1
    sort_funcs: dict[str, Callable[[Any, Any], int]] = {
        "name": compare_names,
        "host_count": compare_hosts_counts,
        "updated": compare_dates,
    }
    try:
        comparator_func = sort_funcs[sort_field]
    except LookupError as e:
        raise ValueError(
            f"Valid options for sort_field: [name, host_count, updated]. Provided: {sort_field}"
        ) from e

    if last_result is not None:
        lr = _get_field(last_result, sort_field)
        cr = _get_field(current_results[0], sort_field)
        comparison_result = comparator_func(lr, cr)
        if comparison_result not in (expected_compare_result, 0):
            return False

    prev_result = None
    for cur_result in current_results:
        if prev_result is not None:
            pr = _get_field(prev_result, sort_field)
            cr = _get_field(cur_result, sort_field)
            comparison_result = comparator_func(pr, cr)
            if comparison_result not in (expected_compare_result, 0):
                return False
        prev_result = cur_result

    return True


@pytest.mark.ephemeral
@pytest.mark.parametrize("n_hosts", [0, 1, 3])
def test_groups_get_by_id_single_group(host_inventory: ApplicationHostInventory, n_hosts: int):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get a single group by ID
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:n_hosts])

    host_inventory.apis.groups.create_n_empty_groups(3)

    response = host_inventory.apis.groups.get_groups_by_id_response(group)
    assert response.total == 1
    assert response.count == 1
    assert len(response.results) == 1
    assert response.results[0] == group


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_by_id_multiple_groups(
    host_inventory: ApplicationHostInventory, with_hosts: bool
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get multiple groups by IDs
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    groups_data = []
    for i in range(3):
        group_hosts = [hosts[i]] if with_hosts else []
        groups_data.append(GroupData(hosts=group_hosts))
    groups = host_inventory.apis.groups.create_groups(groups_data)
    orig_groups_dict = {group.id: group for group in groups}

    host_inventory.apis.groups.create_n_empty_groups(3)

    response = host_inventory.apis.groups.get_groups_by_id_response(groups)
    assert response.total == 3
    assert response.count == 3
    assert len(response.results) == 3
    assert {group.id for group in response.results} == set(orig_groups_dict.keys())
    for group in response.results:
        assert group == orig_groups_dict[group.id]


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_by_id_pagination(host_inventory: ApplicationHostInventory, with_hosts: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Test pagination while getting groups by their IDs
    """
    hosts = host_inventory.kafka.create_random_hosts(10)

    groups_data = [GroupData(hosts=[hosts[i]] if with_hosts else []) for i in range(10)]
    groups = host_inventory.apis.groups.create_groups(groups_data)
    all_groups_ids = {group.id for group in groups}

    found_groups_ids = set()
    for i in range(4):
        response = host_inventory.apis.groups.get_groups_by_id_response(
            groups, per_page=3, page=i + 1
        )
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total == 10
        if i == 3:
            # last page
            assert response.count == 1
            assert len(response.results) == 1
        else:
            assert response.count == 3
            assert len(response.results) == 3
        found_groups_ids.update({group.id for group in response.results})

    assert found_groups_ids == all_groups_ids


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_by_id_ordering(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get groups by IDs - test ordering parameters
    """
    groups = setup_groups_for_ordering

    response = host_inventory.apis.groups.get_groups_by_id_response(
        groups, order_by=order_by, order_how=order_how
    )
    assert response.page == 1
    assert response.total == 10
    assert response.count == 10
    assert len(response.results) == 10
    assert in_order(response.results, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_by_id_ordering_and_pagination(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get groups by IDs - paginate through ordered results
    """
    groups = setup_groups_for_ordering
    all_groups_ids = {group.id for group in groups}

    found_groups = []
    for i in range(4):
        response = host_inventory.apis.groups.get_groups_by_id_response(
            groups, per_page=3, page=i + 1, order_how=order_how, order_by=order_by
        )
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total == 10
        if i == 3:
            # last page
            assert response.count == 1
            assert len(response.results) == 1
        else:
            assert response.count == 3
            assert len(response.results) == 3
        found_groups += response.results

    assert {group.id for group in found_groups} == all_groups_ids
    assert in_order(found_groups, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
def test_groups_get_by_id_order_how_default(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get groups by IDs - default values for order_how parameter
    """
    ascending = order_by == "name"
    groups = setup_groups_for_ordering

    response = host_inventory.apis.groups.get_groups_by_id_response(groups, order_by=order_by)
    assert response.page == 1
    assert response.total == 10
    assert response.count == 10
    assert len(response.results) == 10
    assert in_order(response.results, None, ascending=ascending, sort_field=order_by)


@pytest.mark.ephemeral
def test_groups_get_by_id_order_by_default(host_inventory, setup_groups_for_ordering):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id
      assignee: fstavela
      importance: high
      title: Get groups by IDs - default value for order_by parameter
    """
    groups = setup_groups_for_ordering

    response = host_inventory.apis.groups.get_groups_by_id_response(groups)
    assert response.page == 1
    assert response.total == 10
    assert response.count == 10
    assert len(response.results) == 10
    assert in_order(response.results, None, ascending=True, sort_field="name")


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_by_id_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id, inv-account-integrity
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups by IDs - try to get group from different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    with raises_apierror(404):
        host_inventory.apis.groups.get_groups_by_id_response(groups_secondary[0])


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_by_id_my_and_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
      requirements: inv-groups-get-by-id, inv-account-integrity
      assignee: fstavela
      importance: critical
      title: Get groups by IDs - try to get groups from my and different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_primary = host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    # Make sure we get 404 when trying to get a group from a different account
    with raises_apierror(404):
        response = host_inventory.apis.groups.get_groups_by_id_response([
            groups_primary[0],
            groups_secondary[0],
            groups_primary[1],
        ])

    response = host_inventory.apis.groups.get_groups_by_id_response([
        groups_primary[0],
        groups_primary[1],
    ])
    assert response.count == 2
    assert response.total == 2
    assert response.page == 1
    assert {group.id for group in response.results} == {group.id for group in groups_primary[:2]}


class TestGetGroupByIDEmptyGroups:
    """
    This class is used for test scenarios on GET /groups/<groups_ids> endpoint
    that use just empty groups and don't require any special groups or hosts.
    """

    def test_groups_get_by_id_per_page_min(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          title: Get groups by IDs - minimum for per_page param (1)
        """
        groups = setup_empty_groups_primary[:3]
        response = host_inventory.apis.groups.get_groups_by_id_response(groups, per_page=1)
        assert response.page == 1
        assert response.per_page == 1
        assert response.total == 3
        assert response.count == 1
        assert len(response.results) == 1

    def test_groups_get_by_id_per_page_max(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          title: Get groups by IDs - maximum for per_page param (100)
        """
        groups = setup_empty_groups_primary
        response = host_inventory.apis.groups.get_groups_by_id_response(groups, per_page=100)
        assert response.page == 1
        assert response.per_page == 100
        assert response.total == len(groups)
        assert response.count == 100
        assert len(response.results) == 100

    @pytest.mark.parametrize("per_page", [0, -1, 101])
    def test_groups_get_by_id_per_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for per_page param (out of bounds)
        """
        groups = setup_empty_groups_primary[:103]
        error_msgs: tuple[str, ...]
        if per_page < 1:
            error_msgs = (f"{per_page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{per_page} is greater than the maximum of 100",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 50}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.groups.get_groups_by_id_response(groups, per_page=per_page)

    @pytest.mark.parametrize(
        "per_page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="str"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_groups_get_by_id_per_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, per_page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for per_page param (wrong data type)
        """
        groups = setup_empty_groups_primary[:3]
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(
        #     400, "Wrong type, expected 'integer' for query parameter 'per_page'"
        # ):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.groups.get_groups_by_id_response(groups, per_page=per_page)

    def test_groups_get_by_id_page_min(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Get groups by IDs - minimum for page param (1)
        """
        groups = setup_empty_groups_primary[:3]
        response = host_inventory.apis.groups.get_groups_by_id_response(groups, page=1)
        assert response.page == 1
        assert response.total == 3
        assert response.count == 3
        assert len(response.results) == 3

    def test_groups_get_by_id_page_max(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          title: Get groups by IDs - maximum for page param (21474837)
        """
        groups = setup_empty_groups_primary[:3]
        response = host_inventory.apis.groups.get_groups_by_id_response(groups, page=21474837)
        assert response.page == 21474837
        assert response.total == 3
        assert response.count == 0
        assert len(response.results) == 0

    @pytest.mark.parametrize("page", [0, -1, 21474838])
    def test_groups_get_by_id_page_out_of_bounds(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for page param (out of bounds)
        """
        groups = setup_empty_groups_primary[:3]
        error_msgs: tuple[str, ...]
        if page < 1:
            error_msgs = (f"{page} is less than the minimum of 1",)
        else:
            error_msgs = (f"{page} is greater than the maximum of 21474837",)
        error_msgs += ("{'type': 'integer', 'minimum': 1, 'maximum': 21474837, 'default': 1}",)

        with raises_apierror(400, error_msgs):
            host_inventory.apis.groups.get_groups_by_id_response(groups, page=page)

    @pytest.mark.parametrize(
        "page",
        (
            *EMPTY_BASICS,
            pytest.param([1], id="list of single int"),
            pytest.param([1, 2], id="list of multiple ints"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_groups_get_by_id_page_bad_type(
        self, setup_empty_groups_primary, host_inventory, page
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for page param (wrong data type)
        """
        groups = setup_empty_groups_primary[:3]
        # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
        # with raises_apierror(400, "Wrong type, expected 'integer' for query parameter 'page'"):
        with raises_apierror(400, "Wrong type, expected 'integer' for"):
            host_inventory.apis.groups.get_groups_by_id_response(groups, page=page)

    def test_groups_get_by_id_page_without_groups(
        self, setup_empty_groups_primary, host_inventory
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          title: Get groups by IDs - page without any groups
        """
        groups = setup_empty_groups_primary[:3]
        response = host_inventory.apis.groups.get_groups_by_id_response(groups, per_page=1, page=4)
        assert response.page == 4
        assert response.per_page == 1
        assert response.total == 3
        assert response.count == 0
        assert len(response.results) == 0

    def test_groups_get_by_id_pagination_default(self, setup_empty_groups_primary, host_inventory):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Get groups by IDs - default values for pagination parameters
        """
        groups = setup_empty_groups_primary[:100]
        response = host_inventory.apis.groups.get_groups_by_id_response(groups)
        assert response.page == 1
        assert response.per_page == 50
        assert response.total == 100
        assert response.count == 50
        assert len(response.results) == 50

    @pytest.mark.parametrize(
        "order_by",
        (
            *EMPTY_BASICS,
            pytest.param(1, id="int"),
            pytest.param(["name", "host_count"], id="list of values"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    def test_groups_get_by_id_order_by_bad_type(
        self, setup_empty_groups_primary, host_inventory, order_by
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for order_by param (wrong data type)
        """
        groups = setup_empty_groups_primary[:3]
        with raises_apierror(
            400,
            (
                f"{order_by}",
                "is not one of ['name', 'host_count', 'updated']",
                "{'type': 'string', 'enum': ['name', 'host_count', 'updated']}",
            ),
        ):
            host_inventory.apis.groups.get_groups_by_id_response(groups, order_by=order_by)

    @pytest.mark.parametrize(
        "order_how",
        (
            *EMPTY_BASICS,
            pytest.param(1, id="int"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid(), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
            pytest.param("", id="empty string"),
        ),
    )
    @pytest.mark.parametrize("order_by", ["name", "host_count"])
    def test_groups_get_by_id_order_how_bad_type(
        self, setup_empty_groups_primary, host_inventory, order_how, order_by
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong value for order_how param (wrong data type)
        """
        groups = setup_empty_groups_primary[:3]
        with raises_apierror(
            400, f"'{order_how}' does not match '^([Aa][Ss][Cc])|([Dd][Ee][Ss][Cc])$'"
        ):
            host_inventory.apis.groups.get_groups_by_id_response(
                groups, order_how=order_how, order_by=order_by
            )

    @pytest.mark.parametrize("how_many", [1, 3])
    def test_groups_get_by_id_not_existing(
        self, setup_empty_groups_primary, host_inventory, how_many
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: medium
          negative: true
          title: Get groups by IDs - not existing group
        """
        groups_ids = [generate_uuid() for _ in range(how_many)]
        with raises_apierror(404) as exc:
            host_inventory.apis.groups.get_groups_by_id_response(groups_ids)

        # Verify that the response body includes the not_found_ids field
        response_body = json.loads(exc.value.body)
        assert "not_found_ids" in response_body, "Expected 'not_found_ids' in response body"
        assert set(groups_ids) == set(response_body["not_found_ids"]), (
            f"Expected '{set(groups_ids)}' in not_found_ids, "
            f"got '{response_body['not_found_ids']}'"
        )

    def test_groups_get_by_id_good_and_non_existing(
        self, setup_empty_groups_primary, host_inventory
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: high
          title: Get groups by IDs - existing and not existing group
        """
        groups = setup_empty_groups_primary[:2]
        not_found_id = generate_uuid()

        # Make sure we get 404 when trying to get a group that doesn't exist
        with raises_apierror(404) as exc:
            host_inventory.apis.groups.get_groups_by_id_response([
                groups[0].id,
                not_found_id,
                groups[1].id,
            ])

        # Verify that the response body includes the not_found_ids field
        response_body = json.loads(exc.value.body)
        assert "not_found_ids" in response_body, "Expected 'not_found_ids' in response body"
        assert response_body["not_found_ids"] == [not_found_id], (
            f"Expected 'not_found_ids' to be '[{not_found_id}]', "
            f"got '{response_body['not_found_ids']}'"
        )

        response = host_inventory.apis.groups.get_groups_by_id_response([
            groups[0].id,
            groups[1].id,
        ])
        assert response.count == 2
        assert response.total == 2
        assert response.page == 1
        assert len(response.results) == 2

    @pytest.mark.parametrize(
        "group_id",
        (
            pytest.param([], id="empty list"),
            pytest.param({}, id="empty dict"),
            pytest.param(1, id="int"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid() + "a", id="bad uuid"),
            pytest.param(generate_string_of_length(36, use_punctuation=False), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
        ),
    )
    def test_groups_get_by_id_bad_group_id(
        self, setup_empty_groups_primary, host_inventory: ApplicationHostInventory, group_id
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - wrong group ID (wrong data type)
        """
        with raises_apierror(400, (f"{group_id}", " does not match ")):
            host_inventory.apis.groups.raw_api.api_group_get_groups_by_id([group_id])

    @pytest.mark.parametrize(
        "group_id",
        (
            *EMPTY_BASICS,
            pytest.param(1, id="int"),
            pytest.param(1.5, id="float"),
            pytest.param(generate_uuid() + "a", id="bad uuid"),
            pytest.param(generate_string_of_length(36, use_punctuation=False), id="random string"),
            pytest.param(True, id="True"),
            pytest.param(False, id="False"),
            pytest.param("None", id="None"),
        ),
    )
    def test_groups_get_by_id_good_and_bad_group_id(
        self,
        setup_empty_groups_primary: list[GroupOutWithHostCount],
        host_inventory: ApplicationHostInventory,
        group_id: str,
    ):
        """
        https://issues.redhat.com/browse/ESSNTL-3849

        metadata:
          requirements: inv-groups-get-by-id
          assignee: fstavela
          importance: low
          negative: true
          title: Get groups by IDs - good group and wrong group ID (wrong data type)
        """
        groups = setup_empty_groups_primary[:2]

        groups_ids = [groups[0].id, group_id, groups[1].id]
        with raises_apierror(400, (f"{group_id}", " does not match ")):
            host_inventory.apis.groups.raw_api.api_group_get_groups_by_id(groups_ids)
