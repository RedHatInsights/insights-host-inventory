# mypy: disallow-untyped-defs

"""
metadata:
  requirements: inv-per-reporter-staleness
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import timedelta
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory.utils import assert_datetimes_mismatch
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import DELTAS
from iqe_host_inventory.utils.staleness_utils import TIME_TO_DELETE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE
from iqe_host_inventory.utils.staleness_utils import TIME_TO_STALE_WARNING
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import set_staleness
from iqe_host_inventory.utils.staleness_utils import validate_staleness_response
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory_api.models import HostOut
from iqe_host_inventory_api.models import PerReporterStaleness

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]

ACCURACY = timedelta(milliseconds=100)

logger = logging.getLogger(__name__)


def do_reporter_check_ins(
    host_inventory: ApplicationHostInventory,
    host_type: str,
) -> HostOut:
    """
    Helper function that performs check-ins as two different reporters and
    validates top-level host fields along with per_reporter fields.

    Possible future enhancement:
        Generalize this function to accept n reporters
    """
    # Set the timestamp as a reporter might, but it should be ignored
    host_data = host_inventory.datagen.create_host_data(
        host_type=host_type,
        reporter="puptoo",
        stale_timestamp=generate_timestamp(delta=timedelta(days=5)),
    )

    host = host_inventory.kafka.create_host(host_data)
    host_initial_puptoo = host_inventory.apis.hosts.get_host_by_id(host)
    verify_staleness(host_inventory, host_initial_puptoo, "puptoo")

    # Stash for later check
    puptoo_reporter_staleness = host_initial_puptoo.per_reporter_staleness["puptoo"]

    sleep(1)  # Used to check that the `last_check_in` timestamps are different

    host_data.update(
        reporter="yupana",
        stale_timestamp=generate_timestamp(delta=timedelta(days=3)),
        ansible_host=generate_display_name(),
    )
    host_inventory.kafka.create_host(host_data)
    host_inventory.apis.hosts.wait_for_updated(host, reporter="yupana")

    host_with_yupana = host_inventory.apis.hosts.get_host_by_id(host)
    verify_staleness(host_inventory, host_with_yupana, "yupana")

    assert_datetimes_mismatch(
        host_with_yupana.last_check_in, host_initial_puptoo.last_check_in, ACCURACY
    )

    # Verify that the puptoo data is unchanged after the yupana reporter checks in
    assert puptoo_reporter_staleness == host_with_yupana.per_reporter_staleness["puptoo"]

    return host_with_yupana


def verify_staleness(
    host_inventory: ApplicationHostInventory,
    host: HostOut,
    reporter: str,
) -> None:
    assert host.per_reporter_staleness is not None
    reporter_staleness: PerReporterStaleness = host.per_reporter_staleness[reporter]

    assert reporter_staleness.check_in_succeeded

    assert_datetimes_equal(reporter_staleness.last_check_in, host.last_check_in)
    assert_datetimes_equal(
        host.stale_timestamp,
        reporter_staleness.stale_timestamp,
    )
    assert_datetimes_equal(
        host.stale_warning_timestamp,
        reporter_staleness.stale_warning_timestamp,
    )
    assert_datetimes_equal(
        host.culled_timestamp,
        reporter_staleness.culled_timestamp,
    )
    verify_reporter_timestamps(host_inventory, host, reporter)


def verify_reporter_timestamps(
    host_inventory: ApplicationHostInventory,
    host: HostOut,
    reporter: str,
) -> None:
    response = host_inventory.apis.account_staleness.get_staleness()

    time_to_stale = response[TIME_TO_STALE]
    time_to_stale_warning = response[TIME_TO_STALE_WARNING]
    time_to_stale_delete = response[TIME_TO_DELETE]

    reporter_staleness = host.per_reporter_staleness[reporter]

    assert_datetimes_equal(
        reporter_staleness.stale_timestamp,
        reporter_staleness.last_check_in + timedelta(seconds=time_to_stale),
    )
    assert_datetimes_equal(
        reporter_staleness.stale_warning_timestamp,
        reporter_staleness.last_check_in + timedelta(seconds=time_to_stale_warning),
    )
    assert_datetimes_equal(
        reporter_staleness.culled_timestamp,
        reporter_staleness.last_check_in + timedelta(seconds=time_to_stale_delete),
    )


def log_staleness_timestamps(host: HostOut, reporter: str | None = None) -> None:
    logger.info(f"host updated: {host.updated.strftime('%m/%d/%Y %H:%M:%S')}")
    logger.info(f"host stale_timestamp: {host.stale_timestamp.strftime('%m/%d/%Y %H:%M:%S')}")
    logger.info(
        f"host stale_warning_timestamp: {host.stale_warning_timestamp.strftime('%m/%d/%Y %H:%M:%S')}"  # noqa
    )
    logger.info(f"host culled_timestamp: {host.culled_timestamp.strftime('%m/%d/%Y %H:%M:%S')}")

    def _log_reporter_timestamps(host: HostOut, reporter: str) -> None:
        per_reporter = host.per_reporter_staleness[reporter]
        logger.info(
            f"{reporter} last_check_in: {per_reporter.last_check_in.strftime('%m/%d/%Y %H:%M:%S')}"
        )
        logger.info(
            f"{reporter} stale_timestamp: {per_reporter.stale_timestamp.strftime('%m/%d/%Y %H:%M:%S')}"  # noqa
        )
        logger.info(
            f"{reporter} stale_warning_timestamp: {per_reporter.stale_warning_timestamp.strftime('%m/%d/%Y %H:%M:%S')}"  # noqa
        )
        logger.info(
            f"{reporter} culled_timestamp: {per_reporter.culled_timestamp.strftime('%m/%d/%Y %H:%M:%S')}"  # noqa
        )

    if not reporter:
        return

    if reporter == "all":
        for reporter in host.per_reporter_staleness:
            _log_reporter_timestamps(host, str(reporter))
    else:
        assert reporter in host.per_reporter_staleness
        _log_reporter_timestamps(host, reporter)


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_per_reporter_default_staleness(
    host_inventory: ApplicationHostInventory,
    host_type: str,
) -> None:
    """Test per reporter using default staleness settings
    JIRA: https://issues.redhat.com/browse/ESSNTL-1261

    metadata:
        requirements: inv-staleness-hosts
        assignee: fstavela
        importance: high
        title: Test per reporter staleness
    """

    do_reporter_check_ins(host_inventory, host_type)


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_per_reporter_custom_staleness(
    host_inventory: ApplicationHostInventory,
    host_type: str,
    hbi_staleness_defaults: dict[str, int],
) -> None:
    """Test per reporter using custom staleness settings
    JIRA: https://issues.redhat.com/browse/ESSNTL-1261

    metadata:
        requirements: inv-staleness-hosts
        assignee: fstavela
        importance: high
        title: Test per reporter staleness
    """
    defaults = hbi_staleness_defaults

    settings = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{settings}")
    response = host_inventory.apis.account_staleness.create_staleness(**settings).to_dict()
    validate_staleness_response(response, defaults, settings)

    do_reporter_check_ins(host_inventory, host_type)


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_per_reporter_update_staleness(
    host_inventory: ApplicationHostInventory,
    host_type: str,
    hbi_staleness_defaults: dict[str, int],
) -> None:
    """Test per reporter custom staleness settings update

    metadata:
        requirements: inv-staleness-hosts
        assignee: msager
        importance: high
        title: Test per reporter staleness
    """
    # Generate some initial settings
    settings = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{settings}")
    response = host_inventory.apis.account_staleness.create_staleness(**settings).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    # Check in as multiple reporters and validate
    host = do_reporter_check_ins(host_inventory, host_type)

    # Update the settings
    settings = gen_staleness_settings(want_sample=False)
    logger.info(f"Creating account record with:\n{settings}")
    response = host_inventory.apis.account_staleness.update_staleness(**settings).to_dict()
    validate_staleness_response(response, hbi_staleness_defaults, settings)

    # Verify that the per_reporter timestamps have been updated correctly
    updated_host = host_inventory.apis.hosts.get_host_by_id(host)
    verify_reporter_timestamps(host_inventory, updated_host, "puptoo")
    verify_reporter_timestamps(host_inventory, updated_host, "yupana")


@pytest.mark.ephemeral
@pytest.mark.parametrize("new_reporter", ["satellite", "discovery"])
def test_per_reporter_staleness_replace_yupana(
    host_inventory: ApplicationHostInventory,
    new_reporter: str,
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-2664

    metadata:
        assignee: fstavela
        importance: high
        title: Test that 'satellite' and 'discovery' reporters replace 'yupana' in PRS
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = "yupana"

    host = host_inventory.kafka.create_host(host_data)
    assert list(host.per_reporter_staleness.keys()) == ["yupana"]
    assert host.per_reporter_staleness["yupana"]

    response_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    assert list(response_host.per_reporter_staleness.keys()) == ["yupana"]
    assert response_host.per_reporter_staleness["yupana"]

    host_data["reporter"] = new_reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert list(updated_host.per_reporter_staleness.keys()) == [new_reporter]
    assert updated_host.per_reporter_staleness[new_reporter]

    response_host = host_inventory.apis.hosts.wait_for_updated(host.id, reporter=new_reporter)[0]
    assert list(response_host.per_reporter_staleness.keys()) == [new_reporter]
    assert response_host.per_reporter_staleness[new_reporter]


@pytest.mark.ephemeral
@pytest.mark.parametrize("new_reporter", ["satellite", "discovery"])
def test_per_reporter_staleness_all_reporters_replace_yupana(
    host_inventory: ApplicationHostInventory,
    new_reporter: str,
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-2664

    metadata:
        assignee: fstavela
        importance: high
        title: Test 'yupana' replacements when host has multiple reporters
    """
    other_reporters = ["puptoo", "rhsm-conduit", "cloud-connector", "iqe-hbi"]
    host_data = host_inventory.datagen.create_host_data()
    for reporter in other_reporters:
        host_data["reporter"] = reporter
        host_inventory.kafka.create_host(host_data)

    host_data["reporter"] = "yupana"
    host = host_inventory.kafka.create_host(host_data)
    assert set(host.per_reporter_staleness.keys()) == set(other_reporters).union({"yupana"})
    assert host.per_reporter_staleness["yupana"]

    response_host = host_inventory.apis.hosts.wait_for_updated(host.id, reporter="yupana")[0]
    assert set(response_host.per_reporter_staleness.keys()) == set(other_reporters).union({
        "yupana"
    })
    assert response_host.per_reporter_staleness["yupana"]

    host_data["reporter"] = new_reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert set(updated_host.per_reporter_staleness.keys()) == set(other_reporters).union({
        new_reporter
    })
    assert updated_host.per_reporter_staleness[new_reporter]

    response_host = host_inventory.apis.hosts.wait_for_updated(host.id, reporter=new_reporter)[0]
    assert set(response_host.per_reporter_staleness.keys()) == set(other_reporters).union({
        new_reporter
    })
    assert response_host.per_reporter_staleness[new_reporter]


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "second_reporter", ["puptoo", "rhsm-conduit", "cloud-connector", "iqe-hbi"]
)
def test_per_reporter_staleness_not_replace_yupana(
    host_inventory: ApplicationHostInventory, second_reporter: str
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-2664

    metadata:
        assignee: fstavela
        importance: high
        title: Test that non 'satellite' and non 'discovery' reporters don't replace 'yupana'
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = "yupana"

    host = host_inventory.kafka.create_host(host_data)
    assert list(host.per_reporter_staleness.keys()) == ["yupana"]
    assert host.per_reporter_staleness["yupana"]

    response_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    assert list(response_host.per_reporter_staleness.keys()) == ["yupana"]
    assert response_host.per_reporter_staleness["yupana"]

    host_data["reporter"] = second_reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert set(updated_host.per_reporter_staleness.keys()) == {"yupana", second_reporter}
    assert updated_host.per_reporter_staleness["yupana"]
    assert updated_host.per_reporter_staleness[second_reporter]

    response_host = host_inventory.apis.hosts.wait_for_updated(host, reporter=second_reporter)[0]
    assert set(response_host.per_reporter_staleness.keys()) == {"yupana", second_reporter}
    assert response_host.per_reporter_staleness["yupana"]
    assert response_host.per_reporter_staleness[second_reporter]


@pytest.mark.ephemeral
@pytest.mark.parametrize("first_reporter", ["puptoo", "rhsm-conduit", "cloud-connector"])
@pytest.mark.parametrize("second_reporter", ["satellite", "discovery"])
def test_per_reporter_staleness_not_replace_others(
    host_inventory: ApplicationHostInventory,
    first_reporter: str,
    second_reporter: str,
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-2664

    metadata:
        assignee: fstavela
        importance: high
        title: Test that 'satellite' and 'discovery' don't replace other reporters than 'yupana'
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["reporter"] = first_reporter

    host = host_inventory.kafka.create_host(host_data)
    assert list(host.per_reporter_staleness.keys()) == [first_reporter]
    assert host.per_reporter_staleness[first_reporter]

    response_host = host_inventory.apis.hosts.get_host_by_id(host.id)
    assert list(response_host.per_reporter_staleness.keys()) == [first_reporter]
    assert response_host.per_reporter_staleness[first_reporter]

    host_data["reporter"] = second_reporter
    updated_host = host_inventory.kafka.create_host(host_data)
    assert set(updated_host.per_reporter_staleness.keys()) == {first_reporter, second_reporter}
    assert updated_host.per_reporter_staleness[first_reporter]
    assert updated_host.per_reporter_staleness[second_reporter]

    response_host = host_inventory.apis.hosts.wait_for_updated(host, reporter=second_reporter)[0]
    assert set(response_host.per_reporter_staleness.keys()) == {first_reporter, second_reporter}
    assert response_host.per_reporter_staleness[first_reporter]
    assert response_host.per_reporter_staleness[second_reporter]


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup_culled")
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
def test_per_reporter_registered_with(
    host_inventory: ApplicationHostInventory,
    host_type: str,
) -> None:
    """Test per reporter registered_with filter with custom staleness

    metadata:
        requirements: inv-staleness-hosts
        assignee: msager
        importance: high
        title: Test per reporter staleness
    """
    # Set the timestamp as a reporter might, but it should be ignored
    host_data = host_inventory.datagen.create_host_data(
        host_type=host_type,
        reporter="puptoo",
        stale_timestamp=generate_timestamp(delta=timedelta(days=5)),
    )

    host = host_inventory.kafka.create_host(host_data)
    host_initial_puptoo = host_inventory.apis.hosts.get_host_by_id(host)
    verify_staleness(host_inventory, host_initial_puptoo, "puptoo")

    response = host_inventory.apis.hosts.get_hosts(
        hostname_or_id=host.id, registered_with=["puptoo"]
    )
    assert len(response) == 1

    logger.info("puptoo initial check in (host created).  No custom settings yet.")
    log_staleness_timestamps(response[0], "puptoo")

    deltas = (1, 2, 5)
    logger.info("Setting custom staleness deltas to:")
    logger.info(
        f"stale = {deltas[0]} second, stale_warning = {deltas[1]} seconds, culled = {deltas[2]} seconds"  # noqa
    )
    set_staleness(host_inventory, deltas)

    host_data.update(
        reporter="yupana",
        stale_timestamp=generate_timestamp(delta=timedelta(days=3)),
        ansible_host=generate_display_name(),
    )
    host_inventory.kafka.create_host(host_data)
    host_inventory.apis.hosts.wait_for_updated(host, reporter="yupana")
    host_with_yupana = host_inventory.apis.hosts.get_host_by_id(host)
    verify_staleness(host_inventory, host_with_yupana, "yupana")

    response = host_inventory.apis.hosts.get_hosts(
        hostname_or_id=host.id, registered_with=["yupana"]
    )
    assert len(response) == 1

    logger.info("yupana check in")
    log_staleness_timestamps(response[0], "all")

    # Do a few more yupana checkins to keep the host fresh.
    for _ in range(3):
        host_data.update(ansible_host=generate_display_name())
        host_inventory.kafka.create_host(host_data)
        host_inventory.apis.hosts.wait_for_updated(host, ansible_host=host_data["ansible_host"])

        response = host_inventory.apis.hosts.get_hosts(
            hostname_or_id=host.id, registered_with=["yupana"]
        )
        assert len(response) == 1

        logger.info("yupana check in")
        log_staleness_timestamps(response[0], "all")

        sleep(2)

    # At this point, the host should be fresh from yupana's perspective, but
    # culled from puptoo's perspective.
    response = host_inventory.apis.hosts.get_hosts(
        hostname_or_id=host.id, registered_with=["yupana"]
    )
    assert len(response) == 1

    response = host_inventory.apis.hosts.get_hosts(
        hostname_or_id=host.id, registered_with=["puptoo"]
    )
    assert len(response) == 0

    sleep(deltas[2])

    # Now the host should be culled
    response = host_inventory.apis.hosts.get_hosts(
        hostname_or_id=host.id, registered_with=["yupana"]
    )
    assert len(response) == 0


def create_hosts_reporter_state(
    host_inventory: ApplicationHostInventory,
    host_type: str = "conventional",
    host_count: int = 2,
    reporters: list[str] | None = None,
    with_tags: bool = False,
    deltas: DELTAS = (15, 30, 45),
) -> dict[str, list[HostWrapper]]:
    """
    Helper function that creates hosts for each combination of reporters and
    staleness states (fresh, stale, stale_warning).

    :param host_type: "conventional" or "edge"
    :param host_count: host count per reporter per state (default is 2)
    :param reporters: list of reporters
    :param with_tags: create tags for hosts?
    """
    if reporters is None:
        reporters = ["puptoo", "yupana"]

    fresh_hosts_data = []
    stale_hosts_data = []
    stale_warning_hosts_data = []

    if with_tags:
        create_host_data = host_inventory.datagen.create_n_hosts_data_with_tags
    else:
        create_host_data = host_inventory.datagen.create_n_hosts_data

    for reporter in reporters:
        fresh_hosts_data.extend(
            create_host_data(
                host_count,
                host_type=host_type,
                reporter=reporter,
            )
        )
        stale_hosts_data.extend(
            create_host_data(
                host_count,
                host_type=host_type,
                reporter=reporter,
            )
        )
        stale_warning_hosts_data.extend(
            create_host_data(
                host_count,
                host_type=host_type,
                reporter=reporter,
            )
        )

    hosts = create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data,
        stale_hosts_data,
        stale_warning_hosts_data,
        host_type=host_type,
        deltas=deltas,
    )

    return hosts


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_get_hosts_filter_by_reporter_state(host_inventory: ApplicationHostInventory) -> None:
    """Test GET /hosts filtering by reporter and state combination

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-filter-by-reporter
        assignee: msager
        importance: high
        title: Test GET /hosts filtering by reporter and state combination
    """
    hosts = create_hosts_reporter_state(host_inventory)

    all_host_ids = {host.id for state in hosts.keys() for host in hosts[state]}

    for state in ["fresh", "stale", "stale_warning"]:
        for reporter, range_min, range_max in [("puptoo", 0, 2), ("yupana", 2, 4)]:
            response = host_inventory.apis.hosts.get_hosts(
                staleness=[state], registered_with=[reporter]
            )
            response_expected_ids = {host.id for host in response} & all_host_ids
            assert response_expected_ids == {host.id for host in hosts[state][range_min:range_max]}


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_delete_hosts_filter_by_reporter_state(host_inventory: ApplicationHostInventory) -> None:
    """Test /DELETE hosts filtering by reporter and state combination

    metadata:
        requirements: inv-staleness-hosts, inv-hosts-filter-by-reporter
        assignee: msager
        importance: high
        title: Test /DELETE hosts filtering by reporter and state combination
    """
    hosts = create_hosts_reporter_state(host_inventory, deltas=(20, 40, 60))

    all_host_ids = {host.id for state in hosts.keys() for host in hosts[state]}
    to_be_deleted = deepcopy(all_host_ids)

    for state in ["fresh", "stale", "stale_warning"]:
        for reporter, range_min, range_max in [("puptoo", 0, 2), ("yupana", 2, 4)]:
            response = host_inventory.apis.hosts.get_hosts(
                staleness=[state], registered_with=[reporter]
            )
            response_expected_ids = {host.id for host in response} & all_host_ids
            assert response_expected_ids == {host.id for host in hosts[state][range_min:range_max]}

            host_inventory.apis.hosts.delete_filtered(
                staleness=[state], registered_with=[reporter]
            )
            host_inventory.apis.hosts.wait_for_deleted(hosts[state][range_min:range_max])
            to_be_deleted -= response_expected_ids

            # If we get this far, the correct hosts were deleted.  Make sure no
            # other hosts were also deleted.
            response = host_inventory.apis.hosts.get_hosts_by_id(list(to_be_deleted))
            assert len(response) == len(to_be_deleted)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_get_tags_filter_by_reporter_state(host_inventory: ApplicationHostInventory) -> None:
    """Test GET /tags filtering by reporter and state combination

    metadata:
        requirements: inv-staleness-hosts, inv-tags-get-list, inv-hosts-filter-by-reporter
        assignee: msager
        importance: high
        title: Test GET /tags filtering by reporter and state combination
    """
    reporters = ["puptoo", "yupana", generate_uuid()]
    states = ["fresh", "stale", "stale_warning"]

    hosts = create_hosts_reporter_state(
        host_inventory,
        host_count=1,
        reporters=reporters,
        with_tags=True,
    )

    unexpected_tags = flatten(hosts[state][2].tags for state in states)

    # There are 3 hosts in each state (9 total).  They correspond to reporters
    # "puptoo", "yupana", and a randomly named one.  Retrieve tags filtering by
    # each reporter+state combo and validate.  Also, verify that no unexpected
    # tags are returned.  These latter tags correspond to the random reporter
    # across all states.

    for state in states:
        for idx, reporter in enumerate(reporters[0:2]):
            response = host_inventory.apis.tags.get_tags_response(
                staleness=[state], registered_with=[reporter]
            )
            expected_tags = hosts[state][idx].tags

            assert response.count >= len(expected_tags)
            assert len(response.results) == response.count
            assert_tags_found(expected_tags, response.results)
            assert_tags_not_found(unexpected_tags, response.results)
