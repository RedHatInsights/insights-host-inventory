# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from random import randint
from time import sleep
from typing import Protocol

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.staleness_utils import STALENESS_LIMITS
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state
from iqe_host_inventory.utils.staleness_utils import set_staleness
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory.utils.tag_utils import convert_tag_to_string

logger = logging.getLogger(__name__)

STALE_WARNING_DAYS = 7
CULLED_DAYS = 30

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]


def gen_fresh_date(tz: timezone = UTC) -> datetime:
    """Generate some future date for "fresh" host."""
    return datetime.now(tz) + timedelta(days=randint(1, 7))


def gen_stale_date(tz: timezone = UTC) -> datetime:
    """Generate "stale" host date - STALE_WARNING_DAYS < date < now()"""
    return datetime.now(tz) - timedelta(days=randint(1, STALE_WARNING_DAYS - 1))


def gen_stale_warning_date(tz: timezone = UTC) -> datetime:
    """Generate "stale_warning" host date - now()-CULLED_DAYS < date < now()-STALE_WARNING_DAYS"""
    return datetime.now(tz) - timedelta(days=randint(STALE_WARNING_DAYS, CULLED_DAYS - 1))


def gen_culled_date(tz: timezone = UTC) -> datetime:
    """Generate "stale_warning" host date - now()-CULLED_DAYS-7 < date < now()-CULLED_DAYS"""
    return datetime.now(tz) - timedelta(days=randint(CULLED_DAYS, CULLED_DAYS + 7))


class CallProtocol(Protocol):
    def __call__(self, tz: timezone = UTC) -> datetime: ...


gen_dates: dict[str, CallProtocol] = {
    "fresh": gen_fresh_date,
    "stale": gen_stale_date,
    "stale_warning": gen_stale_warning_date,
    "culled": gen_culled_date,
}


def gen_date_by_state(state: str = "fresh") -> datetime:
    return gen_dates[state]()


