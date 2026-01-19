from __future__ import annotations

import logging
import multiprocessing
import time
from collections.abc import Generator
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from itertools import combinations
from typing import Any

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.test_culling import gen_fresh_date
from iqe_host_inventory.tests.rest.test_culling import gen_stale_date
from iqe_host_inventory.tests.rest.test_culling import gen_stale_warning_date
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_DATETIMES
from iqe_host_inventory.utils import determine_positive_hosts_by_registered_with
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils import get_account_number
from iqe_host_inventory.utils import get_org_id
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import _CORRECT_REGISTERED_WITH_VALUES
from iqe_host_inventory.utils.datagen_utils import _CORRECT_SYSTEM_TYPE_VALUES
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_provider_type
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api.models.host_out import HostOut

pytestmark = [
    pytest.mark.backend,
    pytest.mark.usefixtures("hbi_recreate_data_on_secondary_account_after_delete"),
]

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


@pytest.fixture
def check_delete_filtered_different_account(  # NOQA: C901
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_recreate_data_on_secondary_account_after_delete: None,
    hbi_staleness_secondary_cleanup,
):
    def _check(**kwargs):  # NOQA: C901
        # Clean the account
        host_inventory_secondary.apis.hosts.confirm_delete_all()

        host_data = host_inventory_secondary.datagen.create_host_data()
        if kwargs:
            if "hostname_or_id" in kwargs:
                host_data["fqdn"] = kwargs["hostname_or_id"]
                host_data["display_name"] = kwargs["hostname_or_id"]
            if "provider_type" in kwargs or "provider_id" in kwargs:
                host_data["provider_id"] = kwargs.get("provider_id") or generate_uuid()
                host_data["provider_type"] = kwargs.get("provider_type") or "aws"
            if "registered_with" in kwargs:
                if "insights" in kwargs["registered_with"]:
                    host_data["insights_id"] = kwargs.get("insights_id") or generate_uuid()
                else:
                    host_data["reporter"] = kwargs["registered_with"][0]
            if "staleness" in kwargs:
                if "fresh" in kwargs["staleness"]:
                    staleness = "fresh"
                elif "stale" in kwargs["staleness"]:
                    staleness = "stale"
                elif "stale_warning" in kwargs["staleness"]:
                    staleness = "stale_warning"
            host_data = {**host_data, **kwargs}
            host_data.pop("hostname_or_id", None)
            host_data.pop("registered_with", None)
            host_data.pop("staleness", None)
            if "tags" in kwargs:
                host_data["tags"] = list(kwargs["tags"])
                for i in range(len(kwargs["tags"])):
                    kwargs["tags"][i] = convert_tag_to_string(kwargs["tags"][i])

        if "staleness" in kwargs and staleness != "fresh":
            host = create_hosts_in_state(host_inventory_secondary, [host_data], staleness)[0]
        else:
            host = host_inventory_secondary.kafka.create_host(host_data=host_data)

        # Check with existing matching host in secondary account
        with host_inventory.apis.hosts.verify_host_count_not_changed():
            try:
                host_inventory_secondary.apis.hosts.delete_filtered(**kwargs)
            except ApiException as exc:
                # In case we are trying to use the endpoint without providing parameters
                assert exc.status == 400
                host_inventory_secondary.apis.hosts.delete_by_id_raw(host)
            host_inventory_secondary.apis.hosts.wait_for_deleted(host)

        # Check without existing matching host in secondary account
        with host_inventory.apis.hosts.verify_host_count_not_changed():
            try:
                host_inventory_secondary.apis.hosts.delete_filtered(**kwargs)
            except ApiException as exc:
                # In case we are trying to use the endpoint without providing parameters
                assert exc.status == 400

    yield _check


@pytest.fixture
def check_delete_all_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_recreate_data_on_secondary_account_after_delete: None,
):
    def _check(confirm_delete_all: Any | None = None, **kwargs):
        # Clean the account
        host_inventory_secondary.apis.hosts.confirm_delete_all()

        host_data = host_inventory_secondary.datagen.create_host_data()
        host = host_inventory_secondary.kafka.create_host(host_data=host_data)

        # Check with existing matching host in secondary account
        with host_inventory.apis.hosts.verify_host_count_not_changed():
            try:
                host_inventory_secondary.apis.hosts.delete_all(
                    confirm_delete_all=confirm_delete_all, **kwargs
                )
            except ApiException as exc:
                # In case we are trying to use the endpoint without providing correct parameters
                assert exc.status == 400
                host_inventory_secondary.apis.hosts.delete_by_id_raw(host.id)
            host_inventory_secondary.apis.hosts.wait_for_deleted(host)

        # Check without existing matching host in secondary account
        with host_inventory.apis.hosts.verify_host_count_not_changed():
            try:
                host_inventory_secondary.apis.hosts.delete_all(
                    confirm_delete_all=confirm_delete_all, **kwargs
                )
            except ApiException as exc:
                # In case we are trying to use the endpoint without providing correct parameters
                assert exc.status == 400

    yield _check


