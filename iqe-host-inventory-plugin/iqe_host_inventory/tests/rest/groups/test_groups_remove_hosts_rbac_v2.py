"""Tests for DELETE /groups/{group_id}/hosts/{host_id_list} with RBAC v2 validation.

JIRA: RHINENG-17400

These tests verify that the DELETE /groups/{group_id}/hosts/{host_id_list} endpoint correctly uses
RBAC v2 workspace validation when the 'hbi.api.kessel-groups' feature flag is enabled.

The RBAC v2 path validates that the workspace exists via the Kessel RBAC v2 API
instead of querying the database directly. This is part of the broader Kessel migration.

NOTE: These tests require Kessel to be enabled (BYPASS_KESSEL=false).
To run in ephemeral environments, use: pytest --kessel
In Stage/Prod, these tests run automatically.
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


def test_remove_hosts_from_group_rbac_v2_success(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        title: Remove hosts from group using RBAC v2 workspace validation
    """
    # Create group with hosts
    hosts = host_inventory.upload.create_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    # Wait for workspace to be created in RBAC v2
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Verify all hosts are in the group
    assert group.host_count == 3

    # Remove 2 hosts from group - should validate workspace via RBAC v2
    host_inventory.apis.groups.remove_hosts_from_group(group.id, [hosts[0], hosts[1]])

    # Verify success - only 1 host remains
    updated_group = host_inventory.apis.groups.get_group_by_id(group.id)
    assert updated_group.host_count == 1

    # Verify correct host remains
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 1
    assert response_hosts[0].id == hosts[2].id


def test_remove_hosts_from_group_rbac_v2_partial(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Remove hosts from group incrementally using RBAC v2
    """
    # Create group with 3 hosts
    hosts = host_inventory.upload.create_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    # Wait for workspace creation
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Verify initial state
    assert group.host_count == 3

    # Remove first host - should validate workspace via RBAC v2
    host_inventory.apis.groups.remove_hosts_from_group(group.id, [hosts[0]])
    updated_group = host_inventory.apis.groups.get_group_by_id(group.id)
    assert updated_group.host_count == 2

    # Remove second host
    host_inventory.apis.groups.remove_hosts_from_group(group.id, [hosts[1]])
    updated_group = host_inventory.apis.groups.get_group_by_id(group.id)
    assert updated_group.host_count == 1

    # Verify only third host remains
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 1
    assert response_hosts[0].id == hosts[2].id


def test_remove_hosts_from_group_rbac_v2_all_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Remove all hosts from group using RBAC v2
    """
    # Create group with hosts
    hosts = host_inventory.upload.create_hosts(2)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    # Wait for workspace creation
    host_inventory.apis.workspaces.wait_for_created(group.id)

    assert group.host_count == 2

    # Remove all hosts from group
    host_inventory.apis.groups.remove_hosts_from_group(group.id, hosts)

    # Verify group is now empty
    updated_group = host_inventory.apis.groups.get_group_by_id(group.id)
    assert updated_group.host_count == 0

    # Verify no hosts in group
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 0


def test_remove_hosts_from_group_rbac_v2_idempotent(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        title: Verify removing already-removed host is idempotent (RBAC v2)
    """
    # Create group with hosts
    hosts = host_inventory.upload.create_hosts(2)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    host_inventory.apis.workspaces.wait_for_created(group.id)

    assert group.host_count == 2

    # Remove first host
    host_inventory.apis.groups.remove_hosts_from_group(group.id, [hosts[0]])
    updated_group = host_inventory.apis.groups.get_group_by_id(group.id)
    assert updated_group.host_count == 1

    # Try to remove first host again (already removed) - should return 404
    # This is expected behavior - removing a host that's not in the group fails
    with raises_apierror(404, "Hosts not found"):
        host_inventory.apis.groups.raw_api.api_host_group_delete_host_list_from_group(
            group.id, [hosts[0].id]
        )

    # Verify still only 1 host in group
    response_hosts = host_inventory.apis.groups.get_hosts_from_group(group.id)
    assert len(response_hosts) == 1
    assert response_hosts[0].id == hosts[1].id


def test_remove_hosts_from_nonexistent_group_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: high
        negative: true
        title: Verify 404 when removing hosts from non-existent group (RBAC v2)
    """
    # Create hosts
    hosts = host_inventory.upload.create_hosts(2)

    # Try to remove hosts from non-existent group
    fake_group_id = generate_uuid()

    # Should return 404 because workspace doesn't exist in RBAC v2
    with raises_apierror(404, "Group .* not found"):
        host_inventory.apis.groups.raw_api.api_host_group_delete_host_list_from_group(
            fake_group_id, [h.id for h in hosts]
        )


def test_remove_invalid_hosts_from_group_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: medium
        negative: true
        title: Verify 404 when removing non-existent hosts from group (RBAC v2)
    """
    # Create group and wait for workspace
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Try to remove non-existent hosts
    fake_host_ids = [generate_uuid(), generate_uuid()]

    # Should return 404 because hosts don't exist
    with raises_apierror(404, "Hosts not found"):
        host_inventory.apis.groups.raw_api.api_host_group_delete_host_list_from_group(
            group.id, fake_host_ids
        )


def test_remove_hosts_from_ungrouped_workspace_rbac_v2(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2, inv-ungrouped-workspace
        assignee: maarif
        importance: high
        negative: true
        title: Verify 400 error when removing hosts from ungrouped workspace (RBAC v2)
    """
    # Get ungrouped workspace
    ungrouped_groups = host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts")
    assert len(ungrouped_groups) == 1
    ungrouped_group = ungrouped_groups[0]

    # Create hosts
    hosts = host_inventory.upload.create_hosts(2)

    # Try to remove hosts from ungrouped workspace - should fail with 400
    with raises_apierror(400, "Cannot remove hosts from ungrouped workspace"):
        host_inventory.apis.groups.raw_api.api_host_group_delete_host_list_from_group(
            ungrouped_group.id, [h.id for h in hosts]
        )


def test_remove_hosts_from_group_rbac_v2_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2, inv-account-integrity
        assignee: maarif
        importance: critical
        negative: true
        title: Verify cannot remove hosts from group in different account (RBAC v2)
    """
    # Create group with hosts in primary account
    hosts_primary = host_inventory.upload.create_hosts(2)
    group_name = generate_display_name()
    group_primary = host_inventory.apis.groups.create_group(group_name, hosts=hosts_primary)
    host_inventory.apis.workspaces.wait_for_created(group_primary.id)

    # Try to remove primary account's hosts using secondary account
    # Should fail because workspace doesn't exist in secondary account's RBAC
    with raises_apierror(404, "Group .* not found"):
        host_inventory_secondary.apis.groups.raw_api.api_host_group_delete_host_list_from_group(
            group_primary.id, [h.id for h in hosts_primary]
        )


def test_remove_hosts_from_group_rbac_v2_empty_list(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-17400

    metadata:
        requirements: inv-groups-remove-hosts, inv-kessel-rbac-v2
        assignee: maarif
        importance: low
        negative: true
        title: Verify 400 error when removing empty host list from group (RBAC v2)
    """
    # Create group
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)
    host_inventory.apis.workspaces.wait_for_created(group.id)

    # Try to remove empty list of hosts
    with raises_apierror(400):
        host_inventory.apis.groups.raw_api.api_host_group_delete_host_list_from_group(group.id, [])
