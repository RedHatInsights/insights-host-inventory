# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import multiprocessing
import time
from collections.abc import Generator
from copy import deepcopy
from datetime import UTC
from datetime import datetime

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api.models.host_out import HostOut

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def hosts_for_negative_tests(host_inventory: ApplicationHostInventory) -> list[HostOut]:
    """Create hosts for negative tests, these shouldn't get deleted"""
    return host_inventory.upload.create_hosts(3, cleanup_scope="module")


@pytest.mark.parametrize("invalid_host_id", ["host", "78", "1.223434"])
def test_delete_multiple_hosts_with_invalid_id(
    host_inventory: ApplicationHostInventory,
    hosts_for_negative_tests: list[HostOut],
    invalid_host_id: str,
):
    """
    Test Deletion of Multiple Hosts with an Invalid Id in the Request.

    1. Create three hosts
    2. Issue a delete with an invalid host id intermixed with the others.
    3. Confirm response status code was 400.
    4. Confirm no hosts were deleted.

    metadata:
        requirements: inv-api-validation
        assignee: btweed
        importance: low
        title: Inventory: Confirm deletion of multiple hosts with an invalid id does not
            delete anything.
    """
    # Put one invalid host_id in the mix
    bad_host_list = [host.id for host in hosts_for_negative_tests]
    bad_host_list[1] = invalid_host_id

    # Issue DELETE and expect a 400
    with raises_apierror(400, match_message="Failed validating"):
        host_inventory.apis.hosts.delete_by_id_raw(bad_host_list)

    host_inventory.apis.hosts.verify_not_deleted(hosts_for_negative_tests)