@pytest.fixture(
    name="tz", params=[UTC, timezone(timedelta(hours=10)), timezone(timedelta(hours=-4))]
)
def timezone_fixture(request: pytest.FixtureRequest) -> timezone:
    return request.param


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_list_hosts_by_staleness(host_inventory: ApplicationHostInventory) -> None:
    """
    Filter hosts by staleness values - fresh, stale, stale_warning.

    1. Create some hosts spanning all staleness states
    2. Retrieve these hosts filtering by state
    3. Verify that only the proper hosts are returned

    metadata:
        requirements: inv-hosts-filter-by-staleness, inv-staleness-hosts
        assignee: fstavela
        importance: critical
        title: Inventory: Filter hosts by staleness values - fresh, stale, stale_warning.
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(6)

    hosts = create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data=hosts_data[0:2],
        stale_hosts_data=hosts_data[2:4],
        stale_warning_hosts_data=hosts_data[4:6],
    )

    expected_host_ids: dict[str, set[str]] = {
        state: {host.id for host in state_hosts} for state, state_hosts in hosts.items()
    }

    all_hosts = {host_id for ids in expected_host_ids.values() for host_id in ids}

    http_host_ids: dict[str, set[str]] = {}

    for state in ["fresh", "stale", "stale_warning"]:
        response = host_inventory.apis.hosts.get_hosts(staleness=[state])
        response_ids = {host.id for host in response}
        known_response_ids = all_hosts.intersection(response_ids)
        http_host_ids[state] = known_response_ids

    assert http_host_ids == expected_host_ids


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_host_stale_warning_to_fresh(host_inventory: ApplicationHostInventory) -> None:
    """
    Verify stale warning host becomes fresh if its stale_timestamp was updated.

    1. Create a host in stale warning state
    2. Make sure host is returned by GET request with staleness="stale_warning".
    3. Update the host
    4. Make sure host is returned by GET request with staleness="fresh".

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-filter-by-staleness
        assignee: fstavela
        importance: high
        title: Inventory: Confirm stale warning host becomes fresh
            when a host is updated
    """
    host_data = host_inventory.datagen.create_host_data()

    # Create a stale_warning host
    host: HostWrapper = create_hosts_in_state(
        host_inventory,
        [host_data],
        host_state="stale_warning",
        deltas=(5, 6, 7200),
    )[0]

    # Verify the host state is stale_warning
    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale_warning"])
    assert host.id in [host.id for host in response_hosts]

    # Update the host
    updated_host_data = deepcopy(host_data)
    updated_host_data["display_name"] = generate_display_name()
    host = host_inventory.kafka.create_host(updated_host_data)
    logger.info(
        f"Host id={host.id}, updated={host.updated}, display_name={host.display_name}, stale_timestamp={host.stale_timestamp}"  # noqa
    )
    host_inventory.apis.hosts.wait_for_updated(
        host, display_name=updated_host_data["display_name"]
    )

    # Verify the host is fresh
    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["fresh"])
    assert host.id in [host.id for host in response_hosts]


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_host_stale_to_fresh(host_inventory: ApplicationHostInventory) -> None:
    """
    Verify stale host becomes fresh if its stale_timestamp was updated.

    1. Create a "stale" host
    2. Make sure host is returned by GET request with staleness="stale".
    3. Update the host
    4. Make sure host is returned by GET request with staleness="fresh".

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-filter-by-staleness
        assignee: fstavela
        importance: high
        title: Inventory: Confirm stale host becomes fresh if its stale_timestamp was updated
    """
    host_data = host_inventory.datagen.create_host_data()

    # Create a stale host
    host = create_hosts_in_state(
        host_inventory,
        [host_data],
        host_state="stale",
        deltas=(5, 3600, 7200),
    )[0]

    # Verify the host is stale
    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale"])
    assert host.id in [host.id for host in response_hosts]

    # Update the host
    updated_host_data = deepcopy(host_data)
    updated_host_data["display_name"] = generate_display_name()
    host = host_inventory.kafka.create_host(updated_host_data)
    logger.info(
        f"Host id={host.id}, updated={host.updated}, display_name={host.display_name}, stale_timestamp={host.stale_timestamp}"  # noqa
    )
    host_inventory.apis.hosts.wait_for_updated(
        host, display_name=updated_host_data["display_name"]
    )

    # Verify the host is fresh
    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["fresh"])
    assert host.id in [host.id for host in response_hosts]


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
def test_host_stale_warning_to_culled(host_inventory: ApplicationHostInventory) -> None:
    """
    Verify host is culled after its stale_culling date

    1. Create a host in stale warning state
    2. Make sure host is returned by GET request with staleness="stale_warning".
    3. Wait for expected amount of time for the host to exceed its culling date
    4. Make sure host is no longer returned by GET request with staleness="stale_warning".
    5. Make sure host is culled and not returned even by direct GET by id request.

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-filter-by-staleness
        assignee: fstavela
        importance: high
        title: Inventory: Confirm host is culled after its culling date
    """
    host_data = host_inventory.datagen.create_host_data()

    # Create a stale_warning host
    host = create_hosts_in_state(
        host_inventory,
        [host_data],
        host_state="stale_warning",
        deltas=(1, 2, 5),
    )[0]

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale_warning"])
    assert host.id in [host.id for host in response_hosts]

    delay = 5
    logger.info(f"Waiting {delay} seconds for host to become culled")
    sleep(delay)

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale_warning"])
    assert host.id not in [host.id for host in response_hosts]

    with raises_apierror(404):
        host_inventory.apis.hosts.get_hosts_by_id_response(host)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_default_staleness_filter_hosts_and_tags(host_inventory: ApplicationHostInventory) -> None:
    """
    Test that the staleness filter defaults to ['fresh', 'stale', 'stale_warning']
    on /hosts endpoint

    JIRA: https://issues.redhat.com/browse/ESSNTL-1382

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-get-list
        assignee: fstavela
        importance: medium
        title: Test default staleness filter on /hosts
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data=hosts_data[:1],
        stale_hosts_data=hosts_data[1:2],
        stale_warning_hosts_data=hosts_data[2:],
    )
    all_hosts = hosts["fresh"] + hosts["stale"] + hosts["stale_warning"]
    host_ids = [host.id for host in all_hosts]

    # GET /hosts
    response = host_inventory.apis.hosts.get_hosts_response()
    assert response.count >= 3

    found_host_ids = {host.id for host in response.results}
    assert set(host_ids).intersection(found_host_ids) == set(host_ids)

    # GET /tags
    response = host_inventory.apis.tags.get_tags_response()
    assert response.count >= sum(len(host.tags) for host in all_hosts)

    expected_tags = {convert_tag_to_string(tag) for host in all_hosts for tag in host.tags}
    found_tags = {
        convert_tag_to_string(tag.tag.to_dict()): tag.count
        for tag in response.results
        if convert_tag_to_string(tag.tag.to_dict()) in expected_tags
    }
    assert set(found_tags.keys()) == expected_tags
    assert set(found_tags.values()) == {1}