@pytest.mark.ephemeral
def test_delete_bulk_without_parameters(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint without setting any parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-api-validation
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts without parameters
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    check_delete_filtered_different_account()

    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with raises_apierror(
            400, "bulk-delete operation needs at least one input property to filter on."
        ):
            host_inventory.apis.hosts.delete_filtered()
        host_inventory.apis.hosts.verify_not_deleted(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("confirm_delete_all", [None, False, "random-string", 0, 1])
def test_delete_bulk_all_hosts_wrong_parameters(
    check_delete_all_different_account,
    host_inventory: ApplicationHostInventory,
    confirm_delete_all: bool | str | int | None,
):
    """
    Test DELETE on /hosts/all endpoint without setting correct parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-all, inv-api-validation
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts/all without correct parameters
    """
    host_inventory.kafka.create_random_hosts(5)

    params = {}
    if confirm_delete_all is not None:
        params["confirm_delete_all"] = confirm_delete_all

    check_delete_all_different_account(**params)

    # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
    # error_message = "Wrong type, expected 'boolean' for query parameter"
    error_message = "Wrong type, expected 'boolean' for "
    if confirm_delete_all is None or confirm_delete_all is False:
        error_message = "To delete all hosts, provide confirm_delete_all=true in the request."

    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with raises_apierror(400, match_message=error_message):
            host_inventory.apis.hosts.delete_all(**params)


@pytest.mark.ephemeral
def test_delete_bulk_all_hosts_correct_parameters(
    check_delete_all_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts/all endpoint with all required parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-all
        assignee: fstavela
        importance: medium
        title: Inventory: Test DELETE on /hosts/all with all required parameters
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(6)
    hosts_data[0]["stale_timestamp"] = gen_fresh_date().isoformat()
    hosts_data[0]["insights_id"] = generate_uuid()
    hosts_data[1]["stale_timestamp"] = gen_fresh_date().isoformat()
    hosts_data[1].pop("insights_id", None)
    hosts_data[2]["stale_timestamp"] = gen_stale_date().isoformat()
    hosts_data[2]["insights_id"] = generate_uuid()
    hosts_data[3]["stale_timestamp"] = gen_stale_date().isoformat()
    hosts_data[3].pop("insights_id", None)
    hosts_data[4]["stale_timestamp"] = gen_stale_warning_date().isoformat()
    hosts_data[4]["insights_id"] = generate_uuid()
    hosts_data[5]["stale_timestamp"] = gen_stale_warning_date().isoformat()
    hosts_data[5].pop("insights_id", None)
    host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    check_delete_all_different_account(confirm_delete_all=True)

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response(
        staleness=["fresh", "stale", "stale_warning"]
    ).total
    assert pre_delete_count >= 5

    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.hosts.verify_all_deleted()

    post_delete_count = host_inventory.apis.hosts.get_hosts_response(
        staleness=["fresh", "stale", "stale_warning"]
    ).total
    assert post_delete_count == 0


@pytest.mark.ephemeral
def test_delete_bulk_display_name(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'display_name' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'display_name' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    delete_display_name: str = hosts_data[0]["display_name"]
    hosts_data[1]["display_name"] = delete_display_name
    hosts_data[2]["display_name"] = delete_display_name
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    check_delete_filtered_different_account(
        display_name=delete_display_name,
    )

    with host_inventory.apis.hosts.verify_host_count_changed(delta=-3):
        host_inventory.apis.hosts.delete_filtered(display_name=delete_display_name)
        host_inventory.apis.hosts.wait_for_deleted(hosts[:3])
        host_inventory.apis.hosts.verify_not_deleted(hosts[3:])


@pytest.mark.ephemeral
def test_delete_bulk_fqdn(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'fqdn' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'fqdn' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    delete_fqdn = hosts_data[0]["fqdn"]

    hosts_data[1]["fqdn"] = delete_fqdn
    hosts_data[2]["fqdn"] = delete_fqdn
    hosts_data[3].pop("fqdn", None)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    check_delete_filtered_different_account(fqdn=delete_fqdn)

    with host_inventory.apis.hosts.verify_host_count_changed(delta=-3):
        host_inventory.apis.hosts.delete_filtered(fqdn=delete_fqdn)
        host_inventory.apis.hosts.wait_for_deleted(hosts[:3])
        host_inventory.apis.hosts.verify_not_deleted(hosts[3:])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_hostname_or_id(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'hostname_or_id' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'hostname_or_id' parameter
    """
    searched_value = generate_display_name()
    hosts_data = host_inventory.datagen.create_n_hosts_data(10)
    hosts_data[0]["display_name"] = searched_value
    hosts_data[0]["fqdn"] = searched_value
    hosts_data[1]["display_name"] = searched_value
    hosts_data[2]["fqdn"] = searched_value
    hosts_data[3].pop("display_name")
    hosts_data[3]["fqdn"] = searched_value
    hosts_data[4].pop("fqdn")
    hosts_data[4]["display_name"] = searched_value
    hosts_data[5].pop("display_name")
    hosts_data[6].pop("fqdn")
    hosts_data[7].pop("display_name")
    hosts_data[7].pop("fqdn")
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    check_delete_filtered_different_account(hostname_or_id=searched_value)
    check_delete_filtered_different_account(hostname_or_id=hosts_ids[0])

    # Display name or fqdn
    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(hostname_or_id=searched_value)
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:5])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 5
    response = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=searched_value)
    assert response.total == 0
    # If we try to query all of the hosts by ID, we should get a 404 error because one is missing
    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id(hosts_ids)

    # Host ID
    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(hostname_or_id=hosts_ids[5])
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[5])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 1
    response = host_inventory.apis.hosts.get_hosts_response(hostname_or_id=hosts_ids[5])
    assert response.total == 0
    # If we try to query all of the hosts by ID, we should get a 404 error because one is missing
    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id(hosts_ids)


@pytest.mark.ephemeral
def test_delete_bulk_insights_id(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'insights_id' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'insights_id' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    for data in hosts_data:
        data["provider_type"] = generate_provider_type()
        data["provider_id"] = generate_uuid()
    hosts_data[1]["insights_id"] = hosts_data[0]["insights_id"]
    hosts_data[2]["insights_id"] = hosts_data[0]["insights_id"]
    hosts_data[3].pop("insights_id", None)
    hosts_ids = [
        host.id
        for host in host_inventory.kafka.create_hosts(
            hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
        )
    ]

    check_delete_filtered_different_account(insights_id=hosts_data[0]["insights_id"])

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(insights_id=hosts_data[0]["insights_id"])
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:3])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 3

    response = host_inventory.apis.hosts.get_hosts_response(
        insights_id=hosts_data[0]["insights_id"]
    )
    assert response.total == 0

    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[3:])}
    assert response_ids == set(hosts_ids[3:])


@pytest.mark.ephemeral
def test_delete_bulk_subscription_manager_id(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'subscription_manager_id' parameter

    JIRA: https://issues.redhat.com/browse/RHINENG-17386

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: addubey
        importance: high
        title: Inventory: Test DELETE on /hosts with 'subscription_manager_id' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    for data in hosts_data:
        data["provider_type"] = generate_provider_type()
        data["provider_id"] = generate_uuid()
    hosts_data[1]["subscription_manager_id"] = hosts_data[0]["subscription_manager_id"]
    hosts_data[2]["subscription_manager_id"] = hosts_data[0]["subscription_manager_id"]
    hosts_data[3].pop("subscription_manager_id", None)
    hosts_ids = [
        host.id
        for host in host_inventory.kafka.create_hosts(
            hosts_data=hosts_data, field_to_match=HostWrapper.provider_id
        )
    ]

    check_delete_filtered_different_account(
        subscription_manager_id=hosts_data[0]["subscription_manager_id"]
    )
    with host_inventory.apis.hosts.verify_host_count_changed(delta=-3):
        host_inventory.apis.hosts.delete_filtered(
            subscription_manager_id=hosts_data[0]["subscription_manager_id"]
        )
        host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:3])
        response = host_inventory.apis.hosts.get_hosts_response(
            subscription_manager_id=hosts_data[0]["subscription_manager_id"]
        )
        assert response.total == 0
        response_ids = {
            host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[3:])
        }
        assert response_ids == set(hosts_ids[3:])


@pytest.mark.ephemeral
def test_delete_bulk_provider_id(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'provider_id' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'provider_id' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    for data in hosts_data:
        data["provider_type"] = generate_provider_type()
        data["provider_id"] = generate_uuid()
    hosts_data[-1].pop("provider_type")
    hosts_data[-1].pop("provider_id")
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    check_delete_filtered_different_account(provider_id=hosts_data[0]["provider_id"])

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(provider_id=hosts_data[0]["provider_id"])
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[0])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 1
    response = host_inventory.apis.hosts.get_hosts_response(
        provider_id=hosts_data[0]["provider_id"]
    )
    assert response.total == 0
    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[1:])}
    assert response_ids == set(hosts_ids[1:])


@pytest.mark.ephemeral
def test_delete_bulk_provider_type(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'provider_type' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'provider_type' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    for data in hosts_data:
        data["provider_type"] = "aws"
        data["provider_id"] = generate_uuid()
    hosts_data[0]["provider_type"] = "ibm"
    hosts_data[1]["provider_type"] = "ibm"
    hosts_data[2]["provider_type"] = "ibm"
    hosts_data[3].pop("provider_type")
    hosts_data[3].pop("provider_id")
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    check_delete_filtered_different_account(provider_type="ibm")

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(provider_type="ibm")
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:3])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert pre_delete_count - 3 >= post_delete_count >= 2
    response = host_inventory.apis.hosts.get_hosts_response(provider_type="ibm")
    assert response.total == 0
    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[3:])}
    assert response_ids == set(hosts_ids[3:])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "registered_with",
    [
        pytest.param(values, id=",".join(values))
        for n in (1, 3, len(_CORRECT_REGISTERED_WITH_VALUES))
        for values in combinations(_CORRECT_REGISTERED_WITH_VALUES, n)
    ],
)
def test_delete_bulk_registered_with(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
    prepare_hosts_for_registered_with_filter_function: dict[str, HostWrapper],
    registered_with: Iterable,
):
    """
    Test DELETE on /hosts endpoint with 'registered_with' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'registered_with' parameter
    """
    to_delete_hosts, not_to_delete_hosts = determine_positive_hosts_by_registered_with(
        registered_with, prepare_hosts_for_registered_with_filter_function
    )
    to_delete_hosts_ids = {host.id for host in to_delete_hosts}
    not_to_delete_hosts_ids = {host.id for host in not_to_delete_hosts}
    all_hosts_ids = list(to_delete_hosts_ids | not_to_delete_hosts_ids)

    check_delete_filtered_different_account(registered_with=registered_with)

    with host_inventory.apis.hosts.verify_host_count_changed(-len(to_delete_hosts_ids)):
        host_inventory.apis.hosts.delete_filtered(registered_with=registered_with)

    response = host_inventory.apis.hosts.get_hosts_response(registered_with=registered_with)
    assert response.total == 0

    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id(all_hosts_ids)


@pytest.mark.ephemeral
@pytest.mark.parametrize("registered_with", _CORRECT_REGISTERED_WITH_VALUES)
def test_delete_bulk_registered_with_negative_values(
    host_inventory: ApplicationHostInventory,
    prepare_hosts_for_registered_with_filter_function: dict[str, HostWrapper],
    registered_with: str,
):
    """
    Test DELETE on /hosts endpoint with 'registered_with' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'registered_with' parameter
    """
    positive_hosts, negative_hosts = determine_positive_hosts_by_registered_with(
        [registered_with], prepare_hosts_for_registered_with_filter_function
    )
    to_delete_hosts_ids = {host.id for host in negative_hosts}
    not_to_delete_hosts_ids = {host.id for host in positive_hosts}
    all_hosts_ids = list(to_delete_hosts_ids | not_to_delete_hosts_ids)

    with host_inventory.apis.hosts.verify_host_count_changed(-len(to_delete_hosts_ids)):
        host_inventory.apis.hosts.delete_filtered(registered_with=["!" + registered_with])

    response = host_inventory.apis.hosts.get_hosts_response(
        registered_with=["!" + registered_with]
    )
    assert response.total == 0

    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id(all_hosts_ids)

    response_ids = {
        host.id for host in host_inventory.apis.hosts.get_hosts_by_id(not_to_delete_hosts_ids)
    }
    assert response_ids == not_to_delete_hosts_ids


# todo: Remove this test when https://issues.redhat.com/browse/ESSNTL-2743 is done
@pytest.mark.ephemeral
def test_delete_bulk_registered_with_temp_old(
    host_inventory: ApplicationHostInventory,
    check_delete_filtered_different_account,
):
    """
    Test DELETE on /hosts endpoint with old registered_with 'insights' value.
    This value should be removed from valid options after UI starts using new options.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2613

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Test DELETE on /hosts endpoint with old registered_with 'insights' value
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    hosts_data[1].pop("insights_id")
    hosts_ids = [
        host.id
        for host in host_inventory.kafka.create_hosts(
            hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
        )
    ]

    check_delete_filtered_different_account(registered_with=["insights"])

    with host_inventory.apis.hosts.verify_host_count_changed(-1):
        host_inventory.apis.hosts.delete_filtered(registered_with=["insights"])

    response = host_inventory.apis.hosts.get_hosts_response(registered_with=["insights"])
    assert response.total == 0

    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[1])}
    assert hosts_ids[1] in response_ids


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_delete_bulk_staleness(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'staleness' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'staleness' parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(6)

    hosts = create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data=hosts_data[0:2],
        stale_hosts_data=hosts_data[2:4],
        stale_warning_hosts_data=hosts_data[4:6],
        deltas=(15, 30, 3600),
    )

    host_ids = {host.id for host in hosts["fresh"] + hosts["stale"] + hosts["stale_warning"]}

    hosts_to_delete = {host.id for host in hosts["stale_warning"]}
    hosts_to_keep = host_ids - hosts_to_delete

    check_delete_filtered_different_account(staleness=["stale_warning"])

    logger.info(f"Host IDs: {host_ids}")
    logger.info(f"Expected hosts to be deleted: {hosts_to_delete}")
    logger.info(f"Expected hosts to keep: {hosts_to_keep}")

    with host_inventory.apis.hosts.verify_host_count_changed(-len(hosts_to_delete)):
        host_inventory.apis.hosts.delete_filtered(staleness=["stale_warning"])
        host_inventory.apis.hosts.wait_for_deleted(hosts_to_delete)

    response = host_inventory.apis.hosts.get_hosts_response(staleness=["stale_warning"])
    assert response.total == 0

    # Make sure we get 404 when trying to get hosts that don't exist
    with raises_apierror(404):
        {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(host_ids)}

    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_to_keep)}
    logger.info(f"Response IDs: {response_ids}")
    assert response_ids == hosts_to_keep


@pytest.mark.ephemeral
def test_delete_bulk_tags(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'tags' parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'tags' parameter
    """
    searched_tag = gen_tag()
    str_tag = convert_tag_to_string(searched_tag)
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    hosts_data[0]["tags"] = [searched_tag]
    hosts_data[1]["tags"] = [searched_tag, gen_tag()]
    hosts_data[2]["tags"] = [gen_tag()]
    hosts_data[3]["tags"] = [gen_tag(), gen_tag()]
    hosts_data[4].pop("tags", None)
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    check_delete_filtered_different_account(tags=[searched_tag])

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(tags=[str_tag])
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:2])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 2

    response = host_inventory.apis.hosts.get_hosts_response(tags=[str_tag])
    assert response.total == 0

    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[2:])}
    assert response_ids == set(hosts_ids[2:])


@pytest.mark.ephemeral
def test_delete_bulk_tags_multiple_values(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with multiple 'tags' parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with multiple 'tags' parameters
    """
    searched_tags = [gen_tag(), gen_tag()]
    str_tags = [convert_tag_to_string(tag) for tag in searched_tags]
    hosts_data = host_inventory.datagen.create_n_hosts_data(7)
    hosts_data[0]["tags"] = searched_tags
    hosts_data[1]["tags"] = [*searched_tags, gen_tag()]
    hosts_data[2]["tags"] = [searched_tags[0]]
    hosts_data[3]["tags"] = [searched_tags[0], gen_tag()]
    hosts_data[4]["tags"] = [gen_tag()]
    hosts_data[5]["tags"] = [gen_tag(), gen_tag()]
    hosts_data[6].pop("tags", None)
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    check_delete_filtered_different_account(tags=searched_tags)

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    host_inventory.apis.hosts.delete_filtered(tags=str_tags)
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:4])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 4
    response = host_inventory.apis.hosts.get_hosts_response(tags=str_tags)
    assert response.total == 0
    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[4:])}
    assert response_ids == set(hosts_ids[4:])