def test_delete_existing_and_non_existent_hosts(
    host_inventory: ApplicationHostInventory,
    hosts_for_negative_tests: list[HostOut],
):
    """
    metadata:
        requirements: inv-hosts-delete-by-id
        assignee: fstavela
        importance: medium
        title: Try deleting existing and non-existent hosts in the same request.
    """
    # Put one non-existent host_id in the mix
    bad_host_list = [host.id for host in hosts_for_negative_tests]
    bad_host_list[1] = generate_uuid()

    # Issue DELETE and expect a 404
    with raises_apierror(404):
        host_inventory.apis.hosts.delete_by_id_raw(bad_host_list)
    host_inventory.apis.hosts.verify_not_deleted(hosts_for_negative_tests)


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
        requirements: inv-hosts-delete-by-id
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
        requirements: inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: Confirm deletion of a non-existent host.
    """
    unused_uuid = generate_uuid()

    with raises_apierror(404):
        host_inventory.apis.hosts.delete_by_id_raw(unused_uuid)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
def test_delete_culled_host(host_inventory: ApplicationHostInventory):
    """
    Confirm that is not possible to delete culled hosts.

    1. Create a host in culled state
    2. Attempt to remove the host
    3. Make sure that an error 404 is returned

    metadata:
        requirements: inv-staleness-hosts
        assignee: fstavela
        importance: low
        title: Inventory: Confirm that is not possible to delete a culled host
    """
    host_data = host_inventory.datagen.create_host_data()
    host = create_hosts_in_state(host_inventory, [host_data], host_state="culling")[0]

    with raises_apierror(404):
        host_inventory.apis.hosts.delete_by_id_raw(host)


@pytest.mark.concurrency
@pytest.mark.parametrize("num_concurrent_requests", [5, 10])
def test_concurrency_delete(
    application: Application,
    host_inventory: ApplicationHostInventory,
    num_concurrent_requests: int,
):
    """
    Test Concurrent DELETE Requests of Same Host.

    1. Create a host
    2. Issue multiple concurrent DELETE requests for the host's id
    3. Confirm the host was successfully deleted

    metadata:
        requirements: inv-hosts-delete-by-id
        assignee: fstavela
        importance: high
        title: Inventory: Confirm concurrent deletion of same host.
    """
    if application.config.current_env.lower() == "prod":
        # TODO: add prod env blocker
        pytest.skip("Let us not do stressful/dangerous things against production")

    host = host_inventory.upload.create_host()

    start_time = time.time()

    # Now issue multiple concurrent requests to delete the same host
    host_inventory.apis.hosts.api_client.pool_threads = multiprocessing.cpu_count()
    threads = []
    for _ in range(num_concurrent_requests):
        thread = host_inventory.apis.hosts.raw_api.api_host_delete_host_by_id(
            host_id_list=[host.id], async_req=True
        )
        threads.append(thread)

    for thread in threads:
        try:
            thread.get()
        except ApiException as exc:
            assert exc.status in (404, 500)

    host_inventory.apis.hosts.api_client.pool_threads = 1

    # All concurrent deletions complete, try to GET the host
    # wait for deletion to pass trough the api
    host_inventory.apis.hosts.wait_for_deleted(host)

    end_time = time.time()
    total_time = end_time - start_time
    logger.info("Total time for test execution was %f", total_time)


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
        requirements: inv-hosts-delete-by-id
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
        requirements: inv-hosts-delete-filtered-hosts, inv-rhsm-org_id-header
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
        requirements: inv-hosts-delete-filtered-hosts
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
        requirements: inv-hosts-delete-filtered-hosts
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


@pytest.mark.ephemeral
def test_delete_bulk_last_check_in(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with combined last_check_in_start and last_check_in_end.

    metadata:
        requirements: inv-hosts-filter-by-last_check_in, inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Delete hosts by combined last_check_in_start and last_check_in_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now(tz=UTC)
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now(tz=UTC)
    host_after = host_inventory.kafka.create_host()

    host_inventory.apis.hosts.delete_filtered(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    host_inventory.apis.hosts.wait_for_deleted(hosts)
    host_inventory.apis.hosts.verify_not_deleted([host_before, host_after])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_group_name(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with 'group_name' parameter.

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_name
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
def test_delete_bulk_system_type(
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_deleting_by_system_type_filter: dict[str, list[HostWrapper]],
):
    """
    Test DELETE on /hosts endpoint with 'system_type' parameter.

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Confirm system_type parameter deletes right hosts
    """
    prepared_hosts = deepcopy(setup_hosts_for_deleting_by_system_type_filter)
    expected_hosts = prepared_hosts.pop("edge")

    host_inventory.apis.hosts.delete_filtered(system_type=["edge"])
    host_inventory.apis.hosts.wait_for_deleted(expected_hosts)

    not_deleted = flatten(hosts for hosts in prepared_hosts.values())
    host_inventory.apis.hosts.verify_not_deleted(not_deleted)


@pytest.mark.ephemeral
def test_delete_bulk_tags(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with 'tags' parameter.

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'tags' parameter
    """
    searched_tag = gen_tag()
    str_tag = convert_tag_to_string(searched_tag)
    hosts_data = host_inventory.datagen.create_n_hosts_data(4)
    hosts_data[0]["tags"] = [searched_tag]
    hosts_data[1]["tags"] = [searched_tag, gen_tag()]
    hosts_data[2]["tags"] = [gen_tag()]
    hosts_data[3].pop("tags", None)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    host_inventory.apis.hosts.delete_filtered(tags=[str_tag])
    host_inventory.apis.hosts.wait_for_deleted(hosts[:2])
    host_inventory.apis.hosts.verify_not_deleted(hosts[2:])


@pytest.mark.ephemeral
def test_delete_bulk_workloads_sap(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts endpoint with system_profile workloads SAP filter.

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with workloads SAP filter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(4)
    hosts_data[0]["system_profile"]["workloads"] = {"sap": {"sap_system": True, "sids": ["H2O"]}}
    hosts_data[1]["system_profile"]["workloads"] = {"sap": {"sap_system": True}}
    hosts_data[2]["system_profile"]["workloads"] = {"ansible": {"controller_version": "4.3"}}
    hosts_data[3]["system_profile"].pop("workloads", None)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    host_inventory.apis.hosts.delete_filtered(filter=["[workloads][sap][sap_system][is]=not_nil"])
    host_inventory.apis.hosts.wait_for_deleted(hosts[:2])
    host_inventory.apis.hosts.verify_not_deleted(hosts[2:])


@pytest.mark.ephemeral
def test_delete_bulk_all_hosts(host_inventory: ApplicationHostInventory):
    """
    Test DELETE on /hosts/all endpoint with correct parameters.

    metadata:
        requirements: inv-hosts-delete-all
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
        requirements: inv-hosts-delete-filtered-hosts, inv-account-integrity
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
