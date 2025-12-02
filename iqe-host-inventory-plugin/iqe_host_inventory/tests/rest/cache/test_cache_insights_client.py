"""
metadata:
  requirements: inv-cache-invalidation-insights-client, inv-hosts-get-list
"""

import os
from time import sleep

import pytest
from iqe.utils.blockers import iqe_blocker

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import HostOut

pytestmark = [pytest.mark.backend, pytest.mark.cert_auth]


@pytest.mark.usefixtures("hbi_cert_auth_upload_prepare_host_module")
def test_cache_invalidation_insights_client_get_hosts_list_create_host(
    host_inventory_cert_auth: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-host-create
      assignee: fstavela
      importance: high
      title: Invalidate cache on insights-client API calls when a host is created
    """
    # Init the cache
    insights_id = generate_uuid()
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=insights_id)
    assert len(response) == 0

    # Create a new host to invalidate the cache
    new_host = host_inventory_cert_auth.upload.create_host(insights_id=insights_id)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=insights_id)
    assert len(response) == 1
    assert response[0].id == new_host.id


def test_cache_invalidation_insights_client_get_hosts_list_update_host(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-host-update
      assignee: fstavela
      importance: high
      title: Invalidate cache on insights-client API calls when a host is updated
    """
    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)

    # Update the host to invalidate the cache
    new_display_name = generate_display_name()
    host_inventory_cert_auth.upload.create_host(
        insights_id=host.insights_id, display_name=new_display_name, cleanup_scope="module"
    )
    host_inventory_cert_auth.apis.hosts.wait_for_updated(host, display_name=new_display_name)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert response[0].display_name == new_display_name