@pytest.mark.ephemeral
def test_delete_bulk_filter_operating_system(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'filter' parameter filtering by operating system

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'filter' parameter - OS
    """
    # Create hosts in the primary account
    hosts_data = host_inventory.datagen.create_n_hosts_data(6)
    hosts_data[0]["system_profile"]["operating_system"] = {"major": 8, "minor": 4, "name": "RHEL"}
    hosts_data[1]["system_profile"]["operating_system"] = {"major": 8, "minor": 4, "name": "RHEL"}
    hosts_data[2]["system_profile"]["operating_system"] = {"major": 8, "minor": 3, "name": "RHEL"}
    hosts_data[3]["system_profile"]["operating_system"] = {"major": 7, "minor": 4, "name": "RHEL"}
    hosts_data[4]["system_profile"]["operating_system"] = {
        "major": 7,
        "minor": 4,
        "name": "CentOS",
    }
    hosts_data[5]["system_profile"].pop("operating_system", None)
    hosts_ids_primary = [
        host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    ]

    # Create hosts in the secondary account
    for host_data in hosts_data:
        host_data["org_id"] = get_org_id(host_inventory_secondary.application)
        host_data["account"] = get_account_number(host_inventory_secondary.application)
    hosts_ids_secondary = [
        host.id for host in host_inventory_secondary.kafka.create_hosts(hosts_data=hosts_data)
    ]

    filter = ["[operating_system][RHEL][version][eq][]=8.4"]
    with host_inventory_secondary.apis.hosts.verify_host_count_not_changed():
        with host_inventory.apis.hosts.verify_host_count_changed(-2):
            host_inventory.apis.hosts.delete_filtered(filter=filter)
            host_inventory.apis.hosts.wait_for_deleted(hosts_ids_primary[:2])

    host_inventory.apis.hosts.verify_not_deleted(hosts_ids_primary[2:])
    host_inventory_secondary.apis.hosts.verify_not_deleted(hosts_ids_secondary)

    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert response.total == 0

    # Check secondary account without existing matching host in primary account
    with host_inventory_secondary.apis.hosts.verify_host_count_not_changed():
        host_inventory.apis.hosts.delete_filtered(filter=filter)

    host_inventory_secondary.apis.hosts.verify_not_deleted(hosts_ids_secondary)


@pytest.mark.ephemeral
def test_delete_bulk_filter_operating_system_multiple_values(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with multiple 'filter' parameters filtering by operating system

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with multiple 'filter' parameters - OS
    """
    # Create hosts in the primary account
    hosts_data = host_inventory.datagen.create_n_hosts_data(6)
    hosts_data[0]["system_profile"]["operating_system"] = {"major": 8, "minor": 4, "name": "RHEL"}
    hosts_data[1]["system_profile"]["operating_system"] = {"major": 8, "minor": 4, "name": "RHEL"}
    hosts_data[2]["system_profile"]["operating_system"] = {"major": 8, "minor": 3, "name": "RHEL"}
    hosts_data[3]["system_profile"]["operating_system"] = {"major": 7, "minor": 4, "name": "RHEL"}
    hosts_data[4]["system_profile"]["operating_system"] = {
        "major": 7,
        "minor": 4,
        "name": "CentOS",
    }
    hosts_data[5]["system_profile"].pop("operating_system", None)
    hosts_ids_primary = [
        host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    ]

    # Create hosts in the secondary account
    for host_data in hosts_data:
        host_data["org_id"] = get_org_id(host_inventory_secondary.application)
        host_data["account"] = get_account_number(host_inventory_secondary.application)
    hosts_ids_secondary = [
        host.id for host in host_inventory_secondary.kafka.create_hosts(hosts_data=hosts_data)
    ]

    filter = [
        "[operating_system][RHEL][version][eq][]=8.4",
        "[operating_system][RHEL][version][eq][]=8.3",
    ]
    with host_inventory_secondary.apis.hosts.verify_host_count_not_changed():
        with host_inventory.apis.hosts.verify_host_count_changed(-3):
            host_inventory.apis.hosts.delete_filtered(filter=filter)
            host_inventory.apis.hosts.wait_for_deleted(hosts_ids_primary[:3])

    host_inventory.apis.hosts.verify_not_deleted(hosts_ids_primary[3:])
    host_inventory_secondary.apis.hosts.verify_not_deleted(hosts_ids_secondary)

    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert response.total == 0
    response_ids = {
        host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids_primary[3:])
    }
    assert response_ids == set(hosts_ids_primary[3:])

    # Check secondary account without existing matching host in primary account
    with host_inventory_secondary.apis.hosts.verify_host_count_not_changed():
        host_inventory.apis.hosts.delete_filtered(filter=filter)

    host_inventory_secondary.apis.hosts.verify_not_deleted(hosts_ids_secondary)


