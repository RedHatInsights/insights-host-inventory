import logging
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from itertools import combinations
from typing import Any

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_DATETIMES
from iqe_host_inventory.utils import flatten
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import _CORRECT_SYSTEM_TYPE_VALUES
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_tags
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale
from iqe_host_inventory.utils.staleness_utils import create_hosts_fresh_stale_stalewarning
from iqe_host_inventory.utils.tag_utils import assert_tags_found
from iqe_host_inventory.utils.tag_utils import assert_tags_not_found
from iqe_host_inventory_api import ApiException

pytestmark = [pytest.mark.backend]

logger = logging.getLogger(__name__)


@pytest.fixture
def setup_hosts_with_tags(host_inventory: ApplicationHostInventory):
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    for data in hosts_data:
        data["display_name"] = generate_display_name()
        data["fqdn"] = generate_display_name()
        data["insights_id"] = generate_uuid()
        data["provider_id"] = generate_uuid()
        data["tags"] = generate_tags()
    hosts_data[0]["provider_type"] = "alibaba"
    hosts_data[1]["provider_type"] = "aws"
    yield host_inventory.kafka.create_hosts(hosts_data=hosts_data)


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_get_all_tags(setup_hosts_with_tags, host_inventory):
    """
    Test GET on /tags endpoint without parameters

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags without parameters
    """
    response = host_inventory.apis.tags.get_tags_response()
    assert response.count >= 2
    assert len(response.results) == response.count
    assert_tags_found(
        setup_hosts_with_tags[0].tags + setup_hosts_with_tags[1].tags, response.results
    )


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_display_name(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using display_name URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-display_name
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with display_name parameter
    """
    if case == "exact":
        response = host_inventory.apis.tags.get_tags_response(
            display_name=setup_hosts_with_tags[0].display_name
        )
    else:
        response = host_inventory.apis.tags.get_tags_response(
            display_name=getattr(setup_hosts_with_tags[0].display_name, case)()
        )
    assert response.total == len(setup_hosts_with_tags[0].tags)
    assert len(response.results) == response.total
    assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
    assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_fqdn(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using fqdn URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-fqdn
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with fqdn parameter
    """
    if case == "exact":
        response = host_inventory.apis.tags.get_tags_response(fqdn=setup_hosts_with_tags[0].fqdn)
    else:
        response = host_inventory.apis.tags.get_tags_response(
            fqdn=getattr(setup_hosts_with_tags[0].fqdn, case)()
        )
    assert response.total == len(setup_hosts_with_tags[0].tags)
    assert len(response.results) == response.total
    assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
    assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_hostname_or_id(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using hostname_or_id URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-hostname_or_id
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with hostname_or_id parameter
    """

    def _test_hostname_or_id(hostname_or_id):
        if case == "exact":
            response = host_inventory.apis.tags.get_tags_response(hostname_or_id=hostname_or_id)
        else:
            response = host_inventory.apis.tags.get_tags_response(
                hostname_or_id=getattr(hostname_or_id, case)()
            )
        assert response.total == len(setup_hosts_with_tags[0].tags)
        assert len(response.results) == response.total
        assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
        assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)

    _test_hostname_or_id(setup_hosts_with_tags[0].id)
    _test_hostname_or_id(setup_hosts_with_tags[0].fqdn)
    _test_hostname_or_id(setup_hosts_with_tags[0].display_name)


@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_insights_id(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using insights_id URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-insights_id
        assignee: fstavela
        importance: medium
        title: Inventory: GET on /tags with insights_id parameter
    """
    if case == "exact":
        response = host_inventory.apis.tags.get_tags_response(
            insights_id=setup_hosts_with_tags[0].insights_id
        )
    else:
        response = host_inventory.apis.tags.get_tags_response(
            insights_id=getattr(setup_hosts_with_tags[0].insights_id, case)()
        )
    assert response.total == len(setup_hosts_with_tags[0].tags)
    assert len(response.results) == response.total
    assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
    assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize("case", ["exact", "lower", "upper"])
def test_get_tags_by_provider_id(setup_hosts_with_tags, host_inventory, case):
    """
    Test GET on /tags endpoint using provider_id URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-provider_id
        assignee: fstavela
        importance: medium
        title: Inventory: GET on /tags with provider_id parameter
    """
    if case == "exact":
        response = host_inventory.apis.tags.get_tags_response(
            provider_id=setup_hosts_with_tags[0].provider_id
        )
    else:
        response = host_inventory.apis.tags.get_tags_response(
            provider_id=getattr(setup_hosts_with_tags[0].provider_id, case)()
        )
    assert response.total == len(setup_hosts_with_tags[0].tags)
    assert len(response.results) == response.total
    assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
    assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_provider_type(setup_hosts_with_tags, host_inventory):
    """
    Test GET on /tags endpoint using provider_type URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-provider_type
        assignee: fstavela
        importance: medium
        title: Inventory: GET on /tags with provider_type parameter
    """
    response = host_inventory.apis.tags.get_tags_response(
        provider_type=setup_hosts_with_tags[0].provider_type
    )
    assert response.count >= len(setup_hosts_with_tags[0].tags)
    assert len(response.results) == response.count
    assert_tags_found(setup_hosts_with_tags[0].tags, response.results)
    assert_tags_not_found(setup_hosts_with_tags[1].tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_get_tags_by_staleness(host_inventory: ApplicationHostInventory):
    """
    Test GET on /tags endpoint using staleness URL parameter

    JIRA: https://issues.redhat.com/browse/ESSNTL-1383

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-staleness
        assignee: fstavela
        importance: high
        title: Inventory: GET on /tags with staleness parameter
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)

    hosts = create_hosts_fresh_stale_stalewarning(
        host_inventory,
        fresh_hosts_data=hosts_data[0:1],
        stale_hosts_data=hosts_data[1:2],
        stale_warning_hosts_data=hosts_data[2:3],
    )

    for staleness in ["fresh", "stale", "stale_warning"]:
        response = host_inventory.apis.tags.get_tags_response(staleness=[staleness])
        assert response.count >= len(hosts[staleness][0].tags)
        assert len(response.results) == response.count

        if staleness == "fresh":
            assert_tags_found(hosts["fresh"][0].tags, response.results)
            assert_tags_not_found(
                hosts["stale"][0].tags + hosts["stale_warning"][0].tags, response.results
            )

        elif staleness == "stale":
            assert_tags_found(hosts["stale"][0].tags, response.results)
            assert_tags_not_found(
                hosts["fresh"][0].tags + hosts["stale_warning"][0].tags, response.results
            )

        else:
            assert_tags_found(hosts["stale_warning"][0].tags, response.results)
            assert_tags_not_found(
                hosts["fresh"][0].tags + hosts["stale"][0].tags, response.results
            )


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
def test_get_tags_invalid_parameters_combinations(
    host_inventory: ApplicationHostInventory, params: tuple[str, ...]
):
    """
    Test GET of tags using invalid combination of parameters.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2193

    metadata:
        requirements: inv-tags-get-list, inv-api-validation
        assignee: fstavela
        importance: low
        title: Inventory: Test GET of tags using invalid combination of parameters.
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host = host_inventory.kafka.create_host(host_data=host_data)

    parameters = {}
    for param in params:
        if param == "hostname_or_id":
            parameters["hostname_or_id"] = host.fqdn
        else:
            parameters[param] = getattr(host, param)

    with pytest.raises(ApiException) as err:
        host_inventory.apis.tags.get_tags_response(**parameters)
    assert err.value.status == 400
    assert (
        "Only one of [fqdn, display_name, hostname_or_id, insights_id] may be provided at a time."
        in err.value.body
    )


@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
@pytest.mark.parametrize(
    "id_param_name", ["display_name", "fqdn", "insights_id", "hostname_or_id"]
)
def test_get_tags_valid_parameters_combinations(
    host_inventory: ApplicationHostInventory, id_param_name: str
):
    """
    Test GET of tags using valid combination of parameters.

    JIRA: https://issues.redhat.com/browse/ESSNTL-2193

    metadata:
        requirements: inv-tags-get-list
        assignee: fstavela
        importance: medium
        title: Inventory: Test GET of tags using valid combination of parameters.
    """
    # A total of 7 hosts will be created. Host 1 (using 0-based notation) will be
    # the target host we filter for at the end.  Host 6 will be completely different.
    # Hosts 0-5 will be mostly the same with these exceptions:
    #   hosts 1-5 will be in the same group (hosts 0 and 6 won't be in a group)
    #   host 2 will have a different value for the field that id_param_name represents
    #   host 3 will have a different provider_type
    #   host 4 will be stale (the rest will be fresh)
    #   hosts 0-4 will be in the filtered time range
    #
    # All provider ids and tags will be unique per host.

    hosts_data = [host_inventory.datagen.create_host_data_with_tags()]
    if id_param_name == "hostname_or_id":
        hosts_data[0]["display_name"] = generate_display_name()
    else:
        hosts_data[0][id_param_name] = generate_uuid()
    hosts_data[0]["provider_id"] = generate_uuid()
    hosts_data[0]["provider_type"] = "aws"

    for _ in range(5):
        hosts_data.append(dict(hosts_data[0]))
        hosts_data[-1]["provider_id"] = generate_uuid()
        hosts_data[-1]["tags"] = generate_tags()
    if id_param_name == "hostname_or_id":
        hosts_data[2]["fqdn"] = generate_display_name()
    else:
        hosts_data[2][id_param_name] = generate_uuid()
    hosts_data[3]["provider_type"] = "ibm"

    hosts_data.append(host_inventory.datagen.create_host_data_with_tags())
    hosts_data[-1]["provider_type"] = "gcp"
    hosts_data[-1]["provider_id"] = generate_uuid()

    hosts = host_inventory.kafka.create_hosts(hosts_data, field_to_match=HostWrapper.provider_id)

    # Assign hosts to group - all except hosts[0] and hosts[-1]
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[1:-1])

    # Step through all events to remove conflicts during later update
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
        deltas=(5, 3600, 7200),
        field_to_match=HostWrapper.provider_id,
    )
    updated_hosts = (
        hosts_in_state["fresh"][0:4] + hosts_in_state["stale"] + hosts_in_state["fresh"][4:]
    )

    # Guarantee that the updated_end host will have a later updated time than
    # the other hosts in the filtered range
    updated_end_host = host_inventory.kafka.create_hosts(
        [hosts_data[3]], field_to_match=HostWrapper.provider_id
    )[0]

    # Guarantee that the remaining hosts will be outside the filtered range
    host_inventory.kafka.create_hosts(hosts_data[5:], field_to_match=HostWrapper.provider_id)

    id_param = (
        {id_param_name: hosts_data[1][id_param_name]}
        if id_param_name != "hostname_or_id"
        else {id_param_name: hosts_data[1]["fqdn"]}
    )

    # Due to how we create a set of mixed-state hosts now, the stale host
    # (updated_hosts[4]) will have the earliest updated timestamp.  Thus, the
    # updated_start/updated_end params look a little strange, but they encompass
    # the first 5 hosts.
    response = host_inventory.apis.tags.get_tags_response(
        **id_param,
        provider_type=hosts_data[0]["provider_type"],
        staleness=["fresh"],
        updated_start=updated_hosts[4].updated,
        updated_end=updated_end_host.updated,
        group_name=[group_name],
    )
    assert response.count == len(updated_hosts[1].tags)
    assert_tags_found(updated_hosts[1].tags, response.results)
    not_wanted_tags = updated_hosts[0].tags + flatten(host.tags for host in updated_hosts[2:])
    assert_tags_not_found(not_wanted_tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_updated_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter tags by updated_start
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.updated if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(updated_start=time_filter_s)
    assert response.count >= len(host2.tags + host3.tags)
    assert_tags_found(host2.tags + host3.tags, response.results)
    assert_tags_not_found(host1.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_updated_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter tags by updated_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.updated if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(updated_end=time_filter_s)
    assert response.count >= len(host1.tags + host2.tags)
    assert_tags_found(host1.tags + host2.tags, response.results)
    assert_tags_not_found(host3.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_updated(
    host_inventory: ApplicationHostInventory,
    timestamp: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter tags by combined updated_start and updated_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_before = host_inventory.kafka.create_host(host_data=host_data)
    time_start = datetime.now()
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    time_end = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_after = host_inventory.kafka.create_host(host_data=host_data)

    time_start = hosts[0].updated if timestamp == "exact" else time_start
    time_end = hosts[-1].updated if timestamp == "exact" else time_end

    response = host_inventory.apis.tags.get_tags_response(
        updated_start=time_start, updated_end=time_end
    )
    wanted_tags = flatten(host.tags for host in hosts)
    assert response.count >= len(wanted_tags)
    assert_tags_found(wanted_tags, response.results)
    assert_tags_not_found(host_before.tags + host_after.tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_updated_both_same(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter tags by combined updated_start and updated_end - both same
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    response = host_inventory.apis.tags.get_tags_response(
        updated_start=hosts[1].updated, updated_end=hosts[1].updated
    )
    assert response.count >= len(hosts[1].tags)
    assert_tags_found(hosts[1].tags, response.results)
    assert_tags_not_found(hosts[0].tags + hosts[2].tags, response.results)


@pytest.mark.parametrize("timezone", ["+03:00", "-03:00"], ids=["plus", "minus"])
@pytest.mark.ephemeral
def test_get_tags_by_updated_different_timezone(
    host_inventory: ApplicationHostInventory,
    timezone: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Filter tags by updated with not-UTC timezone
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_before = host_inventory.kafka.create_host(host_data=host_data)
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_after = host_inventory.kafka.create_host(host_data=host_data)

    hours_delta = 3 if timezone[0] == "+" else -3
    time_start = (hosts[0].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )
    time_end = (hosts[-1].updated + timedelta(hours=hours_delta)).strftime(
        f"%Y-%m-%dT%H:%M:%S.%f{timezone}"
    )

    response = host_inventory.apis.tags.get_tags_response(
        updated_start=time_start, updated_end=time_end
    )
    wanted_tags = flatten(host.tags for host in hosts)
    assert response.count >= len(wanted_tags)
    assert_tags_found(wanted_tags, response.results)
    assert_tags_not_found(host_before.tags + host_after.tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_updated_not_created(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated
      assignee: fstavela
      importance: high
      title: Test that updated filters work by last updated, not created timestamp - tags
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data)
    time_start = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data)

    host_inventory.apis.hosts.patch_hosts(host2, display_name=f"{host2.display_name}-updated")
    time_end = datetime.now()
    host_inventory.apis.hosts.patch_hosts(host3, display_name=f"{host3.display_name}-updated")

    response = host_inventory.apis.tags.get_tags_response(
        updated_start=time_start, updated_end=time_end
    )
    assert response.count >= len(host2.tags)
    assert_tags_found(host2.tags, response.results)
    assert_tags_not_found(host1.tags + host3.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize("param", ["updated_start", "updated_end"])
@pytest.mark.parametrize("value", INCORRECT_DATETIMES)
def test_get_tags_by_updated_incorrect_format(
    host_inventory: ApplicationHostInventory, param: str, value: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Get tags with wrong format of updated_start and updated_end parameters
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_inventory.kafka.create_host(host_data)
    if isinstance(value, str):
        value = value.replace("'", "").replace('"', "").replace("\\", "")
    api_param = {param: value}
    error_value = f'\\"{value}\\"' if (isinstance(value, list) and len(value)) else f"'{value}'"
    with raises_apierror(400, f"{error_value} is not a 'date-time'"):
        host_inventory.apis.tags.get_tags_response(**api_param)


@pytest.mark.ephemeral
def test_get_tags_by_updated_start_after_end(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4356

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-updated, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Get tags with updated_start bigger than updated_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host = host_inventory.kafka.create_host(host_data)
    time_start = host.updated + timedelta(hours=1)
    time_end = host.updated - timedelta(hours=1)
    with raises_apierror(400, "updated_start cannot be after updated_end."):
        host_inventory.apis.tags.get_tags_response(updated_start=time_start, updated_end=time_end)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in_start(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter tags by last_check_in_start
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_str = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(last_check_in_start=time_filter_str)
    assert response.count >= len(host2.tags + host3.tags)
    assert_tags_found(host2.tags + host3.tags, response.results)
    assert_tags_not_found(host1.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "time_format",
    ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S.%fZ"],
    ids=["without-timezone", "with-timezone-hours", "with-timezone-char"],
)
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in_end(
    host_inventory: ApplicationHostInventory, time_format: str, timestamp: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter tags by last_check_in_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host1 = host_inventory.kafka.create_host(host_data=host_data)
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host2 = host_inventory.kafka.create_host(host_data=host_data)
    time_filter = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host3 = host_inventory.kafka.create_host(host_data=host_data)

    time_filter = host2.last_check_in if timestamp == "exact" else time_filter
    time_filter_s = time_filter.strftime(time_format)

    response = host_inventory.apis.tags.get_tags_response(last_check_in_end=time_filter_s)
    assert response.count >= len(host1.tags + host2.tags)
    assert_tags_found(host1.tags + host2.tags, response.results)
    assert_tags_not_found(host3.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize("timestamp", ["exact", "not-exact"])
def test_get_tags_by_last_check_in(
    host_inventory: ApplicationHostInventory,
    timestamp: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-21076

    metadata:
      requirements: inv-tags-get-list, inv-hosts-filter-by-last_check_in
      assignee: aprice
      importance: high
      title: Filter tags by combined last_check_in_start and last_check_in_end
    """
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_before = host_inventory.kafka.create_host(host_data=host_data)
    time_start = datetime.now()
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    time_end = datetime.now()
    host_data = host_inventory.datagen.create_host_data_with_tags()
    host_after = host_inventory.kafka.create_host(host_data=host_data)

    time_start = hosts[0].last_check_in if timestamp == "exact" else time_start
    time_end = hosts[-1].last_check_in if timestamp == "exact" else time_end

    response = host_inventory.apis.tags.get_tags_response(
        last_check_in_start=time_start, last_check_in_end=time_end
    )
    wanted_tags = flatten(host.tags for host in hosts)
    assert response.count >= len(wanted_tags)
    assert_tags_found(wanted_tags, response.results)
    assert_tags_not_found(host_before.tags + host_after.tags, response.results)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "case_insensitive", [False, True], ids=["case sensitive", "case insensitive"]
)
def test_get_tags_by_group_name(host_inventory: ApplicationHostInventory, case_insensitive: bool):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter tags by group_name
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    filtered_name = group_name.upper() if case_insensitive else group_name

    response = host_inventory.apis.tags.get_tags_response(group_name=[filtered_name])
    assert response.count == len(hosts[0].tags)
    assert_tags_found(hosts[0].tags, response.results)
    assert_tags_not_found(hosts[1].tags + hosts[2].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_id
        assignee: maarif
        importance: high
        title: Filter tags by group_id
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1])

    response = host_inventory.apis.tags.get_tags_response(group_id=[group.id])
    assert response.count == len(hosts[0].tags)
    assert_tags_found(hosts[0].tags, response.results)
    assert_tags_not_found(hosts[1].tags + hosts[2].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_with_group_name_and_group_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-21927

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name, \
            inv-hosts-filter-by-group_id, inv-api-validation
        assignee: maarif
        importance: high
        negative: true
        title: Verify 400 error when both group_name and group_id filters are used \
            together for tags
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name)

    with raises_apierror(400, "Cannot use both 'group_name' and 'group_id' filters together"):
        host_inventory.apis.tags.get_tags_response(group_name=[group_name], group_id=[group.id])


@pytest.mark.ephemeral
def test_get_tags_by_group_name_empty(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5138

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter tags by empty group_name - get tags of ungrouped hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(2)
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[0])

    response = host_inventory.apis.tags.get_tags_response(group_name=[""])
    assert response.count >= len(hosts[1].tags)
    assert_tags_found(hosts[1].tags, response.results)
    assert_tags_not_found(hosts[0].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_group_name_multiple_groups(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5108

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter tags by multiple group_name values
    """
    hosts = host_inventory.kafka.create_random_hosts(5)
    group_name1 = generate_display_name()
    group_name2 = generate_display_name()
    host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    host_inventory.apis.groups.create_group(group_name2, hosts=hosts[1:3])
    host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[3])

    correct_tags = hosts[0].tags + hosts[1].tags + hosts[2].tags
    response = host_inventory.apis.tags.get_tags_response(group_name=[group_name1, group_name2])
    assert response.count == len(correct_tags)
    assert_tags_found(correct_tags, response.results)
    assert_tags_not_found(hosts[3].tags + hosts[4].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_group_name_multiple_hosts_in_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name
        assignee: fstavela
        importance: high
        title: Filter tags by group_name, if the group has multiple hosts
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data_with_tags(3)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)
    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    response = host_inventory.apis.tags.get_tags_response(group_name=[group_name])
    assert response.count == len(hosts[0].tags + hosts[1].tags)
    assert_tags_found(hosts[0].tags + hosts[1].tags, response.results)
    assert_tags_not_found(hosts[2].tags, response.results)


@pytest.mark.ephemeral
def test_get_tags_by_group_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3826

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-group_name, inv-account-integrity
        assignee: fstavela
        importance: high
        title: Test that I can't get tags by group_name from different account
    """
    host_data_primary = host_inventory.datagen.create_host_data_with_tags()
    host_data_secondary = host_inventory_secondary.datagen.create_host_data_with_tags()

    host_primary = host_inventory.kafka.create_host(host_data_primary)
    host_secondary = host_inventory_secondary.kafka.create_host(host_data_secondary)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=host_primary)
    host_inventory_secondary.apis.groups.create_group(group_name, hosts=host_secondary)

    response = host_inventory.apis.tags.get_tags_response(group_name=[group_name])
    assert response.count == len(host_primary.tags)
    assert_tags_found(host_primary.tags, response.results)
    assert_tags_not_found(host_secondary.tags, response.results)

    response = host_inventory_secondary.apis.tags.get_tags_response(group_name=[group_name])
    assert response.count == len(host_secondary.tags)
    assert_tags_found(host_secondary.tags, response.results)
    assert_tags_not_found(host_primary.tags, response.results)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "system_type",
    [
        pytest.param(values, id=", ".join(values))
        for n in range(len(_CORRECT_SYSTEM_TYPE_VALUES))
        for values in combinations(_CORRECT_SYSTEM_TYPE_VALUES, n + 1)
    ],
)
def test_get_tags_by_system_type(
    host_inventory: ApplicationHostInventory,
    setup_hosts_for_system_type_filtering: dict[str, list[HostWrapper]],
    system_type: list[str],
):
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-19125

    metadata:
        requirements: inv-tags-get-list, inv-hosts-filter-by-system_type
        assignee: zabikeno
        importance: high
        title: Inventory: filter tags by system_type
    """
    prepared_hosts = deepcopy(setup_hosts_for_system_type_filtering)
    expected_hosts = flatten(prepared_hosts.pop(item) for item in system_type)
    expected_tags = flatten(host.tags for host in expected_hosts)

    response = host_inventory.apis.tags.get_tags_response(system_type=system_type)
    assert len(response.results) >= len(expected_tags)
    assert_tags_found(expected_tags, response.results)

    not_expected_hosts = flatten(hosts for hosts in prepared_hosts.values())
    not_expected_tags = flatten(host.tags for host in not_expected_hosts)
    assert_tags_not_found(not_expected_tags, response.results)
