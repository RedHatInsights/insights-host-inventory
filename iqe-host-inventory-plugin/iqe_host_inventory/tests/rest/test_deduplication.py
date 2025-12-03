# mypy: disallow-untyped-defs
"""
More information about deduplication can be found in the following document:
https://docs.google.com/document/d/1OOyDaOU9XFKQJHLUbOhlSRsW5u3zgFgwaG7RmaH8bFU/edit?tab=t.0#heading=h.fuf1c0g8fvay
"""

from __future__ import annotations

import logging
from copy import deepcopy
from time import sleep

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.datagen_utils import Field
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_host_field_value
from iqe_host_inventory.utils.datagen_utils import generate_macs
from iqe_host_inventory.utils.datagen_utils import generate_provider_type
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_canonical_facts
from iqe_host_inventory.utils.datagen_utils import get_canonical_not_id_facts
from iqe_host_inventory.utils.datagen_utils import get_host_field_by_name
from iqe_host_inventory.utils.datagen_utils import get_id_facts
from iqe_host_inventory.utils.datagen_utils import get_immutable_facts
from iqe_host_inventory.utils.datagen_utils import get_mutable_id_facts
from iqe_host_inventory.utils.staleness_utils import create_hosts_in_state

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def ids_by_name(field: Field | str) -> str:
    if isinstance(field, str):
        return field
    return field.name


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_id_facts(), ids=ids_by_name)
def test_dedup_one_matching_id_fact_other_not_matching(
    host_inventory: ApplicationHostInventory, tested_field: Field
) -> None:
    """
    Test that sending a payload with only one ID fact matching the already existing host
    and other ID facts being different (when immutable facts are not included in the message)
    updates the already existing host, and a new host will not be created.

    https://issues.redhat.com/browse/RHINENG-9850

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - one ID fact matching the existing host updates the host
    """
    host_data = host_inventory.datagen.create_host_data()
    ansible_host_field = get_host_field_by_name("ansible_host")
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Remove immutable facts so they don't influence the deduplication
    for field in get_immutable_facts():
        host_data.pop(field.name, None)
    # Remove provider_type when provider_id gets removed
    host_data.pop("provider_type", None)

    # Add all ID facts (except immutable)
    for field in get_mutable_id_facts():
        host_data[field.name] = generate_host_field_value(field)
    host_data[tested_field.name] = generate_host_field_value(tested_field)
    # provider_type has to be provided when provider_id is present
    if tested_field.name == "provider_id":
        host_data["provider_type"] = generate_provider_type()

    host = host_inventory.kafka.create_host(host_data=host_data)

    # Change all canonical and elevated facts, except of the tested field
    for field in get_mutable_id_facts():
        if field != tested_field:
            host_data[field.name] = generate_host_field_value(field)
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Check that the host was updated
    updated_host = host_inventory.kafka.create_host(host_data=host_data)
    assert updated_host.id == host.id
    response_host = host_inventory.apis.hosts.wait_for_updated(
        host, ansible_host=host_data["ansible_host"]
    )[0]
    for field in get_mutable_id_facts():
        assert getattr(response_host, field.name) == host_data[field.name]

    # Check that no new host was created
    response = host_inventory.apis.hosts.get_hosts(display_name=host_data["display_name"])
    assert len(response) == 1


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_id_facts(), ids=ids_by_name)
@pytest.mark.parametrize("original_has_all", [True, False])
def test_dedup_one_id_fact_not_matching(
    host_inventory: ApplicationHostInventory, tested_field: Field, original_has_all: bool
) -> None:
    """
    Test that sending a payload with one ID fact that's different from the existing host
    and other ID facts are not provided creates a new host, even if all other (not ID)
    facts are the same.

    https://issues.redhat.com/browse/RHINENG-9850

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - one different ID fact creates a new host
    """
    host_data = host_inventory.datagen.create_host_data()
    ansible_host_field = get_host_field_by_name("ansible_host")
    orig_ansible_host = generate_host_field_value(ansible_host_field)
    host_data["ansible_host"] = orig_ansible_host

    # Let the host have all the canonical (not ID) facts
    for field in get_canonical_not_id_facts():
        host_data[field.name] = generate_host_field_value(field)

    if original_has_all:
        # Let the original host have all the ID facts
        for field in get_id_facts():
            host_data[field.name] = generate_host_field_value(field)
        host_data["provider_type"] = generate_provider_type()
    else:
        # Let the original host have only the tested ID fact
        for field in get_id_facts():
            host_data.pop(field.name, None)
        host_data[tested_field.name] = generate_host_field_value(tested_field)
        if tested_field.name == "provider_id":
            host_data["provider_type"] = generate_provider_type()
        else:
            host_data.pop("provider_type", None)

    host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )

    # Remove all ID facts from the second payload
    for field in get_id_facts():
        host_data.pop(field.name, None)
    if tested_field.name != "provider_id":
        host_data.pop("provider_type", None)

    # Change the tested ID fact, keep the other canonical facts the same
    host_data[tested_field.name] = generate_host_field_value(tested_field)
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Check that a new host was created
    new_host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )
    assert new_host.id != host.id
    host_inventory.apis.hosts.wait_for_updated(new_host, ansible_host=host_data["ansible_host"])
    host_inventory.apis.hosts.verify_not_updated(host, ansible_host=orig_ansible_host)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", [*get_id_facts(), "all"], ids=ids_by_name)