@pytest.mark.ephemeral
def test_delete_bulk_filter_sap_sids(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'filter' parameter filtering by SAP SIDs

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with 'filter' parameter - SAP SIDs
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(5)
    hosts_data[0]["system_profile"]["sap_sids"] = ["H2O"]
    hosts_data[1]["system_profile"]["sap_sids"] = ["H2O", "ABC"]
    hosts_data[2]["system_profile"]["sap_sids"] = ["ABC"]
    hosts_data[3]["system_profile"]["sap_sids"] = ["ABC", "CBA"]
    hosts_data[4]["system_profile"].pop("sap_sids", None)

    for i in range(5):
        if "workloads" not in hosts_data[i]["system_profile"]:
            hosts_data[i]["system_profile"]["workloads"] = {"sap": {}}

    hosts_data[0]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O"]
    hosts_data[1]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O", "ABC"]
    hosts_data[2]["system_profile"]["workloads"]["sap"]["sids"] = ["ABC"]
    hosts_data[3]["system_profile"]["workloads"]["sap"]["sids"] = ["ABC", "CBA"]
    hosts_data[4]["system_profile"]["workloads"]["sap"].pop("sids", None)
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    filter = ["[sap_sids][]=H2O"]
    host_inventory.apis.hosts.delete_filtered(filter=filter)
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:2])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 2

    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert response.total == 0
    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[2:])}
    assert response_ids == set(hosts_ids[2:])


