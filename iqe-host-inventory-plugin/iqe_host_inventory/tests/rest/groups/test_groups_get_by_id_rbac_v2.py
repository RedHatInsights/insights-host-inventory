"""Tests for GET /groups/{group_id_list} with RBAC v2 (Kessel) feature flag enabled.

JIRA: RHINENG-17397

These tests verify that the GET /groups/{group_id_list} endpoint correctly uses
the RBAC v2 workspace API when the 'hbi.api.kessel-groups' feature flag is enabled.

The RBAC v2 path fetches group/workspace data from the Kessel RBAC v2 API instead
of querying the database directly. This is part of the broader Kessel migration.
"""

from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.tests.rest.groups.test_groups_get_by_id import in_order
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend, pytest.mark.ephemeral]
logger = logging.getLogger(__name__)


@pytest.mark.usefixtures("enable_kessel_groups")
@pytest.mark.parametrize("n_groups", [1, 3, 5])
def test_get_groups_by_id_rbac_v2_success(host_inventory: ApplicationHostInventory, n_groups: int):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get groups by IDs using RBAC v2 workspace API
    """
    # Create groups with hosts to verify host_count is correct
    hosts = host_inventory.kafka.create_random_hosts(n_groups)
    groups_data = [GroupData(hosts=[hosts[i]]) for i in range(n_groups)]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    # Fetch groups via RBAC v2 workspace API (feature flag enabled)
    response = host_inventory.apis.groups.get_groups_by_id_response(groups)

    assert response.total == n_groups
    assert response.count == n_groups
    assert len(response.results) == n_groups
    assert {group.id for group in response.results} == {group.id for group in groups}

    # Verify each group has correct host count
    for result_group in response.results:
        assert result_group.host_count == 1


@pytest.mark.usefixtures("enable_kessel_groups")
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_get_groups_by_id_rbac_v2_ordering(
    host_inventory: ApplicationHostInventory,
    setup_groups_for_ordering,
    order_by: str,
    order_how: str,
):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get groups by IDs with ordering using RBAC v2 workspace API
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


@pytest.mark.usefixtures("enable_kessel_groups")
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_get_groups_by_id_rbac_v2_ordering_and_pagination(
    host_inventory: ApplicationHostInventory,
    setup_groups_for_ordering,
    order_by: str,
    order_how: str,
):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get groups by IDs - paginate through ordered results using RBAC v2
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


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_pagination(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get groups by IDs with pagination using RBAC v2 workspace API
    """
    # Create 10 groups
    hosts = host_inventory.kafka.create_random_hosts(10)
    groups_data = [GroupData(hosts=[hosts[i]]) for i in range(10)]
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


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_not_found(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        negative: true
        title: Get non-existent groups by IDs using RBAC v2 (should return 404)
    """
    # Try to fetch groups that don't exist
    fake_group_ids = [generate_uuid() for _ in range(3)]

    with raises_apierror(404, "One or more groups not found"):
        host_inventory.apis.groups.raw_api.api_group_get_groups_by_id(fake_group_ids)


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_partial_not_found(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        negative: true
        title: Get groups by IDs with some missing (RBAC v2 should return 404)
    """
    # Create 2 valid groups
    groups_data = [GroupData() for _ in range(2)]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    # Mix valid and invalid group IDs
    mixed_ids = [groups[0].id, generate_uuid(), groups[1].id]

    with raises_apierror(404, "One or more groups not found"):
        host_inventory.apis.groups.raw_api.api_group_get_groups_by_id(mixed_ids)


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2, inv-account-integrity
        assignee: maarif
        importance: critical
        negative: true
        title: Get groups by IDs using RBAC v2 - try to get group from different account
    """
    # Create groups in both accounts
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [GroupData(hosts=[hosts_primary[i]]) for i in range(3)]
    groups_data_secondary = [GroupData(hosts=[hosts_secondary[i]]) for i in range(3)]

    host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    # Try to get secondary account's group from primary account (should fail)
    with raises_apierror(404):
        host_inventory.apis.groups.get_groups_by_id_response(groups_secondary[0])


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_empty_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Get empty groups by IDs using RBAC v2 workspace API
    """
    # Create groups without any hosts
    groups_data = [GroupData() for _ in range(3)]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    response = host_inventory.apis.groups.get_groups_by_id_response(groups)

    assert response.total == 3
    assert response.count == 3
    assert len(response.results) == 3

    # Verify all groups have zero host count
    for result_group in response.results:
        assert result_group.host_count == 0


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_single_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get a single group by ID using RBAC v2 workspace API
    """
    # Create a single group with hosts
    hosts = host_inventory.kafka.create_random_hosts(3)
    group = host_inventory.apis.groups.create_group(hosts=hosts)

    # Create other groups to ensure we only get the requested one
    host_inventory.apis.groups.create_n_empty_groups(5)

    response = host_inventory.apis.groups.get_groups_by_id_response(group)

    assert response.total == 1
    assert response.count == 1
    assert len(response.results) == 1
    assert response.results[0].id == group.id
    assert response.results[0].host_count == 3


@pytest.mark.usefixtures("enable_kessel_groups")
def test_get_groups_by_id_rbac_v2_with_mixed_host_counts(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-17397

    metadata:
        requirements: inv-groups-get-by-id, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Get groups with different host counts using RBAC v2
    """
    # Create groups with varying number of hosts (0, 1, 3, 5)
    hosts = host_inventory.kafka.create_random_hosts(9)

    groups_data = [
        GroupData(),  # 0 hosts
        GroupData(hosts=[hosts[0]]),  # 1 host
        GroupData(hosts=hosts[1:4]),  # 3 hosts
        GroupData(hosts=hosts[4:9]),  # 5 hosts
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data)

    response = host_inventory.apis.groups.get_groups_by_id_response(groups)

    assert response.total == 4
    assert response.count == 4
    assert len(response.results) == 4

    # Verify host counts are correct
    expected_host_counts = {0, 1, 3, 5}
    actual_host_counts = {group.host_count for group in response.results}
    assert actual_host_counts == expected_host_counts