@pytest.mark.ephemeral
def test_staleness_filter_max_delta(
    host_inventory: ApplicationHostInventory,
    hbi_staleness_defaults: dict[str, int],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-8730

    metadata:
      requirements: inv-staleness-hosts
      assignee: fstavela
      importance: high
      title: Create staleness settings with max allowed deltas and get hosts by staleness filter
    """

    logger.info(f"Creating account record with:\n{STALENESS_LIMITS}")
    host_inventory.apis.account_staleness.create_staleness(**STALENESS_LIMITS)
    staleness_response = host_inventory.apis.account_staleness.get_staleness()
    validate_staleness_response(staleness_response, hbi_staleness_defaults, STALENESS_LIMITS)

    host_data = host_inventory.datagen.create_host_data()
    host_inventory.kafka.create_host(host_data)

    response = host_inventory.apis.hosts.get_hosts_response()  # Using default staleness
    assert response

    staleness_options = ["fresh", "stale", "stale_warning"]
    for staleness in staleness_options:
        response = host_inventory.apis.hosts.get_hosts_response(staleness=[staleness])
        assert response


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_get_culled_hosts(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-17845

    Culled hosts must not appear in API responses, even if their 'updated'
    timestamp is recent (e.g. from a PATCH).  The API uses 'last_check_in'
    to determine staleness, not 'updated'.

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-get-list
        assignee: fstavela
        importance: medium
        title: Test that culled hosts are not returned by API, even if patched
    """
    culled_hosts = host_inventory.kafka.create_random_hosts(4)
    logger.info("Sleeping 15 seconds to let the hosts age")
    sleep(15)

    # Patch 2 hosts — updates 'updated' timestamp, but not 'last_check_in'
    patched_hosts = culled_hosts[:2]
    host_inventory.apis.hosts.patch_hosts(patched_hosts, display_name=generate_display_name())

    host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, [host.insights_id for host in patched_hosts]
    )

    # Set tight staleness deltas so all old hosts become culled
    host_inventory.apis.account_staleness.create_staleness(
        conventional_time_to_stale=13,
        conventional_time_to_stale_warning=14,
        conventional_time_to_delete=15,
    )

    fresh_hosts = host_inventory.kafka.create_random_hosts(2)

    fresh_hosts_ids = {host.id for host in fresh_hosts}
    patched_hosts_ids = {host.id for host in patched_hosts}
    culled_hosts_ids = {host.id for host in culled_hosts[2:]}

    response = host_inventory.apis.hosts.get_hosts_response()
    assert response.count >= 2

    found_host_ids = {host.id for host in response.results}
    assert len(found_host_ids.intersection(culled_hosts_ids)) == 0
    assert len(found_host_ids.intersection(patched_hosts_ids)) == 0
    assert found_host_ids.intersection(fresh_hosts_ids) == set(fresh_hosts_ids)


@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_staleness_stage_prod(host_inventory: ApplicationHostInventory) -> None:
    """
    This test doesn't use Kafka, so it can run in Stage and Prod

    https://issues.redhat.com/browse/RHINENG-20318

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-get-list
        assignee: fstavela
        importance: high
        title: Test that staleness filtering works correctly after staleness config updates
    """
    host = host_inventory.upload.create_host()

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["fresh"])
    assert host.id in {response_host.id for response_host in response_hosts}

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale", "stale_warning"])
    assert host.id not in {response_host.id for response_host in response_hosts}

    # Create new staleness config
    deltas = (1, 3600, 7200)
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale")

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["fresh", "stale_warning"])
    assert host.id not in {response_host.id for response_host in response_hosts}

    # Update staleness config
    deltas = (1, 2, 7200)
    set_staleness(host_inventory, deltas)
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="stale_warning")

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["fresh", "stale"])
    assert host.id not in {response_host.id for response_host in response_hosts}

    # Delete staleness config
    host_inventory.apis.account_staleness.delete_staleness()
    host_inventory.apis.hosts.wait_for_staleness(host, staleness="fresh")

    response_hosts = host_inventory.apis.hosts.get_hosts(staleness=["stale", "stale_warning"])
    assert host.id not in {response_host.id for response_host in response_hosts}