@pytest.mark.ephemeral
def test_delete_bulk_filter_sap_sids_multiple_values(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with multiple 'filter' parameters filtering by SAP SIDs

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with multiple 'filter' parameters - SAP SIDs
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(7)
    hosts_data[0]["system_profile"]["sap_sids"] = ["H2O", "ABC"]
    hosts_data[1]["system_profile"]["sap_sids"] = ["H2O", "ABC", "CBA"]
    hosts_data[2]["system_profile"]["sap_sids"] = ["H2O"]
    hosts_data[3]["system_profile"]["sap_sids"] = ["H2O", "CBA"]
    hosts_data[4]["system_profile"]["sap_sids"] = ["CBA"]
    hosts_data[5]["system_profile"]["sap_sids"] = ["CBA", "DPS"]
    hosts_data[6]["system_profile"].pop("sap_sids", None)

    for i in range(7):
        if "workloads" not in hosts_data[i]["system_profile"]:
            hosts_data[i]["system_profile"]["workloads"] = {"sap": {}}

    hosts_data[0]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O", "ABC"]
    hosts_data[1]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O", "ABC", "CBA"]
    hosts_data[2]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O"]
    hosts_data[3]["system_profile"]["workloads"]["sap"]["sids"] = ["H2O", "CBA"]
    hosts_data[4]["system_profile"]["workloads"]["sap"]["sids"] = ["CBA"]
    hosts_data[5]["system_profile"]["workloads"]["sap"]["sids"] = ["CBA", "DPS"]
    hosts_data[6]["system_profile"]["workloads"]["sap"].pop("sids", None)
    hosts_ids = [host.id for host in host_inventory.kafka.create_hosts(hosts_data=hosts_data)]

    pre_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    filter = ["[sap_sids][]=H2O", "[sap_sids][]=ABC"]
    host_inventory.apis.hosts.delete_filtered(filter=filter)
    host_inventory.apis.hosts.wait_for_deleted(hosts_ids[:2])
    post_delete_count = host_inventory.apis.hosts.get_hosts_response().total
    assert post_delete_count == pre_delete_count - 2

    response = host_inventory.apis.hosts.get_hosts_response(filter=filter)
    assert response.total == 0
    response_ids = {host.id for host in host_inventory.apis.hosts.get_hosts_by_id(hosts_ids[2:])}
    assert response_ids == set(hosts_ids[2:])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_filter_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    Test DELETE on /hosts endpoint with 'filter' parameter doesn't affect different accounts

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-account-integrity
        assignee: fstavela
        importance: critical
        title: Inventory: Test DELETE on /hosts with 'filter' doesn't affect different accounts
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["system_profile"]["operating_system"] = {"major": 8, "minor": 4, "name": "RHEL"}
    sec_host_data = {
        **host_data,
        "org_id": get_org_id(host_inventory_secondary.application),
    }

    host = host_inventory.kafka.create_host(host_data=host_data)
    sec_host = host_inventory_secondary.kafka.create_host(host_data=sec_host_data)

    # Check with existing matching host in secondary account
    filter = ["[operating_system][RHEL][version][eq][]=8.4"]
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(filter=filter)

    host_inventory_secondary.apis.hosts.wait_for_deleted(sec_host)

    # Check without existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(filter=filter)

    host_inventory.apis.hosts.verify_not_deleted(host)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
@pytest.mark.parametrize(
    "id_param_name", ["display_name", "fqdn", "insights_id", "subscription_manager_id"]
)
def test_delete_bulk_combination_all(
    check_delete_filtered_different_account,
    host_inventory: ApplicationHostInventory,
    id_param_name: str,
):
    """
    Test DELETE on /hosts endpoint with combination of multiple parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with combination of multiple parameters
    """
    # A total of 8 hosts will be created. Host 1 (using 0-based notation) will be
    # the target host we filter for at the end.  Host 7 will be completely different.
    # Hosts 0-6 will be mostly the same with these exceptions:
    #   hosts 1-6 will be in the same group (hosts 0 and 7 won't be in a group)
    #   host 2 will have a different value for the field that id_param_name represents
    #   host 3 will have a different provider_type
    #   host 4 will be stale (the rest will be fresh)
    #   host 5 will have different tags
    #   hosts 0-5 will be in the filtered time range
    #
    # All provider ids will be unique per host.

    tags = [gen_tag()]
    str_tags = [convert_tag_to_string(tag) for tag in tags]
    hosts_data = [host_inventory.datagen.create_host_data()]
    hosts_data[0][id_param_name] = generate_uuid()
    hosts_data[0]["provider_id"] = generate_uuid()
    hosts_data[0]["provider_type"] = "aws"
    hosts_data[0]["tags"] = tags

    for _ in range(6):
        hosts_data.append(dict(hosts_data[0]))
        hosts_data[-1]["provider_id"] = generate_uuid()
    hosts_data[2][id_param_name] = generate_uuid()
    hosts_data[3]["provider_type"] = "ibm"
    hosts_data[5]["tags"] = [gen_tag()]

    hosts_data.append(host_inventory.datagen.create_host_data())
    hosts_data[-1]["provider_type"] = "gcp"
    hosts_data[-1]["provider_id"] = generate_uuid()

    hosts = host_inventory.kafka.create_hosts(hosts_data, field_to_match=HostWrapper.provider_id)

    # Assign hosts to group - all except hosts[0] and hosts[-1]
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[1:-1])

    # Step through all events, to remove conflicts during later update
    provider_ids = [host.provider_id for host in hosts[1:-1]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.provider_id, provider_ids)

    # Group creation corrupted the hosts updated timestamps, so we have to reset
    # them now.  Update a random field (using rhc_client_id in this case) and
    # verify the update has completed.
    rhc_client_id = generate_uuid()
    for host_data in hosts_data:
        host_data["system_profile"]["rhc_client_id"] = rhc_client_id
    updated_hosts = host_inventory.kafka.create_hosts(
        hosts_data, field_to_match=HostWrapper.provider_id
    )
    for host in updated_hosts:
        host_inventory.apis.hosts.wait_for_system_profile_updated(
            host.id, rhc_client_id=rhc_client_id
        )

    # Make host 4 stale and preserve ordering.
    fresh_hosts_data = hosts_data[0:4] + hosts_data[5:]
    stale_hosts_data = hosts_data[4:5]
    hosts_in_state = create_hosts_fresh_stale(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        deltas=(15, 3600, 7200),
        field_to_match=HostWrapper.provider_id,
    )
    updated_hosts = (
        hosts_in_state["fresh"][0:4] + hosts_in_state["stale"] + hosts_in_state["fresh"][4:]
    )

    # Guarantee that the updated_end host will have a later updated time than
    # the other hosts in the filtered range
    updated_end_host = host_inventory.kafka.create_hosts(
        [hosts_data[5]], field_to_match=HostWrapper.provider_id
    )[0]

    # Guarantee that the remaining hosts will be outside the filtered range
    host_inventory.kafka.create_hosts(hosts_data[6:], field_to_match=HostWrapper.provider_id)

    id_param = {id_param_name: hosts_data[1][id_param_name]}

    check_delete_filtered_different_account(
        **id_param,
        provider_type=hosts_data[1]["provider_type"],
        staleness=["fresh"],
        tags=tags,
    )

    # Due to how we create a set of mixed-state hosts now, the stale host
    # (updated_hosts[4]) will have the earliest updated timestamp.  Thus, the
    # updated_start/updated_end params look a little strange, but they encompass
    # the first 6 hosts.
    with host_inventory.apis.hosts.verify_host_count_changed(-1):
        host_inventory.apis.hosts.delete_filtered(
            **id_param,
            provider_type=hosts_data[0]["provider_type"],
            staleness=["fresh"],
            tags=str_tags,
            updated_start=updated_hosts[4].updated,
            updated_end=updated_end_host.updated,
            group_name=[group_name],
        )
        host_inventory.apis.hosts.wait_for_deleted(updated_hosts[1])

    # Step through all events to remove conflicts during teardown
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.id, [updated_hosts[1].id])

    response = host_inventory.apis.hosts.get_hosts_response(
        **id_param,
        provider_type=hosts_data[0]["provider_type"],
        staleness=["fresh"],
        tags=str_tags,
        updated_start=updated_hosts[4].updated,
        updated_end=updated_end_host.updated,
        group_name=[group_name],
    )
    assert response.total == 0
    host_inventory.apis.hosts.verify_not_deleted([updated_hosts[0], *updated_hosts[2:]])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "params",
    [
        ("display_name", "fqdn"),
        ("display_name", "insights_id"),
        ("display_name", "hostname_or_id"),
        ("fqdn", "insights_id"),
        ("fqdn", "hostname_or_id"),
        ("insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id"),
        ("display_name", "fqdn", "hostname_or_id"),
        ("display_name", "insights_id", "hostname_or_id"),
        ("fqdn", "insights_id", "hostname_or_id"),
        ("display_name", "fqdn", "insights_id", "hostname_or_id"),
    ],
)
def test_delete_bulk_combination_invalid_parameters(
    host_inventory: ApplicationHostInventory, params: tuple[str]
):
    """
    Test GET of host using invalid combination of parameters.

    JIRA: https://issues.redhat.com/browse/ESSNTL-931

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-api-validation
        assignee: fstavela
        importance: medium
        title: Inventory: Test GET of host using invalid combination of parameters.
    """
    host = host_inventory.kafka.create_host()
    parameters = {}
    for param in params:
        if param == "hostname_or_id":
            parameters["hostname_or_id"] = host.fqdn
        else:
            parameters[param] = getattr(host, param)

    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with pytest.raises(ApiException) as err:
            host_inventory.apis.hosts.delete_filtered(**parameters)
        assert err.value.status == 400
        assert (
            "Only one of [fqdn, display_name, hostname_or_id, insights_id] "
            "may be provided at a time." in err.value.body
        )

    host_inventory.apis.hosts.verify_not_deleted(host, retries=1)


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["display_name", "hostname_or_id"])
def test_delete_bulk_with_wildcard(host_inventory: ApplicationHostInventory, field: str):
    """
    Test DELETE on /hosts endpoint with wildcard in parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with wildcard in parameter
    """
    value1 = generate_string_of_length(10, use_digits=False, use_punctuation=False)
    value2 = generate_string_of_length(10, use_digits=False, use_punctuation=False)
    value1 = value1.replace(value1[2:6], "12lm")
    value2 = value2.replace(value2[4:8], "12lm")
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)
    if field == "hostname_or_id":
        hosts_data[0]["display_name"] = value1
        hosts_data[0]["fqdn"] = generate_string_of_length(
            10, use_digits=False, use_punctuation=False
        )
        hosts_data[1]["fqdn"] = value2
        hosts_data[1]["display_name"] = generate_string_of_length(
            10, use_digits=False, use_punctuation=False
        )
        hosts_data[2]["fqdn"] = generate_string_of_length(
            10, use_digits=False, use_punctuation=False
        )
        hosts_data[2]["display_name"] = generate_string_of_length(
            10, use_digits=False, use_punctuation=False
        )
    else:
        hosts_data[0][field] = value1
        hosts_data[1][field] = value2
        hosts_data[2][field] = generate_string_of_length(
            10, use_digits=False, use_punctuation=False
        )
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    param = {field: "1*m"}
    host_inventory.apis.hosts.delete_filtered(**param)
    host_inventory.apis.hosts.wait_for_deleted(hosts[:-1])
    host_inventory.apis.hosts.verify_not_deleted(hosts[-1])


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["display_name", "hostname_or_id"])
def test_delete_bulk_only_wildcard(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    field: str,
):
    """
    Test DELETE on /hosts endpoint with only wildcard in parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts with only wildcard in parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    if field == "hostname_or_id":
        hosts_data[0]["display_name"] = generate_uuid()
        hosts_data[1]["fqdn"] = generate_uuid()
    else:
        hosts_data[0][field] = generate_uuid()
        hosts_data[1][field] = generate_uuid()
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    param = {field: "*"}

    # Check different account
    sec_host_data = {
        **hosts_data[0],
        "org_id": get_org_id(host_inventory_secondary.application),
    }

    host_secondary = host_inventory_secondary.kafka.create_host(sec_host_data)

    # Check with existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(**param)
        host_inventory_secondary.apis.hosts.wait_for_deleted(host_secondary)

    # Check without existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(**param)

    # Back to main account
    host_inventory.apis.hosts.delete_filtered(**param)
    host_inventory.apis.hosts.wait_for_deleted(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["fqdn", "provider_id"])
def test_delete_bulk_not_accepted_wildcard(host_inventory: ApplicationHostInventory, field: str):
    """
    Test DELETE on /hosts endpoint doesn't accept wildcard on certain parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: fstavela
        importance: high
        title: Inventory: Test DELETE on /hosts doesn't accept wildcard on certain parameters
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_id"] = generate_uuid()
    host_data["provider_type"] = generate_provider_type()
    host_data[field] = generate_uuid()
    host_id = host_inventory.kafka.create_host(host_data).id
    param = {field: "*"}

    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory.apis.hosts.delete_filtered(**param)

    host_inventory.apis.hosts.verify_not_deleted(host_id, retries=1)


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["insights_id", "provider_type"])
def test_delete_bulk_parameters_verification(host_inventory: ApplicationHostInventory, field: str):
    """
    Test parameters verification on DELETE on /hosts endpoint

    JIRA: https://issues.redhat.com/browse/ESSNTL-1509

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-api-validation
        assignee: fstavela
        importance: medium
        title: Inventory: Test parameters verification on DELETE on /hosts endpoint
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["provider_id"] = generate_uuid()
    host_data["provider_type"] = generate_provider_type()
    host_id = host_inventory.kafka.create_host(host_data).id
    param = {field: generate_string_of_length(10)}

    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with pytest.raises(ApiException) as err:
            host_inventory.apis.hosts.delete_filtered(**param)
        assert err.value.status == 400

    host_inventory.apis.hosts.verify_not_deleted(host_id, retries=1)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_updated_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Delete hosts by updated_start
    """
    host1 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host2 = host_inventory.kafka.create_host()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.updated if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    host_inventory.apis.hosts.delete_filtered(updated_start=time_filter_s)
    host_inventory.apis.hosts.wait_for_deleted([host2, host3])
    response_hosts = host_inventory.apis.hosts.get_hosts(updated_start=time_filter_s)
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(host1)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_updated_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Delete hosts by updated_end
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.updated if timestamp == "exact" else time_filter

    time_filter_s = time_filter.strftime(time_format)

    host_inventory.apis.hosts.delete_filtered(updated_end=time_filter_s)
    host_inventory.apis.hosts.wait_for_deleted([host1, host2])
    response_hosts = host_inventory.apis.hosts.get_hosts(updated_end=time_filter_s)
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(host3)


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_updated(host_inventory: ApplicationHostInventory, timestamp: str):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Delete hosts by combined updated_start and updated_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now()
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now()
    host_after = host_inventory.kafka.create_host()

    time_start = hosts[0].updated if timestamp == "exact" else time_start
    time_end = hosts[-1].updated if timestamp == "exact" else time_end

    host_inventory.apis.hosts.delete_filtered(updated_start=time_start, updated_end=time_end)
    host_inventory.apis.hosts.wait_for_deleted(hosts)
    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted([host_before, host_after])


