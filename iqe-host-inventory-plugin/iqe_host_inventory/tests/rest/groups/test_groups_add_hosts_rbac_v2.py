"""Tests for POST /groups/{group_id}/hosts with RBAC v2 (Kessel) workspace validation.

JIRA: RHINENG-17399

These tests verify that the POST /groups/{group_id}/hosts endpoint correctly uses
RBAC v2 workspace validation when the 'hbi.api.kessel-groups' feature flag is enabled.

The RBAC v2 path validates that the workspace exists via the Kessel RBAC v2 API
instead of querying the database directly. This is part of the broader Kessel migration.

REVISIT: These tests require Kessel setup in the ephemeral environment.
To run in the EE, use the --kessel option: pytest --kessel
"""

from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
def test_add_hosts_to_group_rbac_v2_success(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Add hosts to group using RBAC v2 workspace validation
    """
    # Create group and verify workspace is created
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    # Wait for workspace to be created in RBAC v2
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Create hosts via upload (Kafka)
    hosts = host_inventory.upload.create_hosts(3)

    # Add hosts to group - should validate workspace via RBAC v2
    updated_group = host_inventory.apis.groups.add_hosts_to_group(group.id, hosts)

    # Verify success
    assert updated_group.id == group.id
    assert updated_group.name == group_name
    assert updated_group.host_count == 3

    # Verify hosts are in the group
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 3
    host_ids = {h.id for h in response_hosts}
    assert all(h.id in host_ids for h in hosts)


@pytest.mark.ephemeral
def test_add_hosts_to_nonexistent_group_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        negative: true
        title: Verify 404 when adding hosts to non-existent group (RBAC v2)
    """
    # Create hosts
    hosts = host_inventory.upload.create_hosts(2)

    # Try to add hosts to non-existent group
    fake_group_id = generate_uuid()

    # Should return 404 because workspace doesn't exist in RBAC v2
    with raises_apierror(404, "not found"):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(
            fake_group_id, [h.id for h in hosts]
        )


@pytest.mark.ephemeral
def test_add_hosts_to_group_rbac_v2_partial_success(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Add multiple hosts to group incrementally using RBAC v2
    """
    # Create group with 1 host
    hosts = host_inventory.upload.create_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])

    # Wait for workspace creation
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Verify initial state
    assert group.host_count == 1

    # Add second host - should validate workspace via RBAC v2
    updated_group = host_inventory.apis.groups.add_hosts_to_group(
        group.id, [hosts[1]], wait_for_added=False
    )
    assert updated_group.host_count == 2

    # Add third host
    updated_group = host_inventory.apis.groups.add_hosts_to_group(
        group.id, [hosts[2]], wait_for_added=False
    )
    assert updated_group.host_count == 3

    # Wait for final state and verify all hosts are in group
    host_inventory.apis.groups.wait_for_hosts_added(group.id, hosts, retries=20, delay=1.0)
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 3


@pytest.mark.ephemeral
def test_add_invalid_hosts_to_group_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        negative: true
        title: Verify 404 when adding non-existent hosts to group (RBAC v2)
    """
    # Create group and wait for workspace
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Try to add non-existent hosts
    fake_host_ids = [generate_uuid(), generate_uuid()]

    # Should return 400 because hosts don't exist
    with raises_apierror(400, "Could not find existing host"):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(
            group.id, fake_host_ids
        )


@pytest.mark.ephemeral
def test_add_hosts_to_group_rbac_v2_idempotent(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Verify adding same host twice is idempotent (RBAC v2)
    """
    # Create group with hosts
    hosts = host_inventory.upload.create_hosts(2)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.workspaces.wait_for_created(group.id)

    assert group.host_count == 1

    # Add second host
    updated_group = host_inventory.apis.groups.add_hosts_to_group(
        group.id, [hosts[1]], wait_for_added=False
    )
    assert updated_group.host_count == 2

    # Add first host again (already in group) - should be idempotent
    updated_group = host_inventory.apis.groups.add_hosts_to_group(
        group.id, [hosts[0]], wait_for_added=False
    )
    assert updated_group.host_count == 2  # Still 2, not 3

    # Wait for final state and verify only 2 hosts in group
    host_inventory.apis.groups.wait_for_hosts_added(group.id, hosts, retries=20, delay=1.0)
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 2


@pytest.mark.ephemeral
def test_add_hosts_to_group_rbac_v2_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2, inv-account-integrity
        assignee: maarif
        importance: critical
        negative: true
        title: Verify cannot add hosts from one account to group in another account (RBAC v2)
    """
    # Create group in primary account
    group_name = generate_display_name()
    group_primary = host_inventory.apis.groups.create_group(group_name)
    host_inventory.apis.workspaces.wait_for_created(group_primary.id)

    # Create hosts in secondary account
    hosts_secondary = host_inventory_secondary.upload.create_hosts(2)

    # Try to add secondary account's hosts to primary account's group
    # Should fail because workspace doesn't exist in secondary account's RBAC
    with raises_apierror(404):
        host_inventory_secondary.apis.groups.raw_api.api_host_group_add_host_list_to_group(
            group_primary.id, [h.id for h in hosts_secondary]
        )


@pytest.mark.ephemeral
def test_add_hosts_to_ungrouped_workspace_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2, inv-ungrouped-workspace
        assignee: maarif
        importance: high
        title: Verify can add hosts to ungrouped workspace using RBAC v2
    """
    # Get ungrouped workspace
    ungrouped_groups = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")
    assert len(ungrouped_groups) == 1
    ungrouped_group = ungrouped_groups[0]

    # Create hosts
    hosts = host_inventory.upload.create_hosts(2)

    # Add hosts to ungrouped workspace - should work with RBAC v2 validation
    updated_group = host_inventory.apis.groups.add_hosts_to_group(ungrouped_group.id, hosts)

    # Verify hosts were added
    assert updated_group.id == ungrouped_group.id
    assert updated_group.host_count >= 2  # May have other hosts

    # Verify hosts are in ungrouped workspace
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(ungrouped_group.id)
    response_host_ids = {h.id for h in response_hosts}
    assert all(h.id in response_host_ids for h in hosts)


@pytest.mark.ephemeral
def test_add_hosts_to_group_rbac_v2_empty_list(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17399

    metadata:
        requirements: inv-groups-add-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: low
        negative: true
        title: Verify 400 error when adding empty host list to group (RBAC v2)
    """
    # Create group
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Try to add empty list of hosts
    with raises_apierror(400):
        host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(group.id, [])
