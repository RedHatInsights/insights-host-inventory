# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api.models.host_out import HostOut

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def hosts_for_negative_tests(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    """Create hosts for negative tests, these shouldn't get deleted"""
    return host_inventory.upload.create_hosts(3, cleanup_scope="module")


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_delete_multiple_hosts(host_inventory: ApplicationHostInventory):
    """
    Test Deletion of Multiple Hosts.

    1. Create three hosts
    2. Issue a request to delete all three hosts
    3. Confirm response status code was OK
    4. Confirm all three hosts were deleted

    metadata:
        assignee: fstavela
        importance: critical
        title: Inventory: Confirm deletion of multiple hosts works.
    """
    # Create 3 new hosts
    hosts = host_inventory.upload.create_hosts(3)
    host_inventory.apis.hosts.delete_by_id_raw(hosts)
    host_inventory.apis.hosts.wait_for_deleted(hosts)


def test_delete_non_existent_host(
    host_inventory: ApplicationHostInventory,
):
    """
    Test Deletion of Non-existent Host.

    1. Issue a DELETE request against a non-existent host ID
    2. Confirm the response is 404

    metadata:
        assignee: fstavela
        importance: low
        title: Inventory: Confirm deletion of a non-existent host.
    """
    unused_uuid = generate_uuid()

    with raises_apierror(404):
        host_inventory.apis.hosts.delete_by_id_raw(unused_uuid)


@pytest.mark.smoke
@pytest.mark.core
@pytest.mark.qa
def test_host_deletion_happy_path(host_inventory: ApplicationHostInventory):
    """
    Test Host Deletion Happy Path.

    1. Create a host
    2. Issue request to delete the host
    3. Confirm DELETE request was successful via a GET

    metadata:
        assignee: fstavela
        importance: critical
        title: Inventory: Confirm host deletion happy path
    """
    host = host_inventory.upload.create_host()

    host_inventory.apis.hosts.delete_by_id_raw(host)
    host_inventory.apis.hosts.wait_for_deleted(host)
    with raises_apierror(404):
        host_inventory.apis.hosts.delete_by_id_raw(host)


@pytest.fixture()
def host_inventory_x509_rhsm(
    application: Application, hbi_identity_auth_x509_rhsm: DynaBox
) -> Generator[ApplicationHostInventory]:
    with application.copy_using(
        auth_type=AuthType.IDENTITY, user=hbi_identity_auth_x509_rhsm, verify_ssl=False
    ) as app:
        yield app.host_inventory


@pytest.mark.ephemeral
def test_delete_hosts_by_subman_id_internal_rhsm_request(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    host_inventory_x509_rhsm: ApplicationHostInventory,
    hbi_default_org_id: str,
):
    """
    This test simulates the internal `DELETE /hosts?subscription_manager_id=...` request from RHSM
    that they make when a host is unregistered from RHSM, to delete it from Insights Inventory.

    https://issues.redhat.com/browse/RHINENG-18446

    metadata:
        assignee: fstavela
        importance: high
        title: Test DELETE on /hosts with 'group_name' parameter doesn't affect different accounts
    """
    searched_subman_id = generate_uuid()
    matching_host_data = host_inventory.datagen.create_host_data(
        subscription_manager_id=searched_subman_id
    )
    not_matching_host_data = host_inventory.datagen.create_host_data(
        subscription_manager_id=generate_uuid()
    )
    secondary_host_data = host_inventory_secondary.datagen.create_host_data(
        subscription_manager_id=searched_subman_id
    )
    primary_org_hosts = host_inventory.kafka.create_hosts([
        matching_host_data,
        not_matching_host_data,
    ])
    secondary_org_host = host_inventory_secondary.kafka.create_host(secondary_host_data)

    with temp_headers(
        host_inventory_x509_rhsm.apis.hosts.raw_api, {"x-inventory-org-id": hbi_default_org_id}
    ):
        host_inventory_x509_rhsm.apis.hosts.raw_api.api_host_delete_hosts_by_filter(
            subscription_manager_id=searched_subman_id
        )

    response_hosts = host_inventory.apis.hosts.get_hosts_by_id(primary_org_hosts[1])
    assert len(response_hosts) == 1
    assert response_hosts[0].id == primary_org_hosts[1].id

    # Make sure the host from different org wasn't deleted
    response_hosts = host_inventory_secondary.apis.hosts.get_hosts_by_id([secondary_org_host.id])
    assert len(response_hosts) == 1
    assert response_hosts[0].id == secondary_org_host.id


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_hostname_or_id(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with 'hostname_or_id' parameter.

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'hostname_or_id' parameter
    """
    searched_value = generate_display_name()
    hosts_data = host_inventory.datagen.create_n_hosts_data(4)
    hosts_data[0]["display_name"] = searched_value
    hosts_data[1]["fqdn"] = searched_value
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    host_inventory.apis.hosts.delete_filtered(hostname_or_id=searched_value)
    host_inventory.apis.hosts.wait_for_deleted(hosts[:2])
    host_inventory.apis.hosts.verify_not_deleted(hosts[2:])


@pytest.mark.ephemeral
def test_delete_bulk_registered_with(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with 'registered_with' parameter.

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'registered_with' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    hosts_data[0]["reporter"] = "puptoo"
    hosts_data[1]["reporter"] = "puptoo"
    hosts_data[2]["reporter"] = "satellite"
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    host_inventory.apis.hosts.delete_filtered(registered_with=["puptoo"])
    host_inventory.apis.hosts.wait_for_deleted(hosts[:2])
    host_inventory.apis.hosts.verify_not_deleted(hosts[2])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_group_name(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with 'group_name' parameter.

    metadata:
        assignee: fstavela
        importance: high
        title: Delete hosts by group_name
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    host_inventory.apis.hosts.delete_filtered(group_name=[group_name])
    host_inventory.apis.hosts.wait_for_deleted(hosts[0])
    host_inventory.apis.hosts.verify_not_deleted(hosts[1:])


@pytest.mark.ephemeral
def test_delete_bulk_all_hosts(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts/all endpoint with correct parameters.

    metadata:
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts/all with correct parameters
    """
    host_inventory.kafka.create_random_hosts(5)

    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.hosts.verify_all_deleted()


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    Test that bulk delete on one account doesn't affect hosts in another account.

    metadata:
        assignee: fstavela
        importance: critical
        title: Inventory: Test DELETE on /hosts doesn't affect different accounts
    """
    searched_value = generate_display_name()
    host_data_primary = host_inventory.datagen.create_host_data()
    host_data_primary["display_name"] = searched_value
    host_primary = host_inventory.kafka.create_host(host_data=host_data_primary)

    host_data_secondary = host_inventory_secondary.datagen.create_host_data()
    host_data_secondary["display_name"] = searched_value
    host_secondary = host_inventory_secondary.kafka.create_host(host_data=host_data_secondary)

    with host_inventory_secondary.apis.hosts.verify_host_count_not_changed():
        host_inventory.apis.hosts.delete_filtered(display_name=searched_value)
        host_inventory.apis.hosts.wait_for_deleted(host_primary)

    host_inventory_secondary.apis.hosts.verify_not_deleted(host_secondary)