@pytest.mark.ephemeral
def test_delete_bulk_updated_both_same(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Delete hosts by combined updated_start and updated_end - both same
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    host_inventory.apis.hosts.delete_filtered(
        updated_start=hosts[1].updated, updated_end=hosts[1].updated
    )
    host_inventory.apis.hosts.wait_for_deleted(hosts[1])
    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=hosts[1].updated, updated_end=hosts[1].updated
    )
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted([hosts[0], hosts[2]])


@pytest.mark.parametrize("timezone", ["+03:00", "-03:00"], ids=["plus", "minus"])
@pytest.mark.ephemeral
def test_delete_bulk_updated_different_timezone(
    host_inventory: ApplicationHostInventory,
    timezone: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Delete hosts by updated with not-UTC timezone
    """
    host_before = host_inventory.kafka.create_host()
    hosts = host_inventory.kafka.create_random_hosts(3)
    host_after = host_inventory.kafka.create_host()

    hours_delta = 3 if timezone[0] == "+" else -3
    time_start = (hosts[0].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )
    time_end = (hosts[-1].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )

    host_inventory.apis.hosts.delete_filtered(updated_start=time_start, updated_end=time_end)
    host_inventory.apis.hosts.wait_for_deleted(hosts)
    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted([host_before, host_after])


@pytest.mark.ephemeral
def test_delete_bulk_updated_not_created(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-hosts-filter-by-updated, inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: high
      title: Test that updated filters work by last updated, not created timestamp - deleting hosts
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_start = datetime.now()
    host3 = host_inventory.kafka.create_host()
    host_inventory.apis.hosts.patch_hosts(host2, display_name=f"{host2.display_name}-updated")
    time_end = datetime.now()
    host_inventory.apis.hosts.patch_hosts(host3, display_name=f"{host3.display_name}-updated")

    host_inventory.apis.hosts.delete_filtered(updated_start=time_start, updated_end=time_end)
    host_inventory.apis.hosts.wait_for_deleted(host2)

    response_hosts = host_inventory.apis.hosts.get_hosts(
        updated_start=time_start, updated_end=time_end
    )
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted([host1, host3])


@pytest.mark.ephemeral
@pytest.mark.parametrize("param", ["updated_start", "updated_end"])
@pytest.mark.parametrize("value", INCORRECT_DATETIMES)
def test_delete_bulk_updated_incorrect_format(
    host_inventory: ApplicationHostInventory, param: str, value: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements:
        - inv-hosts-filter-by-updated
        - inv-api-validation
        - inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: medium
      negative: true
      title: Delete hosts with wrong format of updated_start and updated_end parameters
    """
    host_inventory.kafka.create_host()
    if isinstance(value, str):
        value = value.replace("'", "").replace('"', "").replace("\\", "")
    api_param = {param: value}
    error_value = f'\\"{value}\\"' if (isinstance(value, list) and len(value)) else f"'{value}'"
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with raises_apierror(400, f"{error_value} is not a 'date-time'"):
            host_inventory.apis.hosts.delete_filtered(**api_param)


@pytest.mark.ephemeral
def test_delete_bulk_updated_start_after_end(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements:
        - inv-hosts-filter-by-updated
        - inv-api-validation
        - inv-hosts-delete-filtered-hosts
      assignee: fstavela
      importance: medium
      negative: true
      title: Delete hosts with updated_start bigger than updated_end
    """
    host = host_inventory.kafka.create_host()
    time_start = host.updated + timedelta(hours=1)
    time_end = host.updated - timedelta(hours=1)
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        with raises_apierror(400, "updated_start cannot be after updated_end."):
            host_inventory.apis.hosts.delete_filtered(
                updated_start=time_start, updated_end=time_end
            )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_updated_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
        requirements:
            - inv-hosts-delete-filtered-hosts
            - inv-account-integrity
            - inv-hosts-filter-by-updated
        assignee: fstavela
        importance: critical
        title: Test DELETE on /hosts with 'updated' parameters doesn't affect different accounts
    """
    time_start = datetime.now()
    host_primary = host_inventory.kafka.create_host()
    host_secondary = host_inventory_secondary.kafka.create_host()
    time_end = datetime.now()

    # Check with existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(
            updated_start=time_start, updated_end=time_end
        )
        host_inventory_secondary.apis.hosts.wait_for_deleted(host_secondary)

    # Check without existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(
            updated_start=time_start, updated_end=time_end
        )

    host_inventory.apis.hosts.verify_not_deleted(host_primary)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_last_check_in_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-hosts-filter-by-last_check_in, inv-hosts-delete-filtered-hosts
      assignee: aprice
      importance: high
      title: Delete hosts by last_check_in_start
    """
    host1 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host2 = host_inventory.kafka.create_host()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_str = time_filter.strftime(time_format)

    host_inventory.apis.hosts.delete_filtered(last_check_in_start=time_filter_str)
    host_inventory.apis.hosts.wait_for_deleted([host2, host3])
    response_hosts = host_inventory.apis.hosts.get_hosts(last_check_in_start=time_filter_str)
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(host1)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_last_check_in_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-hosts-filter-by-last_check_in, inv-hosts-delete-filtered-hosts
      assignee: aprice
      importance: high
      title: Delete hosts by last_check_in_end
    """
    host1 = host_inventory.kafka.create_host()
    host2 = host_inventory.kafka.create_host()
    time_filter = datetime.now()
    host3 = host_inventory.kafka.create_host()
    time_filter = host2.last_check_in if timestamp == "exact" else time_filter

    time_filter_s = time_filter.strftime(time_format)

    host_inventory.apis.hosts.delete_filtered(last_check_in_end=time_filter_s)
    host_inventory.apis.hosts.wait_for_deleted([host1, host2])
    response_hosts = host_inventory.apis.hosts.get_hosts(last_check_in_end=time_filter_s)
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(host3)


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_delete_bulk_last_check_in(host_inventory: ApplicationHostInventory, timestamp: str):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-hosts-filter-by-last_check_in, inv-hosts-delete-filtered-hosts
      assignee: aprice
      importance: high
      title: Delete hosts by combined last_check_in_start and last_check_in_end
    """
    host_before = host_inventory.kafka.create_host()
    time_start = datetime.now()
    hosts = host_inventory.kafka.create_random_hosts(3)
    time_end = datetime.now()
    host_after = host_inventory.kafka.create_host()

    time_start = hosts[0].last_check_in if timestamp == "exact" else time_start
    time_end = hosts[-1].last_check_in if timestamp == "exact" else time_end

    host_inventory.apis.hosts.delete_filtered(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    host_inventory.apis.hosts.wait_for_deleted(hosts)
    response_hosts = host_inventory.apis.hosts.get_hosts(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted([host_before, host_after])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_last_check_in_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
        requirements:
            - inv-hosts-delete-filtered-hosts
            - inv-account-integrity
            - inv-hosts-filter-by-last_check_in
        assignee: aprice
        importance: critical
        title: Test DELETE on /hosts with 'last_check_in' params doesn't affect other accounts
    """
    time_start = datetime.now()
    host_primary = host_inventory.kafka.create_host()
    host_secondary = host_inventory_secondary.kafka.create_host()
    time_end = datetime.now()

    # Check with existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(
            last_check_in_start=time_start, last_check_in_end=time_end
        )
        host_inventory_secondary.apis.hosts.wait_for_deleted(host_secondary)

    # Check without existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(
            last_check_in_start=time_start, last_check_in_end=time_end
        )

    host_inventory.apis.hosts.verify_not_deleted(host_primary)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
)
def test_delete_bulk_group_name(host_inventory: ApplicationHostInventory, case_insensitive: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

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

    filtered_name = group_name.upper() if case_insensitive else group_name

    host_inventory.apis.hosts.delete_filtered(group_name=[filtered_name])
    host_inventory.apis.hosts.wait_for_deleted(hosts[0])
    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[filtered_name])
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(hosts[1:])