def test_cache_invalidation_insights_client_get_hosts_list_patch_host(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-hosts-patch
      assignee: fstavela
      importance: high
      title: Invalidate cache on insights-client API calls when a host is patched
    """
    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)

    # Patch the host to invalidate the cache
    new_display_name = generate_display_name()
    host_inventory.apis.hosts.patch_hosts(host, display_name=new_display_name)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert response[0].display_name == new_display_name


@pytest.mark.usefixtures("hbi_cert_auth_upload_prepare_host_module")
def test_cache_invalidation_insights_client_get_hosts_list_delete_host_by_id(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-hosts-delete-by-id
      assignee: fstavela
      importance: high
      title: Invalidate cache on insights-client API calls when a host is deleted by ID
    """
    # Prepare the second host
    host_to_delete = host_inventory_cert_auth.upload.create_host(insights_id=generate_uuid())

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(
        insights_id=host_to_delete.insights_id
    )
    assert len(response) == 1
    assert response[0].id == host_to_delete.id

    # Delete the second host to invalidate the cache
    host_inventory.apis.hosts.delete_by_id(host_to_delete)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(
        insights_id=host_to_delete.insights_id
    )
    assert len(response) == 0


@pytest.mark.usefixtures("hbi_cert_auth_upload_prepare_host_module")
def test_cache_invalidation_insights_client_get_hosts_list_delete_filtered(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Invalidate cache on insights-client API calls when a host is deleted by filter
    """
    # Prepare the second host
    host_to_delete = host_inventory_cert_auth.upload.create_host(insights_id=generate_uuid())

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(
        insights_id=host_to_delete.insights_id
    )
    assert len(response) == 1
    assert response[0].id == host_to_delete.id

    # Delete the second host to invalidate the cache
    host_inventory.apis.hosts.delete_filtered(insights_id=host_to_delete.insights_id)
    host_inventory.apis.hosts.wait_for_deleted(host_to_delete)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(
        insights_id=host_to_delete.insights_id
    )
    assert len(response) == 0


def test_cache_invalidation_insights_client_get_hosts_list_create_group(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client API calls when a group is created
    """
    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert is_ungrouped_host(response[0])

    # Create a new group to invalidate the cache
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id


def test_cache_invalidation_insights_client_get_hosts_list_patch_group(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client API calls when a group is patched
    """
    # Create a group
    host = hbi_cert_auth_upload_prepare_host_module
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id
    assert response[0].groups[0].name == group.name

    # Patch the group's name
    new_name = generate_display_name()
    host_inventory.apis.groups.patch_group(group=group, name=new_name)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id
    assert response[0].groups[0].name == new_name


def test_cache_invalidation_insights_client_get_hosts_list_add_to_group(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-add-hosts
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client API calls when a host is added to a group
    """
    # Create a group
    host = hbi_cert_auth_upload_prepare_host_module
    group = host_inventory.apis.groups.create_group(generate_display_name())

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert is_ungrouped_host(response[0])

    # Add the host to the group to invalidate the cache
    host_inventory.apis.groups.add_hosts_to_group(group=group, hosts=host)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id


def test_cache_invalidation_insights_client_get_hosts_list_remove_from_group(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-remove-hosts
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client API calls when a host is removed from a group
    """
    # Create a group
    host = hbi_cert_auth_upload_prepare_host_module
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id

    # Remove the host from the group to invalidate the cache
    host_inventory.apis.groups.remove_hosts_from_group(group=group, hosts=host)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert is_ungrouped_host(response[0])


def test_cache_invalidation_insights_client_get_hosts_list_remove_from_multiple_groups(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client calls when hosts are removed from multiple groups
    """
    # Create a group
    host = hbi_cert_auth_upload_prepare_host_module
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id

    # Remove the host from the group using DELETE /groups/hosts/<hosts_ids> to invalidate the cache
    host_inventory.apis.groups.remove_hosts_from_multiple_groups(host)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert is_ungrouped_host(response[0])


def test_cache_invalidation_insights_client_get_hosts_list_delete_group(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-groups-delete
      assignee: fstavela
      importance: medium
      title: Invalidate cache on insights-client API calls when a group is deleted
    """
    # Create a group
    host = hbi_cert_auth_upload_prepare_host_module
    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=host)

    # Init the cache
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert len(response[0].groups) == 1
    assert response[0].groups[0].id == group.id

    # Delete the group to invalidate the cache
    host_inventory.apis.groups.delete_groups(group)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert is_ungrouped_host(response[0])


def wait_for_staleness_cache_invalidation(delay: int = 1) -> None:
    # For staleness operations, requests return right away and a thread is
    # spawned to invalidate the cache, so we need a short delay.
    #
    # https://redhat-internal.slack.com/archives/CQFKM031T/p1724768361126559
    sleep(delay)


@iqe_blocker(iqe_blocker.jira("RHINENG-18758", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.skipif(
    os.getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "prod",
    reason="The cache invalidation takes a long time (possibly over 10 minutes) in Prod",
)
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_cache_invalidation_insights_client_get_hosts_list_create_staleness(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-staleness-post
      assignee: fstavela
      importance: low
      title: Invalidate cache on insights-client API calls when a staleness config is created
    """
    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    initial_timestamp = response[0].stale_timestamp

    # Create staleness config to invalidate the cache
    host_inventory.apis.account_staleness.create_staleness(conventional_time_to_stale=100)

    wait_for_staleness_cache_invalidation()

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert response[0].stale_timestamp != initial_timestamp


@iqe_blocker(iqe_blocker.jira("RHINENG-18758", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.skipif(
    os.getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "prod",
    reason="The cache invalidation takes a long time (possibly over 10 minutes) in Prod",
)
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_cache_invalidation_insights_client_get_hosts_list_update_staleness(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-staleness-patch
      assignee: fstavela
      importance: low
      title: Invalidate cache on insights-client API calls when a staleness config is updated
    """
    # Create staleness config
    host_inventory.apis.account_staleness.create_staleness(conventional_time_to_stale=500)

    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    initial_timestamp = response[0].stale_timestamp

    # Update staleness config to invalidate the cache
    host_inventory.apis.account_staleness.update_staleness(conventional_time_to_stale=100)

    wait_for_staleness_cache_invalidation()

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert response[0].stale_timestamp != initial_timestamp


@iqe_blocker(iqe_blocker.jira("RHINENG-18758", category=iqe_blocker.PRODUCT_ISSUE))
@pytest.mark.skipif(
    os.getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "prod",
    reason="The cache invalidation takes a long time (possibly over 10 minutes) in Prod",
)
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_cache_invalidation_insights_client_get_hosts_list_delete_staleness(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-staleness-delete
      assignee: fstavela
      importance: low
      title: Invalidate cache on insights-client API calls when a staleness config is deleted
    """
    # Create staleness config
    host_inventory.apis.account_staleness.create_staleness(conventional_time_to_stale=100)

    # Init the cache
    host = hbi_cert_auth_upload_prepare_host_module
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    initial_timestamp = response[0].stale_timestamp

    # Delete staleness config to invalidate the cache
    host_inventory.apis.account_staleness.delete_staleness()

    wait_for_staleness_cache_invalidation()

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_hosts(insights_id=host.insights_id)
    assert len(response) == 1
    assert response[0].id == host.id
    assert response[0].stale_timestamp != initial_timestamp


@pytest.mark.usefixtures("hbi_cert_auth_upload_prepare_host_module")
def test_cache_invalidation_insights_client_get_host_exists(
    host_inventory_cert_auth: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/RHINENG-11687

    metadata:
      requirements: inv-host_exists-get-by-insights-id
      assignee: msager
      importance: medium
      title: Invalidate cache on insights-client API calls when checking a host's existence
    """
    # Init the cache
    insights_id = generate_uuid()
    with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
        host_inventory_cert_auth.apis.hosts.get_host_exists(insights_id)

    # Create a new host to invalidate the cache
    new_host = host_inventory_cert_auth.upload.create_host(insights_id=insights_id)

    # Check that the cache has been invalidated
    response = host_inventory_cert_auth.apis.hosts.get_host_exists(insights_id)
    assert response.id == new_host.id

    # Delete the host to invalidate the cache
    host_inventory.apis.hosts.delete_by_id(new_host)

    # Check that the cache has been invalidated
    with raises_apierror(404, match_message=f"No host found for Insights ID '{insights_id}'"):
        host_inventory_cert_auth.apis.hosts.get_host_exists(insights_id)
