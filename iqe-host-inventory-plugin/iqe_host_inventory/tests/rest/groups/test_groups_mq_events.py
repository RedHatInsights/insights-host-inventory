from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.api_utils import ungrouped_host_groups
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import check_api_update_events
from iqe_host_inventory.utils.kafka_utils import check_host_timestamps
from iqe_host_inventory_api import GroupOut
from iqe_host_inventory_api import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def group_to_mq_dict(group: GroupOut | GroupOutWithHostCount) -> dict[str, str]:
    return {"id": group.id, "name": group.name, "ungrouped": group.ungrouped}


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("how_many", [1, 3])
def test_groups_mq_events_produce_create_group(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when a new group is created
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(
        group_name, hosts=hosts, wait_for_created=False
    )

    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == how_many
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_create_groups_same_host(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating groups with same hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name1 = generate_display_name()
    host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, [hosts[0].insights_id]
    )

    group_name2 = generate_display_name()
    with raises_apierror(400):
        host_inventory.apis.groups.create_group(group_name2, hosts=hosts, wait_for_created=False)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_create_group_without_name(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating group without name
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    data = {"host_ids": [host.id for host in hosts]}
    with raises_apierror(400):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "bad_id",
    [generate_uuid(), generate_string_of_length(36, use_punctuation=False)],
    ids=["uuid", "random string"],
)
def test_groups_mq_events_not_produce_create_group_bad_hosts(
    host_inventory: ApplicationHostInventory,
    bad_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating group with bad host IDs
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name = generate_display_name()
    hosts_ids = [hosts[0].id, bad_id, hosts[1].id]
    with raises_apierror(400):
        host_inventory.apis.groups.create_group(
            group_name, hosts=hosts_ids, wait_for_created=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["account", "random123"])
def test_groups_mq_events_not_produce_create_group_unknown_field(
    host_inventory: ApplicationHostInventory,
    field: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating group with unknown field
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    data = {
        "name": generate_display_name(),
        "host_ids": [host.id for host in hosts],
        field: "123456",
    }
    with raises_apierror(400):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
def test_groups_mq_events_produce_patch_add_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are added to group via PATCH
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, hosts=hosts, wait_for_updated=False
    )
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 3
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("remove_all", [True, False], ids=["all", "part"])
def test_groups_mq_events_produce_patch_remove_hosts(
    host_inventory: ApplicationHostInventory,
    remove_all: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are removed from group via PATCH
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    updated_hosts = [] if remove_all else hosts[:2]
    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, hosts=updated_hosts, wait_for_updated=False
    )
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 3
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        if not remove_all and msg.host.id != hosts[2].id:
            original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_produce_patch_add_and_remove_hosts(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are added and removed from group via PATCH
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, hosts=hosts[1:], wait_for_updated=False
    )
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 3
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        if msg.host.id != hosts[0].id:
            original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_produce_patch_change_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are changed in group via PATCH
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, hosts=hosts[2:], wait_for_updated=False
    )
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 4
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        if msg.host.id in (hosts[2].id, hosts[3].id):
            original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_produce_patch_change_name(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when group's name is changed via PATCH
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, name=generate_display_name(), wait_for_updated=False
    )
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 3
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("remove_hosts", [True, False], ids=["remove hosts", "update hosts"])
def test_groups_mq_events_produce_patch_change_name_and_hosts(
    host_inventory: ApplicationHostInventory,
    remove_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts and name are changed in group via PATCH
    """
    n_hosts = 2 if remove_hosts else 3
    hosts = host_inventory.kafka.create_random_hosts(n_hosts)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    updated_hosts = [] if remove_hosts else hosts[1:]
    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.patch_group(
        group, name=generate_display_name(), hosts=updated_hosts, wait_for_updated=False
    )

    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == n_hosts
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    group_dict = group_to_mq_dict(updated_group)
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        if not remove_hosts and msg.host.id != hosts[0].id:
            original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_patch_groups_same_host(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when patching groups with same hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[3])
    host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, [hosts[3].insights_id]
    )

    group = host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[:2])
    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    with raises_apierror(400):
        host_inventory.apis.groups.patch_group(group, hosts=hosts[1:], wait_for_updated=False)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "bad_id",
    [generate_uuid(), generate_string_of_length(36, use_punctuation=False)],
    ids=["uuid", "random string"],
)
def test_groups_mq_events_not_produce_patch_group_bad_hosts(
    host_inventory: ApplicationHostInventory,
    bad_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when patching group with bad host IDs
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    hosts_ids = [hosts[1].id, bad_id, hosts[2].id]
    with raises_apierror(400):
        host_inventory.apis.groups.patch_group(group, hosts=hosts_ids, wait_for_updated=False)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("field", ["account", "random123"])
def test_groups_mq_events_not_produce_patch_group_unknown_field(
    host_inventory: ApplicationHostInventory,
    field: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when patching group with unknown field
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    insights_ids = [host.insights_id for host in hosts[:2]]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    data = {
        "host_ids": [host.id for host in hosts[1:]],
        field: "123456",
    }
    with raises_apierror(400):
        host_inventory.apis.groups.raw_api.api_group_patch_group_by_id(group.id, data)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
def test_groups_mq_events_produce_delete_single_group(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-delete, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when a single group is deleted
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.groups.delete_groups(group, wait_for_deleted=False)
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == 3
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("all_with_hosts", [True, False], ids=["all with hosts", "one with hosts"])
def test_groups_mq_events_produce_delete_multiple_groups(
    host_inventory: ApplicationHostInventory,
    all_with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-delete, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when multiple groups are deleted
    """
    hosts = host_inventory.kafka.create_random_hosts(4 if all_with_hosts else 2)

    group_name = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    group2_name = generate_display_name()
    group2_hosts = hosts[2:] if all_with_hosts else []
    group2 = host_inventory.apis.groups.create_group(group2_name, hosts=group2_hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.groups.delete_groups([group1, group2], wait_for_deleted=False)
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts}
    assert len(msgs) == len(hosts)
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_delete_group_bad_id(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-delete, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when deleting group with bad ID
    """
    bad_id = generate_string_of_length(36, use_punctuation=False)
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    group2_name = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group2_name, hosts=hosts[2:])

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    group_ids = [group1.id, bad_id, group2.id]
    with raises_apierror(400):
        host_inventory.apis.groups.delete_groups(group_ids, wait_for_deleted=False)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
def test_groups_mq_events_produce_remove_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-remove-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are removed from group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.groups.remove_hosts_from_group(
        group, hosts=hosts[:how_many], wait_for_removed=False
    )
    insights_ids = [host.insights_id for host in hosts[:how_many]]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts[:how_many]}
    assert len(msgs) == how_many
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        original_hosts[msg.host.id]["groups"] = ungrouped_host_groups(host_inventory)
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_remove_hosts_bad_id(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-remove-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when removing bad host IDs from group
    """
    bad_id = generate_string_of_length(36, use_punctuation=False)
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    host_ids = [hosts[0].id, bad_id, hosts[1].id]
    with raises_apierror(400):
        host_inventory.apis.groups.remove_hosts_from_group(
            group, hosts=host_ids, wait_for_removed=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "bad_id",
    [generate_uuid(), generate_string_of_length(36, use_punctuation=False)],
    ids=["uuid", "random string"],
)
def test_groups_mq_events_not_produce_remove_hosts_from_bad_group(
    host_inventory: ApplicationHostInventory,
    bad_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-remove-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when removing hosts from bad group ID
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    error_codes = (400, 404)
    with raises_apierror(error_codes):
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            api.api_host_group_delete_hosts_from_group(bad_id, [host.id for host in hosts])

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_remove_hosts_from_different_group(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3855

    metadata:
      requirements: inv-groups-remove-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when removing hosts from a different group
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    group_name2 = generate_display_name()
    host_inventory.apis.groups.create_group(group_name2, hosts=hosts[2:])

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    with raises_apierror(404):
        host_inventory.apis.groups.remove_hosts_from_group(
            group, hosts=hosts[2:], wait_for_removed=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
def test_groups_mq_events_produce_add_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are added to group
    """
    hosts = host_inventory.kafka.create_random_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[-1])

    insights_ids = [hosts[-1].insights_id]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    updated_group = host_inventory.apis.groups.add_hosts_to_group(
        group, hosts=hosts[:how_many], wait_for_added=False
    )
    insights_ids = [host.insights_id for host in hosts[:how_many]]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts[:how_many]}
    assert len(msgs) == how_many
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        group_dict = group_to_mq_dict(updated_group)
        original_hosts[msg.host.id]["groups"] = [group_dict]
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_add_hosts_bad_id(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when adding bad host IDs to group
    """
    bad_id = generate_string_of_length(36, use_punctuation=False)
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[-1])

    insights_ids = [hosts[-1].insights_id]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    host_ids = [hosts[0].id, bad_id, hosts[1].id]
    with raises_apierror(400):
        host_inventory.apis.groups.add_hosts_to_group(group, hosts=host_ids, wait_for_added=False)

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "bad_id",
    [generate_uuid(), generate_string_of_length(36, use_punctuation=False)],
    ids=["uuid", "random string"],
)
def test_groups_mq_events_not_produce_add_hosts_to_bad_group(
    host_inventory: ApplicationHostInventory,
    bad_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      requirements: inv-groups-add-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when adding hosts to bad group ID
    """
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])

    insights_ids = [hosts[0].insights_id]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    error_codes = (400, 404)
    with raises_apierror(error_codes):
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            api.api_host_group_add_host_list_to_group(bad_id, [hosts[1].id])

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
def test_groups_mq_events_produce_remove_hosts_from_multiple_groups(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are removed from multiple groups via
             DELETE /groups/hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    group_name = generate_display_name()
    host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])

    if how_many > 1:
        host_inventory.apis.groups.create_group(generate_display_name(), hosts=hosts[1:])

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.groups.remove_hosts_from_multiple_groups(hosts, wait_for_removed=False)
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    original_hosts = {host.id: host.data() for host in hosts[:how_many]}
    assert len(msgs) == how_many
    assert {msg.host.id for msg in msgs} == set(original_hosts.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, original_hosts[msg.host.id])
        original_hosts[msg.host.id]["groups"] = ungrouped_host_groups(host_inventory)
        assert msg.host.data() == original_hosts[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_groups_mq_events_not_produce_remove_hosts_from_multiple_groups(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-groups-remove-hosts-multiple-groups, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad
             DELETE /groups/hosts/<host_ids> request
    """
    bad_id = generate_string_of_length(36, use_punctuation=False)
    hosts = host_inventory.kafka.create_random_hosts(2)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    insights_ids = [host.insights_id for host in hosts]
    host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.insights_id, insights_ids)

    host_ids = [hosts[0].id, bad_id, hosts[1].id]
    with raises_apierror(400):
        host_inventory.apis.groups.remove_hosts_from_group(
            group, hosts=host_ids, wait_for_removed=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize(
    "request_id", [generate_uuid(), "", None], ids=["uuid", "empty str", "without"]
)
def test_groups_mq_events_preserve_request_id(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    request_id: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-groups-add-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that groups MQ event messages preserve request_id in message headers and data
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    group = host_inventory.apis.groups.create_group(generate_display_name())

    time1 = datetime.now(tz=UTC)
    if request_id is not None:
        with temp_headers(
            host_inventory.apis.groups.raw_api, {"x-rh-insights-request-id": request_id}
        ):
            host_inventory.apis.groups.add_hosts_to_group(group, hosts=hosts, wait_for_added=False)
    else:
        host_inventory.apis.groups.add_hosts_to_group(group, hosts=hosts, wait_for_added=False)

    insights_ids = [host.insights_id for host in hosts[:how_many]]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    check_api_update_events(
        msgs, time1, time2, host_inventory.apis.rest_identity, request_id=request_id
    )