@pytest.mark.ephemeral
def test_delete_bulk_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_id
        assignee: maarif
        importance: high
        title: Delete hosts by group_id
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    host_inventory.apis.hosts.delete_filtered(group_id=[group.id])
    host_inventory.apis.hosts.wait_for_deleted(hosts[0])
    response_hosts = host_inventory.apis.hosts.get_hosts(group_id=[group.id])
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(hosts[1:])


@pytest.mark.ephemeral
def test_delete_bulk_with_group_name_and_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_name, inv-hosts-filter-by-group_id, inv-api-validation
        assignee: maarif
        importance: high
        negative: true
        title: Verify 400 error when both group_name and group_id filters are used together for delete
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    with raises_apierror(400, "Cannot use both 'group_name' and 'group_id' filters together"):
        host_inventory.apis.hosts.delete_filtered(group_name=[group_name], group_id=[group.id])


@pytest.mark.ephemeral
def test_delete_bulk_group_name_empty(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5138

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Delete hosts by empty group_name - delete ungrouped hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(2)
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[0])

    host_inventory.apis.hosts.delete_filtered(group_name=[""])
    host_inventory.apis.hosts.wait_for_deleted(hosts[1])
    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[""])
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(hosts[0])


@pytest.mark.ephemeral
def test_delete_bulk_group_name_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5108

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Delete hosts by multiple group_name values
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    group_name1 = generate_display_name()
    group_name2 = generate_display_name()
    host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    host_inventory.apis.groups.create_group(group_name2, hosts=hosts[1:3])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[3])

    host_inventory.apis.hosts.delete_filtered(group_name=[group_name1, group_name2])
    host_inventory.apis.hosts.wait_for_deleted(hosts[:3])
    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[group_name1, group_name2])
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(hosts[3:])


