from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
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
        elif field_name == "type":
            # type field is only in RBAC v2 workspaces, not in OpenAPI model
            # Derive it from the ungrouped field which IS in the model
            return "ungrouped-hosts" if group.ungrouped else "standard"
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
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_by_id_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3849

    metadata:
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