def test_dedup_all_id_facts_not_matching(
    host_inventory: ApplicationHostInventory, tested_field: Field | str
) -> None:
    """
    Test that sending a payload with all ID facts being different from the existing host
    creates a new host, even if all canonical (not ID) facts are the same.

    https://issues.redhat.com/browse/RHINENG-9850

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - all different ID facts create a new host
    """
    host_data = host_inventory.datagen.create_host_data()
    ansible_host_field = get_host_field_by_name("ansible_host")
    orig_ansible_host = generate_host_field_value(ansible_host_field)
    host_data["ansible_host"] = orig_ansible_host

    # Let the host have all canonical (not ID) facts
    for field in get_canonical_not_id_facts():
        host_data[field.name] = generate_host_field_value(field)

    if isinstance(tested_field, str):  # tested_field == "all"
        # Let the original host have all ID facts
        for field in get_id_facts():
            host_data[field.name] = generate_host_field_value(field)
        host_data["provider_type"] = generate_provider_type()
    else:
        # Let the original host have only the tested ID fact
        for field in get_id_facts():
            host_data.pop(field.name, None)
        host_data[tested_field.name] = generate_host_field_value(tested_field)
        if tested_field.name == "provider_id":
            host_data["provider_type"] = generate_provider_type()
        else:
            host_data.pop("provider_type", None)

    host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )

    # Change all ID facts, keep the other canonical facts the same
    for field in get_id_facts():
        host_data[field.name] = generate_host_field_value(field)
    if "provider_type" not in host_data:
        host_data["provider_type"] = generate_provider_type()
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Check that a new host was created
    new_host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )
    assert new_host.id != host.id
    host_inventory.apis.hosts.wait_for_updated(new_host, ansible_host=host_data["ansible_host"])
    host_inventory.apis.hosts.verify_not_updated(host, ansible_host=orig_ansible_host)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_id_facts(), ids=ids_by_name)