@pytest.mark.ephemeral
def test_delete_bulk_group_name_multiple_hosts_in_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-hosts-delete-filtered-hosts, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Delete hosts by group_name, if the group has multiple hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    host_inventory.apis.hosts.delete_filtered(group_name=[group_name])
    host_inventory.apis.hosts.wait_for_deleted(hosts[:2])
    response_hosts = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response_hosts) == 0
    host_inventory.apis.hosts.verify_not_deleted(hosts[2])


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_delete_bulk_group_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements:
            - inv-hosts-delete-filtered-hosts
            - inv-account-integrity
            - inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: critical
        title: Test DELETE on /hosts with 'group_name' parameter doesn't affect different accounts
    """
    host_primary = host_inventory.kafka.create_host()
    host_secondary = host_inventory_secondary.kafka.create_host()

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=host_primary)
    host_inventory_secondary.apis.groups.create_group(group_name, hosts=host_secondary)

    # Check with existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(group_name=[group_name])
        host_inventory_secondary.apis.hosts.wait_for_deleted(host_secondary)

    # Check without existing matching host in secondary account
    with host_inventory.apis.hosts.verify_host_count_not_changed():
        host_inventory_secondary.apis.hosts.delete_filtered(group_name=[group_name])

    host_inventory.apis.hosts.verify_not_deleted(host_primary)


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


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "system_type",
    [
        pytest.param(values, id=",".join(values))
        for n in (1, 3, len(_CORRECT_SYSTEM_TYPE_VALUES))
        for values in combinations(_CORRECT_SYSTEM_TYPE_VALUES, n)
    ],
)
def test_delete_hosts_by_system_type(
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_deleting_by_system_type_filter: dict[str, list[HostWrapper]],
    system_type: list[str],
):
    """.
    JIRA: https://issues.redhat.com/browse/RHINENG-19125

    metadata:
        requirements: inv-hosts-delete-filtered-hosts
        assignee: zabikeno
        importance: high
        title: Confirm system_type parameter delete right hosts
    """
    prepared_hosts = deepcopy(setup_hosts_for_deleting_by_system_type_filter)
    expected_hosts = flatten(prepared_hosts.pop(item) for item in system_type)

    host_inventory.apis.hosts.delete_filtered(system_type=system_type)
    host_inventory.apis.hosts.wait_for_deleted(expected_hosts)

    not_deleted = flatten(hosts for hosts in prepared_hosts.values())
    host_inventory.apis.hosts.verify_not_deleted(not_deleted)

    response = host_inventory.apis.hosts.get_hosts(system_type=system_type)
    assert len(response) == 0
