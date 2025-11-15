from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostMessageWrapper
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import OperatingSystem
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_operating_system as gen_os
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory.utils.kafka_utils import check_api_update_events
from iqe_host_inventory.utils.kafka_utils import check_delete_events
from iqe_host_inventory.utils.kafka_utils import check_host_timestamps
from iqe_host_inventory.utils.kafka_utils import check_mq_create_events
from iqe_host_inventory.utils.kafka_utils import check_mq_create_or_update_event_host_data
from iqe_host_inventory.utils.kafka_utils import check_mq_update_events

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend]


def get_kafka_msgs(
    host_inventory: ApplicationHostInventory, hosts: list[HostWrapper]
) -> tuple[list[HostMessageWrapper], datetime]:
    insights_ids = [host.insights_id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time = datetime.now(tz=UTC)

    assert len(msgs) == len(hosts)
    return msgs, time


def generate_bootc_status(host_data: dict, bootc_status: str | dict | None):
    bootc_status_field = get_sp_field_by_name("bootc_status")
    if bootc_status is None:
        host_data["system_profile"].pop("bootc_status", None)
    elif bootc_status == "without_booted":
        bootc_status_value = generate_sp_field_value(bootc_status_field)
        bootc_status_value.pop("booted", None)
        host_data["system_profile"]["bootc_status"] = bootc_status_value
    elif bootc_status == "with_booted":
        bootc_status_value = generate_sp_field_value(bootc_status_field)
        bootc_status_value.pop("rollback", None)
        bootc_status_value.pop("staged", None)
        host_data["system_profile"]["bootc_status"] = bootc_status_value
    else:
        host_data["system_profile"]["bootc_status"] = bootc_status


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("how_many", [1, 3])
def test_hosts_mq_events_produce_patch_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are updated via PATCH /hosts/<host_ids> endpoint
    """  # NOQA: E501
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    new_display_name = generate_display_name()
    new_ansible_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.patch_hosts(
        hosts, display_name=new_display_name, ansible_host=new_ansible_name, wait_for_updated=False
    )

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    # Check host data
    hosts_dict = {host.id: host.data() for host in hosts}
    assert {msg.host.id for msg in msgs} == set(hosts_dict.keys())
    for msg in msgs:
        check_host_timestamps(msg.host, hosts_dict[msg.host.id])
        hosts_dict[msg.host.id]["display_name"] = new_display_name
        hosts_dict[msg.host.id]["ansible_host"] = new_ansible_name
        assert msg.host.data() == hosts_dict[msg.host.id]

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_patch_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad PATCH /hosts/<host_ids> request
    """
    host = host_inventory.kafka.create_host()

    new_name = generate_string_of_length(300)
    with raises_apierror(400):
        host_inventory.apis.hosts.patch_hosts(host, display_name=new_name, wait_for_updated=False)

    host_inventory.kafka.verify_host_messages_not_produced([host])


@pytest.mark.ephemeral
def test_hosts_mq_events_produce_patch_hosts_facts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch-facts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are updated via
             PATCH /hosts/<host_ids>/facts/<namespace> endpoint
    """
    fact_namespace = "namespace1"
    original_facts = {
        "fact1": generate_string_of_length(10),
        "fact2": generate_string_of_length(10),
    }
    formatted_facts = [{"namespace": fact_namespace, "facts": original_facts}]
    host_data = host_inventory.datagen.create_host_data(facts=formatted_facts)
    host = host_inventory.kafka.create_host(host_data=host_data)

    new_facts = {"fact2": generate_string_of_length(10), "fact3": generate_string_of_length(10)}

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.raw_api.api_host_merge_facts([host.id], fact_namespace, new_facts)

    msgs, time2 = get_kafka_msgs(host_inventory, [host])

    # Check host data
    assert msgs[0].host.id == host.id
    host_dict = host.data()
    check_host_timestamps(msgs[0].host, host_dict)
    host_dict["facts"][0]["facts"] = {**original_facts, **new_facts}
    assert msgs[0].host.data() == host_dict

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_patch_hosts_facts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch-facts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad
             PATCH /hosts/<host_ids>/facts/<namespace> request
    """
    host = host_inventory.kafka.create_host()

    facts = {
        "fact1": generate_string_of_length(10),
        "fact2": generate_string_of_length(10),
    }
    with raises_apierror(404):
        host_inventory.apis.hosts.raw_api.api_host_merge_facts([host.id], "new-namespace", facts)

    host_inventory.kafka.verify_host_messages_not_produced([host])


@pytest.mark.ephemeral
def test_hosts_mq_events_produce_put_hosts_facts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-put-facts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are updated via
             PUT /hosts/<host_ids>/facts/<namespace> endpoint
    """
    fact_namespace = "namespace1"
    original_facts = {
        "fact1": generate_string_of_length(10),
        "fact2": generate_string_of_length(10),
    }
    formatted_facts = [{"namespace": fact_namespace, "facts": original_facts}]
    host_data = host_inventory.datagen.create_host_data(facts=formatted_facts)
    host = host_inventory.kafka.create_host(host_data=host_data)

    new_facts = {"fact2": generate_string_of_length(10), "fact3": generate_string_of_length(10)}

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.replace_facts([host.id], namespace=fact_namespace, facts=new_facts)

    msgs, time2 = get_kafka_msgs(host_inventory, [host])
    first_host = msgs[0].host
    # Check host data
    assert first_host.id == host.id
    host_dict = host.data()
    check_host_timestamps(first_host, host_dict)
    host_dict["facts"][0]["facts"] = new_facts
    assert first_host.data() == host_dict

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_put_hosts_facts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-put-facts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad
             PUT /hosts/<host_ids>/facts/<namespace> request
    """
    host = host_inventory.kafka.create_host()

    facts = {
        "fact1": generate_string_of_length(10),
        "fact2": generate_string_of_length(10),
    }
    with raises_apierror(404):
        host_inventory.apis.hosts.replace_facts([host.id], namespace="new-namespace", facts=facts)

    host_inventory.kafka.verify_host_messages_not_produced([host])


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("how_many", [1, 3])
def test_hosts_mq_events_produce_delete_hosts_by_ids(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are deleted via
             DELETE /hosts/<host_ids> endpoint
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_delete_hosts_by_ids(
    host_inventory: ApplicationHostInventory, is_kessel_phase_1_enabled: bool
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad DELETE /hosts/<host_ids> request
    """
    not_existing_host_id = generate_uuid()
    host = HostWrapper({"id": not_existing_host_id})
    with raises_apierror(403 if is_kessel_phase_1_enabled else 404):
        host_inventory.apis.hosts.raw_api.api_host_delete_host_by_id([not_existing_host_id])

    host_inventory.kafka.verify_host_messages_not_produced([host], field=HostWrapper.id)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
def test_hosts_mq_events_produce_delete_hosts_filtered(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-filtered-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are deleted via DELETE /hosts endpoint
    """
    display_name = generate_display_name()
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        host_data["display_name"] = display_name
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.raw_api.api_host_delete_hosts_by_filter(display_name=display_name)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_delete_hosts_filtered(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-filtered-hosts, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad DELETE /hosts request
    """
    host = host_inventory.kafka.create_host()
    host_inventory.apis.hosts.raw_api.api_host_delete_hosts_by_filter(
        display_name=generate_display_name()
    )

    host_inventory.kafka.verify_host_messages_not_produced([host])


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
def test_hosts_mq_events_produce_delete_hosts_all(
    host_inventory: ApplicationHostInventory,
    how_many: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-all, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when hosts are deleted via DELETE /hosts/all endpoint
    """
    display_name = generate_display_name()
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        host_data["display_name"] = display_name
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.raw_api.api_host_delete_all_hosts(confirm_delete_all=True)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
def test_hosts_mq_events_not_produce_delete_hosts_all(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-all, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when sending bad DELETE /hosts/all request
    """
    host = host_inventory.kafka.create_host()
    with raises_apierror(400):
        host_inventory.apis.hosts.raw_api.api_host_delete_all_hosts()

    host_inventory.kafka.verify_host_messages_not_produced([host])


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("host_type", ["edge", None])
def test_hosts_mq_events_update_preserves_host_type(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    host_type: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'updated' MQ event messages preserve host_type in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if host_type is None:
            host_data["system_profile"].pop("host_type", None)
        else:
            host_data["system_profile"]["host_type"] = host_type
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    new_display_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.patch_hosts(
        hosts, display_name=new_display_name, wait_for_updated=False
    )

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("host_type", ["edge", None])
def test_hosts_mq_events_delete_preserves_host_type(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    host_type: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' MQ event messages preserve host_type in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if host_type is None:
            host_data["system_profile"].pop("host_type", None)
        else:
            host_data["system_profile"]["host_type"] = host_type
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize(
    "operating_system",
    [gen_os("RHEL"), gen_os("CentOS"), gen_os("CentOS Linux"), None],
    ids=["RHEL", "CentOS", "CentOS Linux", "None"],
)
def test_hosts_mq_events_update_preserves_os_name(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    operating_system: OperatingSystem,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'updated' MQ event messages preserve os_name in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if operating_system is None:
            host_data["system_profile"].pop("operating_system", None)
        else:
            host_data["system_profile"]["operating_system"] = operating_system
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    new_display_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.patch_hosts(
        hosts, display_name=new_display_name, wait_for_updated=False
    )

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize(
    "operating_system",
    [gen_os("RHEL"), gen_os("CentOS"), gen_os("CentOS Linux"), None],
    ids=["RHEL", "CentOS", "CentOS Linux", "None"],
)
def test_hosts_mq_events_delete_preserves_os_name(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    operating_system: OperatingSystem,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' MQ event messages preserve os_name in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if operating_system is None:
            host_data["system_profile"].pop("operating_system", None)
        else:
            host_data["system_profile"]["operating_system"] = operating_system
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("bootc_status", [None, {}, "without_booted", "with_booted"])
def test_hosts_mq_events_update_preserves_is_bootc(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    bootc_status: str | dict | None,
):
    """
    https://issues.redhat.com/browse/RHINENG-11272

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'updated' MQ event messages preserve is_bootc in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        generate_bootc_status(host_data, bootc_status)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    new_display_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.patch_hosts(
        hosts, display_name=new_display_name, wait_for_updated=False
    )

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("bootc_status", [None, {}, "without_booted", "with_booted"])
def test_hosts_mq_events_delete_preserves_is_bootc(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    bootc_status: str | dict | None,
):
    """
    https://issues.redhat.com/browse/RHINENG-11272

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' MQ event messages preserve is_bootc in message headers
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        generate_bootc_status(host_data, bootc_status)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("insights_id", ["random", None], ids=["with", "without"])
def test_hosts_mq_events_update_preserves_insights_id(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    insights_id: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'updated' MQ event messages preserve insights_id in message headers and data
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if insights_id is None:
            host_data.pop("insights_id", None)
        else:
            host_data["insights_id"] = generate_uuid()
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    new_display_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.patch_hosts(
        hosts, display_name=new_display_name, wait_for_updated=False
    )

    hosts_ids = [host.id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.id, hosts_ids)
    time2 = datetime.now(tz=UTC)
    assert len(msgs) == len(hosts)

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("insights_id", ["random", None], ids=["with", "without"])
def test_hosts_mq_events_delete_preserves_insights_id(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    insights_id: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' MQ event messages preserve insights_id in message headers and data
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if insights_id is None:
            host_data.pop("insights_id", None)
        else:
            host_data["insights_id"] = generate_uuid()
    hosts = host_inventory.kafka.create_hosts(
        hosts_data=hosts_data, field_to_match=HostWrapper.subscription_manager_id
    )

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    hosts_ids = [host.id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.id, hosts_ids)
    time2 = datetime.now(tz=UTC)
    assert len(msgs) == len(hosts)

    check_delete_events(msgs, time1, time2, hosts, host_inventory.apis.rest_identity)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize("with_rhsm_id", [True, False], ids=["with RHSM ID", "without RHSM ID"])
@pytest.mark.parametrize("initiated_by_frontend", [True, False], ids=["UI", "not UI"])
def test_hosts_mq_events_delete_preserves_subscription_manager_id_and_initiated_by_frontend(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    with_rhsm_id: bool,
    initiated_by_frontend: bool,
):
    """
    https://issues.redhat.com/browse/RHINENG-12780

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' event has subscription_manager_id and indicates manual (UI) delete
    """
    hosts_data = host_inventory.datagen.create_n_hosts_data(how_many)
    for host_data in hosts_data:
        if with_rhsm_id:
            host_data["subscription_manager_id"] = generate_uuid()
        else:
            host_data.pop("subscription_manager_id", None)
    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    time1 = datetime.now(tz=UTC)
    if initiated_by_frontend:
        with temp_headers(host_inventory.apis.hosts.raw_api, {"x-rh-frontend-origin": "hcc"}):
            host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)
    else:
        host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    hosts_ids = [host.id for host in hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.id, hosts_ids)
    time2 = datetime.now(tz=UTC)
    assert len(msgs) == len(hosts)

    check_delete_events(
        msgs,
        time1,
        time2,
        hosts,
        host_inventory.apis.rest_identity,
        initiated_by_frontend=initiated_by_frontend,
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("frontend_header", ["hcb", ""])
def test_hosts_mq_events_delete_not_initiated_by_frontend(
    host_inventory: ApplicationHostInventory, frontend_header: str
):
    """
    https://issues.redhat.com/browse/RHINENG-12780

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' event doesn't indicate manual (UI) delete with different UI headers
    """
    host = host_inventory.kafka.create_host()

    time1 = datetime.now(tz=UTC)
    with temp_headers(
        host_inventory.apis.hosts.raw_api, {"x-rh-frontend-origin": frontend_header}
    ):
        host_inventory.apis.hosts.delete_by_id(host, wait_for_deleted=False)

    msgs = host_inventory.kafka.wait_for_filtered_host_messages(HostWrapper.id, [host.id])
    time2 = datetime.now(tz=UTC)
    assert len(msgs) == 1

    check_delete_events(
        msgs, time1, time2, [host], host_inventory.apis.rest_identity, initiated_by_frontend=False
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize(
    "request_id", [generate_uuid(), "", None], ids=["uuid", "empty str", "without"]
)
def test_hosts_mq_events_update_preserves_request_id(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    request_id: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'updated' MQ event messages preserve request_id in message headers and data
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    new_display_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    if request_id is not None:
        with temp_headers(
            host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": request_id}
        ):
            host_inventory.apis.hosts.patch_hosts(
                hosts, display_name=new_display_name, wait_for_updated=False
            )
    else:
        host_inventory.apis.hosts.patch_hosts(
            hosts, display_name=new_display_name, wait_for_updated=False
        )

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_api_update_events(
        msgs, time1, time2, host_inventory.apis.rest_identity, request_id=request_id
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3])
@pytest.mark.parametrize(
    "request_id", [generate_uuid(), "", None], ids=["uuid", "empty str", "without"]
)
def test_hosts_mq_events_delete_preserves_request_id(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    request_id: str | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
      requirements: inv-hosts-delete-by-id, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that 'delete' MQ event messages preserve request_id in message headers and data
    """
    hosts = host_inventory.kafka.create_random_hosts(how_many)

    time1 = datetime.now(tz=UTC)
    if request_id is not None:
        with temp_headers(
            host_inventory.apis.hosts.raw_api, {"x-rh-insights-request-id": request_id}
        ):
            host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)
    else:
        host_inventory.apis.hosts.delete_by_id(hosts, wait_for_deleted=False)

    msgs, time2 = get_kafka_msgs(host_inventory, hosts)

    check_delete_events(
        msgs, time1, time2, hosts, host_inventory.apis.rest_identity, request_id=request_id
    )


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("host_type", ["edge", None])
def test_hosts_mq_events_kafka_create_preserves_host_type(
    host_inventory: ApplicationHostInventory, host_type: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-create
        assignee: fstavela
        importance: high
        title: Test creating a host produces a kafka message with host_type in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if host_type is None:
        host_data["system_profile"].pop("host_type", None)
    else:
        host_data["system_profile"]["host_type"] = host_type

    time1 = datetime.now(tz=UTC)
    created_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(created_messages) == 1
    created_message = created_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(created_message.host.data()),
        host_data,
        time1,
        time2,
        groups=created_message.host.data().get("groups", []),
    )
    check_mq_create_events(
        [created_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=created_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("host_type", ["edge", None])
def test_hosts_mq_events_kafka_update_preserves_host_type(
    host_inventory: ApplicationHostInventory, host_type: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test updating a host produces a kafka message with host_type in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if host_type is None:
        host_data["system_profile"].pop("host_type", None)
    else:
        host_data["system_profile"]["host_type"] = host_type
    original_host = host_inventory.kafka.create_host(host_data)

    host_data["display_name"] = generate_display_name()

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        groups=updated_message.host.data().get("groups", []),
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=updated_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "operating_system",
    [gen_os("RHEL"), gen_os("CentOS"), gen_os("CentOS Linux"), None],
    ids=["RHEL", "CentOS", "CentOS Linux", "None"],
)
def test_hosts_mq_events_kafka_create_preserves_os_name(
    host_inventory: ApplicationHostInventory, operating_system: OperatingSystem | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-create
        assignee: fstavela
        importance: high
        title: Test creating a host produces a kafka message with os_name in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if operating_system is None:
        host_data["system_profile"].pop("operating_system", None)
    else:
        host_data["system_profile"]["operating_system"] = operating_system

    time1 = datetime.now(tz=UTC)
    created_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(created_messages) == 1
    created_message = created_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(created_message.host.data()), host_data, time1, time2
    )
    check_mq_create_events(
        [created_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=created_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "operating_system",
    [gen_os("RHEL"), gen_os("CentOS"), gen_os("CentOS Linux"), None],
    ids=["RHEL", "CentOS", "CentOS Linux", "None"],
)
def test_hosts_mq_events_kafka_update_preserves_os_name(
    host_inventory: ApplicationHostInventory, operating_system: OperatingSystem | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test updating a host produces a kafka message with os_name in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if operating_system is None:
        host_data["system_profile"].pop("operating_system", None)
    else:
        host_data["system_profile"]["operating_system"] = operating_system
    original_host = host_inventory.kafka.create_host(host_data)

    host_data["display_name"] = generate_display_name()

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=updated_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("bootc_status", [None, {}, "without_booted", "with_booted"])
def test_hosts_mq_events_kafka_create_preserves_is_bootc(
    host_inventory: ApplicationHostInventory,
    bootc_status: str | dict | None,
):
    """
    https://issues.redhat.com/browse/RHINENG-11272

    metadata:
        requirements: inv-produce-event-messages, inv-host-create
        assignee: fstavela
        importance: high
        title: Test creating a host produces a kafka message with is_bootc in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    generate_bootc_status(host_data, bootc_status)

    time1 = datetime.now(tz=UTC)
    created_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(created_messages) == 1
    created_message = created_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(created_message.host.data()),
        host_data,
        time1,
        time2,
        groups=created_message.host.data().get("groups", []),
    )
    check_mq_create_events(
        [created_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=created_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.smoke
@pytest.mark.parametrize("bootc_status", [None, {}, "without_booted", "with_booted"])
def test_hosts_mq_events_kafka_update_preserves_is_bootc(
    host_inventory: ApplicationHostInventory,
    bootc_status: str | dict | None,
):
    """
    https://issues.redhat.com/browse/RHINENG-11272

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test updating a host produces a kafka message with is_bootc in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    generate_bootc_status(host_data, bootc_status)
    original_host = host_inventory.kafka.create_host(host_data)

    host_data["display_name"] = generate_display_name()

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events([host_data])
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        groups=updated_message.host.data().get("groups", []),
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=updated_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("insights_id", ["random", None], ids=["with", "without"])
def test_hosts_mq_events_kafka_create_preserves_insights_id(
    host_inventory: ApplicationHostInventory, insights_id: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-create
        assignee: fstavela
        importance: high
        title: Test creating a host produces a kafka message with insights_id in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if insights_id is None:
        host_data.pop("insights_id", None)
    else:
        host_data["insights_id"] = generate_uuid()

    time1 = datetime.now(tz=UTC)
    created_messages = host_inventory.kafka.create_host_events(
        [host_data], field_to_match=HostWrapper.subscription_manager_id
    )
    time2 = datetime.now(tz=UTC)

    assert len(created_messages) == 1
    created_message = created_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(created_message.host.data()),
        host_data,
        time1,
        time2,
        groups=created_message.host.data().get("groups", []),
    )
    check_mq_create_events(
        [created_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=created_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("insights_id", ["random", None], ids=["with", "without"])
def test_hosts_mq_events_kafka_update_preserves_insights_id(
    host_inventory: ApplicationHostInventory, insights_id: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test updating a host produces a kafka message with insights_id in headers
    """
    host_data = host_inventory.datagen.create_host_data()
    if insights_id is None:
        host_data.pop("insights_id", None)
    else:
        host_data["insights_id"] = generate_uuid()
    original_host = host_inventory.kafka.create_host(
        host_data, field_to_match=HostWrapper.subscription_manager_id
    )

    host_data["display_name"] = generate_display_name()

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events(
        [host_data], field_to_match=HostWrapper.subscription_manager_id
    )
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=updated_message.headers["request_id"],
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "request_id",
    [generate_uuid(), "", None, "not-provided"],
    ids=["uuid", "empty str", "None", "not provided"],
)
def test_hosts_mq_events_kafka_create_preserves_request_id(
    host_inventory: ApplicationHostInventory, request_id: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-create
        assignee: fstavela
        importance: high
        title: Test creating a host produces a kafka message with request_id in headers
    """
    if request_id == "not-provided":
        metadata = None
        expected_request_id = None
    else:
        metadata = {"request_id": request_id}
        expected_request_id = request_id

    host_data = host_inventory.datagen.create_host_data()

    time1 = datetime.now(tz=UTC)
    created_messages = host_inventory.kafka.create_host_events(
        [host_data],
        metadata=metadata,
        omit_request_id=(metadata is None),
    )
    time2 = datetime.now(tz=UTC)

    assert len(created_messages) == 1
    created_message = created_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(created_message.host.data()), host_data, time1, time2
    )
    check_mq_create_events(
        [created_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=expected_request_id,
    )
    if request_id != "not-provided":
        assert created_message.value["platform_metadata"]["request_id"] == request_id


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "request_id",
    [generate_uuid(), "", None, "not-provided"],
    ids=["uuid", "empty str", "None", "not provided"],
)
def test_hosts_mq_events_kafka_update_preserves_request_id(
    host_inventory: ApplicationHostInventory, request_id: str | None
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test updating a host produces a kafka message with request_id in headers
    """
    if request_id == "not-provided":
        metadata = None
        expected_request_id = None
    else:
        metadata = {"request_id": request_id}
        expected_request_id = request_id

    host_data = host_inventory.datagen.create_host_data()
    original_host = host_inventory.kafka.create_host(host_data)

    host_data["display_name"] = generate_display_name()

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events(
        [host_data],
        metadata=metadata,
        omit_request_id=(metadata is None),
    )
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=expected_request_id,
    )
    if request_id != "not-provided":
        assert updated_message.value["platform_metadata"]["request_id"] == request_id


@pytest.mark.ephemeral
def test_hosts_mq_events_kafka_update_preserves_headers_without_provided_data(
    host_inventory: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-5471
    https://github.com/RedHatInsights/insights-host-inventory/pull/1528

    metadata:
        requirements: inv-produce-event-messages, inv-host-update
        assignee: fstavela
        importance: high
        title: Test headers in updated event have data from updated host, instead of input data
    """
    host_data = host_inventory.datagen.create_host_data()
    host_data["insights_id"] = generate_uuid()
    host_data["system_profile"]["operating_system"] = gen_os("RHEL")
    host_data["system_profile"]["host_type"] = "edge"
    original_host = host_inventory.kafka.create_host(host_data)

    host_data["display_name"] = generate_display_name()
    update_host_data = deepcopy(host_data)
    update_host_data.pop("insights_id")
    update_host_data["system_profile"].pop("operating_system")
    update_host_data["system_profile"].pop("host_type")

    time1 = datetime.now(tz=UTC)
    updated_messages = host_inventory.kafka.create_host_events(
        [update_host_data], field_to_match=HostWrapper.subscription_manager_id
    )
    time2 = datetime.now(tz=UTC)

    assert len(updated_messages) == 1
    updated_message = updated_messages[0]
    check_mq_create_or_update_event_host_data(
        deepcopy(updated_message.host.data()),
        host_data,
        time1,
        time2,
        created_timestamp=original_host.created,
        host_id=original_host.id,
    )
    check_mq_update_events(
        [updated_message],
        time1,
        time2,
        {"identity": host_inventory.kafka.identity},
        request_id=updated_message.headers["request_id"],
    )