def test_dedup_id_facts_priority(
    host_inventory: ApplicationHostInventory, tested_field: Field
) -> None:
    """
    Test that sending a payload with the higher priority ID fact matching Host 2 and all the
    lower priority ID facts + other canonical facts matching Host 1 updates Host 2.

    https://issues.redhat.com/browse/RHINENG-9850

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - ID facts priority
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(2)
    ansible_host_field = get_host_field_by_name("ansible_host")
    for host_data in hosts_data:
        host_data["ansible_host"] = generate_host_field_value(ansible_host_field)
        # Add all ID facts
        for field in get_id_facts():
            host_data[field.name] = generate_host_field_value(field)
        host_data["provider_type"] = generate_provider_type()

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    # Let the new host have all lower priority facts from the first host
    new_host_data = deepcopy(hosts_data[0])

    # Remove the higher priority ID facts and immutable facts from the new host
    for field in get_id_facts():
        # This should never happen, but let's make mypy happy
        assert field.dedup_order is not None, "Incorrect configuration, check datagen_utils.py"
        assert tested_field.dedup_order is not None, (
            "Incorrect configuration, check datagen_utils.py"
        )
        if field.dedup_order < tested_field.dedup_order or field.is_immutable:
            new_host_data.pop(field.name, None)
    new_host_data.pop("provider_type", None)

    # Let the new host have the tested field (now with the highest prio) from the second host
    new_host_data[tested_field.name] = hosts_data[1][tested_field.name]
    if tested_field.name == "provider_id":
        new_host_data["provider_type"] = hosts_data[1]["provider_type"]

    # Check that the host with matching tested field was updated
    new_host_data["ansible_host"] = generate_host_field_value(ansible_host_field)
    updated_host = host_inventory.kafka.create_host(
        host_data=new_host_data, field_to_match=HostWrapper.ansible_host
    )
    assert updated_host.id == hosts[1].id
    host_inventory.apis.hosts.wait_for_updated(
        hosts[1], ansible_host=new_host_data["ansible_host"]
    )

    # Check that the other host was not updated
    host_inventory.apis.hosts.verify_not_updated(hosts[0], ansible_host=hosts[0].ansible_host)

    # Check that no new host was created
    response = host_inventory.apis.hosts.get_hosts(display_name=new_host_data["display_name"])
    assert len(response) == 2


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_immutable_facts(), ids=ids_by_name)
def test_dedup_immutable_facts_not_matching(
    host_inventory: ApplicationHostInventory, tested_field: Field
) -> None:
    """
    Test that sending a payload with one immutable fact that's different from the existing host
    creates a new host, even if all other immutable and ID facts are the same.

    https://issues.redhat.com/browse/RHINENG-9850
    https://issues.redhat.com/browse/RHINENG-11657

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - one different immutable fact creates a new host
    """
    host_data = host_inventory.datagen.create_host_data()
    ansible_host_field = get_host_field_by_name("ansible_host")
    orig_ansible_host = generate_host_field_value(ansible_host_field)
    host_data["ansible_host"] = orig_ansible_host

    # Let the host have all ID facts
    for field in get_id_facts():
        host_data[field.name] = generate_host_field_value(field)
    host_data["provider_type"] = generate_provider_type()
    host_data[tested_field.name] = generate_host_field_value(tested_field)

    host = host_inventory.kafka.create_host(host_data=host_data)

    # Change the tested immutable fact, keep the other facts the same
    host_data[tested_field.name] = generate_host_field_value(tested_field)
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Check that a new host was created
    new_host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )
    assert new_host.id != host.id
    host_inventory.apis.hosts.wait_for_updated(new_host, ansible_host=host_data["ansible_host"])
    host_inventory.apis.hosts.verify_not_updated(host, ansible_host=orig_ansible_host)


# Although this test is non-applicable at the moment, leaving it in the code
# base in case we add another field to the immutable facts in the future.
@pytest.mark.ephemeral
@pytest.mark.skip("We currently have only one immutable fact - provider_id")
def test_dedup_immutable_facts_each_matching_different_host(
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test that sending a payload with multiple immutable facts and each of them matching a different
    host creates a new host.

    https://issues.redhat.com/browse/RHINENG-12053
    https://issues.redhat.com/browse/RHINENG-11657

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-deduplication
        title: Test dedup - multiple immutable facts matching multiple hosts creates a new host
    """
    ansible_host_field = get_host_field_by_name("ansible_host")

    hosts_data = host_inventory.datagen.create_n_hosts_data(len(get_immutable_facts()))
    for host_data in hosts_data:
        host_data["ansible_host"] = generate_host_field_value(ansible_host_field)
        # Let the hosts have all ID facts
        for field in get_id_facts():
            host_data[field.name] = generate_host_field_value(field)
        host_data["provider_type"] = generate_provider_type()

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    # Create a new host, which will match one immutable fact from each previously created host
    host_data = deepcopy(hosts_data[0])
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)
    for i, field in enumerate(get_immutable_facts()):
        host_data[field.name] = hosts_data[i][field.name]
        if field.name == "provider_id":
            host_data["provider_type"] = hosts_data[i]["provider_type"]

    # Check that a new host will be created
    new_host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )
    assert new_host.id not in {host.id for host in hosts}
    host_inventory.apis.hosts.wait_for_updated(new_host, ansible_host=host_data["ansible_host"])
    for host in hosts:
        host_inventory.apis.hosts.verify_not_updated(host, ansible_host=host.ansible_host)


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_id_facts(), ids=ids_by_name)
def test_dedup_add_ID_fact(
    host_inventory: ApplicationHostInventory,
    tested_field: Field,
) -> None:
    """
    Test adding a new ID fact, but leaving other the same
    updates the existing host and new fact is added to the host

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - adding new ID fact to host
    """
    host_data = host_inventory.datagen.create_host_data()
    ansible_host_field = get_host_field_by_name("ansible_host")
    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)

    # Remove immutable facts so they don't influence the deduplication
    for field in get_immutable_facts():
        host_data.pop(field.name, None)
    # Remove provider_type when provider_id gets removed
    host_data.pop("provider_type", None)

    # Add all ID facts (except immutable)
    for field in get_mutable_id_facts():
        host_data[field.name] = generate_host_field_value(field)

    host_data.pop(tested_field.name, None)

    host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )

    host_data["ansible_host"] = generate_host_field_value(ansible_host_field)
    host_data[tested_field.name] = generate_host_field_value(tested_field)
    # provider_type has to be provided when provider_id is present
    if tested_field.name == "provider_id":
        host_data["provider_type"] = generate_provider_type()

    # Check that the host was updated
    updated_host = host_inventory.kafka.create_host(
        host_data=host_data, field_to_match=HostWrapper.ansible_host
    )
    assert updated_host.id == host.id
    response_host = host_inventory.apis.hosts.wait_for_updated(
        host, ansible_host=host_data["ansible_host"]
    )[0]
    assert getattr(response_host, tested_field.name) == host_data[tested_field.name]

    # Check that no new host was created
    response = host_inventory.apis.hosts.get_hosts(display_name=host_data["display_name"])
    assert len(response) == 1


