# mypy: disallow-untyped-defs

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.outage, pytest.mark.cert_auth]


def test_outage_get_host_list(
    host_inventory: ApplicationHostInventory, hbi_default_org_id: str
) -> None:
    """
    Test that we can access Inventory and get a list of hosts

    metadata:
        requirements: inv-hosts-get-list
        assignee: fstavela
        importance: critical
        title: Access Inventory and get a list of hosts
    """
    response = host_inventory.apis.hosts.get_hosts_response()

    assert hasattr(response, "total")
    logger.info(f"There are {response.total} hosts in account {hbi_default_org_id}")

    assert hasattr(response, "count")
    assert response.count == len(response.results)


def test_outage_get_host_by_id(
    host_inventory: ApplicationHostInventory, hbi_cert_auth_upload_prepare_host_module: HostOut
) -> None:
    """
    Test getting host by ID

    metadata:
        requirements: inv-hosts-get-by-id
        assignee: fstavela
        importance: critical
        title: Get host by ID
    """
    host = hbi_cert_auth_upload_prepare_host_module

    response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)

    assert response.count == 1
    assert response.results[0].id == host.id
    logger.info(f"Host's org ID: {response.results[0].org_id}")


def test_outage_get_host_by_hostname_or_id(
    host_inventory: ApplicationHostInventory, hbi_cert_auth_upload_prepare_host_module: HostOut
) -> None:
    """
    Test getting host by hostname_or_id parameter. This parameter is used by UI when filtering
    hosts by name.

    metadata:
        requirements: inv-hosts-filter-by-hostname_or_id
        assignee: fstavela
        importance: critical
        title: Get host by hostname_or_id
    """
    host = hbi_cert_auth_upload_prepare_host_module

    response = host_inventory.apis.hosts.get_hosts(hostname_or_id=host.display_name)
    assert len(response) == 1

    response_host = response[0]
    assert response_host.display_name == host.display_name
    assert response_host.id == host.id


@pytest.mark.parametrize("with_host", [False, True], ids=["empty group", "with host"])
def test_outage_groups(
    host_inventory: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
    with_host: bool,
) -> None:
    """
    This test checks creating a group, checking that it has correct attributes and deleting it
    at the teardown. This workflow tests 3 endpoints:
    - POST /groups
    - GET /groups/<group_id>
    - DELETE /groups/<group_id>

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: critical
      title: Create a group
    """
    host = hbi_cert_auth_upload_prepare_host_module
    expected_hosts = [host] if with_host else []

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(
        group_name, hosts=expected_hosts, wait_for_created=False
    )

    assert group.id
    assert group.name == group_name
    assert group.host_count == len(expected_hosts)
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=expected_hosts)


def test_outage_cert_auth(
    host_inventory: ApplicationHostInventory,
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cert_auth_upload_prepare_host_module: HostOut,
    hbi_default_org_id: str,
) -> None:
    """
    Test that I can create host through ingress/puptoo archive upload using cert auth
    and the owner_id field is not empty. Then test that I can access this host with both cert auth
    and basic auth.

    https://issues.redhat.com/browse/RHCLOUD-12124

    metadata:
        requirements: inv-api-cert-auth, inv-host-create
        assignee: fstavela
        importance: critical
        title: Test that creating host via archive upload using cert auth creates owner_id
    """
    host = hbi_cert_auth_upload_prepare_host_module

    # Check that we can access the host using cert auth
    # Get host list
    response = host_inventory_cert_auth.apis.hosts.get_hosts_response()
    assert response.count >= 1
    assert host.id in {res_host.id for res_host in response.results}
    assert all(res_host.org_id == hbi_default_org_id for res_host in response.results)

    # Get host list with insights_id parameter (insights-client does this)
    response = host_inventory_cert_auth.apis.hosts.get_hosts_response(insights_id=host.insights_id)
    assert response.count == 1
    assert response.results[0].id == host.id

    # Get host by ID
    response = host_inventory_cert_auth.apis.hosts.get_hosts_by_id_response(host.id)
    assert response.count == 1
    assert response.results[0].id == host.id

    # Get system profile
    response = host_inventory_cert_auth.apis.hosts.get_hosts_system_profile_response(host.id)
    assert response.count == 1
    assert response.results[0].system_profile.owner_id

    # Check that we can access the host using basic auth
    # Get host by ID
    response = host_inventory.apis.hosts.get_hosts_by_id_response(host.id)
    assert response.count == 1
    assert response.results[0].id == host.id

    # Get system profile
    response = host_inventory.apis.hosts.get_hosts_system_profile_response(host.id)
    assert response.count == 1
    assert response.results[0].system_profile.owner_id