def host_diff(host: HostWrapper | dict, updated_host: HostWrapper | dict) -> str:
    if not isinstance(host, dict):
        host = host.data()
    if not isinstance(updated_host, dict):
        updated_host = updated_host.data()
    diff = {
        field: (v, updated_host[field])
        for field, v in host.items()
        if field != "updated" and v != updated_host[field] and not isinstance(v, dict)
    }
    return "\n".join(f"{field}: {old} != {new}" for field, (old, new) in diff.items())


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.usefixtures("hbi_staleness_cleanup")
def test_dedup_culled_host(host_inventory: ApplicationHostInventory) -> None:
    """
    Test creating host with the same payload as culled host creates new host

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication, inv-staleness-hosts
        title: Test deduplication - culled host
    """
    host_data = host_inventory.datagen.create_host_data()
    for field in get_canonical_facts():
        host_data[field.name] = generate_host_field_value(field)
    host_data["provider_type"] = generate_provider_type()
    host = create_hosts_in_state(
        host_inventory,
        [host_data],
        host_state="culling",
        deltas=(5, 6, 7),
    )[0]

    host_data["ansible_host"] = generate_host_field_value(get_host_field_by_name("ansible_host"))
    second_host = host_inventory.kafka.create_host(host_data=host_data)

    assert second_host.id != host.id
    host_inventory.apis.hosts.wait_for_updated(
        second_host,
        ansible_host=host_data["ansible_host"],
    )

    # Check that the first host didn't get updated and is still culled
    response = host_inventory.apis.hosts.get_hosts_by_id(host)
    assert len(response) == 0


@pytest.mark.smoke
@pytest.mark.ephemeral
@pytest.mark.parametrize("tested_field", get_id_facts(), ids=ids_by_name)
def test_dedup_of_similar_hosts(
    host_inventory: ApplicationHostInventory,
    tested_field: Field,
) -> None:
    """
    Test that when I send an MQ message with canonical facts of one host
    and ID facts of another host, the host with matching elevated
    facts gets updated.

    https://mailman-int.corp.redhat.com/archives/insights-prio/2021-September/msg00018.html
    https://ansible.slack.com/archives/CQFKM031T/p1631105457072800
    https://bugzilla.redhat.com/show_bug.cgi?id=2002399

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - two similar hosts
    """
    display_name = generate_display_name()
    hosts_data = [host_inventory.datagen.create_host_data() for _ in range(2)]

    for host_data in hosts_data:
        for fact in get_id_facts():
            host_data.pop(fact.name, None)

        host_data[tested_field.name] = generate_host_field_value(tested_field)
        if tested_field.name == "provider_id":
            host_data["provider_type"] = generate_provider_type()
        else:
            host_data.pop("provider_type", None)
        host_data["display_name"] = display_name

    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.ansible_host
    )
    response = host_inventory.apis.hosts.get_hosts_response(display_name=display_name)
    assert response.count == 2

    # Assign all facts from the first host, only the tested elevated fact from the second host
    new_host_data = dict(hosts_data[0])
    new_host_data[tested_field.name] = hosts_data[1][tested_field.name]
    # Both, provider_id and provider_type must match
    if tested_field.name == "provider_id":
        new_host_data["provider_type"] = hosts_data[1]["provider_type"]

    updated_host = host_inventory.kafka.create_host(
        new_host_data,
        field_to_match=HostWrapper.ansible_host,
    )
    assert updated_host.id == hosts[1].id
    response = host_inventory.apis.hosts.get_hosts_response(display_name=display_name)
    assert response.count == 2


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_dedup_of_similar_host_with_different_org_id(
    hbi_secondary_org_id: str,
    host_inventory_secondary: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    Test creating host with matching facts and different org_id and account
    will not update the existing host

    metadata:
        assignee: zabikeno
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - two similar hosts with different org_id
    """
    ansible_host = get_host_field_by_name("ansible_host")
    # create first host data
    host_data = host_inventory.datagen.create_complete_host_data()
    # create the same host data with different org_id
    host_data_secondary = {
        **host_data,
        "org_id": hbi_secondary_org_id,
    }

    # create hosts with matching host_data and different org_id
    host = host_inventory.kafka.create_host(host_data)
    host_secondary = host_inventory_secondary.kafka.create_host(host_data_secondary)
    assert host_secondary.id != host.id

    # check if the first host didn't update while creating a new host with different org_id
    host_inventory.apis.hosts.verify_not_updated(host, org_id=host_data["org_id"])

    # try to update a host and check if the second host is not updated with the new ansible name
    host_data["ansible_host"] = generate_host_field_value(ansible_host)
    updated_host = host_inventory.kafka.create_host(host_data)
    host_inventory.apis.hosts.wait_for_updated(
        updated_host, ansible_host=host_data["ansible_host"]
    )
    host_inventory_secondary.apis.hosts.verify_not_updated(
        host_secondary, ansible_host=host_data_secondary["ansible_host"]
    )


@pytest.mark.smoke
@pytest.mark.ephemeral
def test_dedup_provider_fields_combination(host_inventory: ApplicationHostInventory) -> None:
    """
    Test that provider_id and provider_type combination act as a single ID fact,
    and both of them must match for the host to be considered to be the same host.

    metadata:
        assignee: fstavela
        importance: critical
        requirements: inv-host-deduplication
        title: Test deduplication - provider_id + provider_type combination must match
    """

    original_provider_type = "aws"
    new_provider_type = "ibm"

    host_data = host_inventory.datagen.create_host_data()
    for field in get_canonical_facts():
        host_data[field.name] = generate_host_field_value(field)
    host_data["provider_type"] = original_provider_type

    original_provider_id = host_data["provider_id"]
    original_host = host_inventory.kafka.create_host(host_data)

    # Keep the same provider_id but change provider_type
    host_data["provider_type"] = new_provider_type
    new_host1 = host_inventory.kafka.create_host(host_data)
    assert new_host1.id != original_host.id

    response_hosts = host_inventory.apis.hosts.get_hosts(display_name=host_data["display_name"])
    assert len(response_hosts) == 2
    host_inventory.apis.hosts.verify_not_updated(
        original_host, provider_type=original_provider_type
    )

    # Keep the same provider_type but change provider_id
    host_data["provider_type"] = original_provider_type
    host_data["provider_id"] = generate_uuid()
    new_host2 = host_inventory.kafka.create_host(host_data)
    assert new_host2.id != original_host.id
    assert new_host2.id != new_host1.id

    response_hosts = host_inventory.apis.hosts.get_hosts(display_name=host_data["display_name"])
    assert len(response_hosts) == 3
    host_inventory.apis.hosts.verify_not_updated(original_host, provider_id=original_provider_id)


@pytest.mark.ephemeral
def test_dedup_provider_issue(host_inventory: ApplicationHostInventory) -> None:
    """
    Test that we can't have 2 hosts with the same provider_id + provider_type
    This test is reproducing this issue: https://issues.redhat.com/browse/RHINENG-9012

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-deduplication
        title: Test deduplication: RHINENG-9012
    """
    # Create the original host with all elevated canonical facts
    subman_id1 = generate_uuid()
    insights_id = generate_uuid()
    provider_id = generate_uuid()
    provider_type = "aws"
    reporter1 = "rhsm-system-profile-bridge"

    host_data = host_inventory.datagen.create_host_data()
    host_data["subscription_manager_id"] = subman_id1
    host_data["insights_id"] = insights_id
    host_data["provider_id"] = provider_id
    host_data["provider_type"] = provider_type
    host_data["reporter"] = reporter1

    original_host = host_inventory.kafka.create_host(host_data)

    # Create the second host (duplicate), without provider fields, insights_id and mac_addresses
    # and with different subscription_manager_id
    subman_id2 = generate_uuid()
    reporter2 = "cloud-connector"

    host_data2 = deepcopy(host_data)
    host_data2.pop("insights_id")
    host_data2.pop("provider_id")
    host_data2.pop("provider_type")
    host_data2.pop("mac_addresses")
    host_data2["subscription_manager_id"] = subman_id2
    host_data2["reporter"] = reporter2

    second_host = host_inventory.kafka.create_host(
        host_data2,
        field_to_match=HostWrapper.subscription_manager_id,
    )
    assert second_host.id != original_host.id

    # Send a message that should update the original host, but instead updates the second host,
    # which causes that we will have 2 hosts with the same provider fields
    host_data3 = deepcopy(host_data2)
    host_data3["provider_id"] = provider_id
    host_data3["provider_type"] = provider_type
    host_data3["reporter"] = reporter1

    updated_host = host_inventory.kafka.create_host(
        host_data3, field_to_match=HostWrapper.subscription_manager_id
    )
    assert updated_host.id == original_host.id

    sleep(3)

    response_hosts = host_inventory.apis.hosts.get_hosts(provider_id=provider_id)
    assert len(response_hosts) == 1


@pytest.mark.ephemeral
def test_dedup_same_mac_address_issue(host_inventory: ApplicationHostInventory) -> None:
    """
    Test that when 2 hosts share the same MAC address, we will not end up with duplicates in HBI.
    This test reproduces this issue: https://issues.redhat.com/browse/RHINENG-15736

    We have 2 hosts. Both of them have different insights_id and subscription_manager_id, but they
    share the same MAC address. One of them has one more MAC address. So we have:
    - System1: insights_id_1, subman_id_1, [mac1, mac2]
    - System2: insights_id_2, subman_id_2, [mac1]

    The workflow of the test is as follows:
    - System1 makes an upload - a new host will be created in HBI (host1)
    - System2 makes an upload - a new host should be created, but the first one is updated instead,
        because it matches on a MAC address ("sub list"). So we now have host1 with:
        insights_id_2, subman_id_2, [mac1]
    - System1 makes an upload - a new host will be created in HBI (host2), because it doesn't match
        the existing host (MAC addresses are a "super list", which isn't considered a match).
        So now we have host2 with: insights_id_1, subman_id_1, [mac1, mac2]
    - System2 makes an upload - it updates host2, because it matches on a MAC address (sublist).
        Even though the MAC addresses match on both hosts, host2 is updated because it is higher in
        the Inventory table (most recently updated) and once Inventory finds a match, it doesn't
        look for more hosts. So now we have:
        - host1: insights_id_2, subman_id_2, [mac1]
        - host2: insights_id_2, subman_id_2, [mac1]
    - System1 makes an upload - a new host will be created in HBI (host3)
    - It goes on like this and every day we have a new duplicate in the Inventory table.

    https://issues.redhat.com/browse/RHINENG-16019

    metadata:
        assignee: fstavela
        importance: high
        requirements: inv-host-deduplication
        title: Test deduplication: RHINENG-15736
    """
    display_name = generate_display_name()
    host_data1 = host_inventory.datagen.create_host_data()
    host_data1["insights_id"] = generate_uuid()
    host_data1["subscription_manager_id"] = generate_uuid()
    host_data1["mac_addresses"] = generate_macs(2)
    host_data1["display_name"] = display_name

    host_data2 = host_inventory.datagen.create_host_data()
    host_data2["insights_id"] = generate_uuid()
    host_data2["subscription_manager_id"] = generate_uuid()
    host_data2["mac_addresses"] = [host_data1["mac_addresses"][0]]
    host_data2["display_name"] = display_name

    host1 = host_inventory.kafka.create_host(host_data1)
    host2 = host_inventory.kafka.create_host(host_data2)
    assert host1.id != host2.id

    # Update a random field just to be able to wait until the host is updated
    host_data1["ansible_host"] = generate_display_name()
    updated_host1 = host_inventory.kafka.create_host(host_data1)
    assert updated_host1.id == host1.id
    host_inventory.apis.hosts.wait_for_updated(host1, ansible_host=host_data1["ansible_host"])

    # Same here
    host_data2["ansible_host"] = generate_display_name()
    updated_host2 = host_inventory.kafka.create_host(host_data2)
    assert updated_host2.id == host2.id
    host_inventory.apis.hosts.wait_for_updated(host2, ansible_host=host_data2["ansible_host"])

    response_hosts = host_inventory.apis.hosts.get_hosts(display_name=display_name)
    assert len(response_hosts) == 2
