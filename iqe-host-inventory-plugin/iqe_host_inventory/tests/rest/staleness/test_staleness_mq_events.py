from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.api_utils import temp_headers
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.kafka_utils import check_api_update_events
from iqe_host_inventory.utils.kafka_utils import check_prs_timestamps
from iqe_host_inventory.utils.staleness_utils import gen_staleness_settings
from iqe_host_inventory.utils.staleness_utils import validate_host_timestamps

pytestmark = [pytest.mark.backend, pytest.mark.usefixtures("hbi_staleness_cleanup")]
logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def prepare_hosts(host_inventory: ApplicationHostInventory) -> list[HostWrapper]:
    # Delete all hosts to avoid conflicts when searching for kafka events for existing hosts
    host_inventory.apis.hosts.confirm_delete_all()
    new_hosts = host_inventory.kafka.create_random_hosts(5, cleanup_scope="module")
    edge_hosts_data = host_inventory.datagen.create_n_hosts_data(5, host_type="edge")
    new_hosts += host_inventory.kafka.create_hosts(edge_hosts_data, cleanup_scope="module")
    return new_hosts


def validate_timestamps(
    host_inventory_app: ApplicationHostInventory,
    orig_host: HostWrapper,
    msg_host: HostWrapper,
    staleness_settings: dict | None = None,
) -> None:
    assert msg_host.created == orig_host.created
    assert msg_host.last_check_in == orig_host.last_check_in
    assert msg_host.updated == orig_host.updated
    host_type = orig_host.system_profile.get("host_type", "conventional")
    validate_host_timestamps(host_inventory_app, msg_host, host_type)
    check_prs_timestamps(
        msg_host.per_reporter_staleness,
        orig_host.reporter,
        orig_host.last_check_in,
        staleness_settings=staleness_settings,
    )


@pytest.mark.ephemeral
@pytest.mark.smoke
def test_staleness_mq_events_produce_create_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when a new staleness config is created
    """
    new_staleness_settings = gen_staleness_settings(want_sample=False)
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.account_staleness.create_staleness(
        **new_staleness_settings, wait_for_host_events=False
    )
    insights_ids = [host.insights_id for host in prepare_hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    hosts_by_ids = {host.id: host for host in prepare_hosts}
    assert len(msgs) == len(prepare_hosts)
    assert {msg.host.id for msg in msgs} == set(hosts_by_ids.keys())

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)

    for msg in msgs:
        validate_timestamps(
            host_inventory, hosts_by_ids[msg.host.id], msg.host, new_staleness_settings
        )


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_create_staleness_second_time(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating staleness config the second time
    """
    host_inventory.apis.account_staleness.create_staleness(
        **gen_staleness_settings(want_sample=False), wait_for_host_events=True
    )

    with raises_apierror(400):
        host_inventory.apis.account_staleness.create_staleness(
            **gen_staleness_settings(want_sample=False), wait_for_host_events=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_create_staleness_bad_values(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when creating staleness config with bad values
    """
    with raises_apierror(400):
        host_inventory.apis.account_staleness.create_staleness(
            conventional_time_to_stale=50,
            conventional_time_to_stale_warning=10,
            wait_for_host_events=False,
        )

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_produce_update_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when staleness config is updated
    """
    host_inventory.apis.account_staleness.create_staleness(
        **gen_staleness_settings(want_sample=False), wait_for_host_events=True
    )

    new_staleness_settings = gen_staleness_settings(want_sample=False)
    time1 = datetime.now(tz=UTC)
    host_inventory.apis.account_staleness.update_staleness(
        **new_staleness_settings, wait_for_host_events=False
    )
    insights_ids = [host.insights_id for host in prepare_hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    hosts_by_ids = {host.id: host for host in prepare_hosts}
    assert len(msgs) == len(prepare_hosts)
    assert {msg.host.id for msg in msgs} == set(hosts_by_ids.keys())

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)

    for msg in msgs:
        validate_timestamps(
            host_inventory, hosts_by_ids[msg.host.id], msg.host, new_staleness_settings
        )


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_update_staleness_nonexistent(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when updating a non-existent staleness config
    """
    with raises_apierror(404):
        host_inventory.apis.account_staleness.update_staleness(
            **gen_staleness_settings(want_sample=False), wait_for_host_events=False
        )

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_update_staleness_bad_values(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-patch, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when updating staleness config with bad values
    """
    host_inventory.apis.account_staleness.create_staleness(
        **gen_staleness_settings(want_sample=False), wait_for_host_events=True
    )

    with raises_apierror(400):
        host_inventory.apis.account_staleness.update_staleness(
            conventional_time_to_stale=50,
            conventional_time_to_stale_warning=10,
            wait_for_host_events=False,
        )

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_produce_delete_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-delete, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Produce kafka event message when staleness config is deleted
    """
    host_inventory.apis.account_staleness.create_staleness(
        **gen_staleness_settings(want_sample=False), wait_for_host_events=True
    )

    time1 = datetime.now(tz=UTC)
    host_inventory.apis.account_staleness.delete_staleness(wait_for_host_events=False)
    insights_ids = [host.insights_id for host in prepare_hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    hosts_by_ids = {host.id: host for host in prepare_hosts}
    assert len(msgs) == len(prepare_hosts)
    assert {msg.host.id for msg in msgs} == set(hosts_by_ids.keys())

    check_api_update_events(msgs, time1, time2, host_inventory.apis.rest_identity)

    for msg in msgs:
        validate_timestamps(host_inventory, hosts_by_ids[msg.host.id], msg.host)


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_delete_staleness_nonexistent(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-delete, inv-produce-event-messages
      assignee: fstavela
      importance: high
      negative: true
      title: Don't produce kafka event message when deleting a non-existent staleness config
    """
    with raises_apierror(404):
        host_inventory.apis.account_staleness.delete_staleness(wait_for_host_events=False)

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_get_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-get, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Don't produce kafka event message when getting staleness config
    """
    host_inventory.apis.account_staleness.get_staleness()

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
def test_staleness_mq_events_not_produce_get_default_staleness(
    host_inventory: ApplicationHostInventory,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-get-defaults, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Don't produce kafka event message when getting the default staleness config
    """
    host_inventory.apis.account_staleness.get_default_staleness()

    host_inventory.kafka.verify_host_messages_not_produced(prepare_hosts, timeout=2)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "request_id", [generate_uuid(), "", None], ids=["uuid", "empty str", "without"]
)
def test_staleness_mq_events_preserve_request_id(
    host_inventory: ApplicationHostInventory,
    request_id: str | None,
    prepare_hosts: list[HostWrapper],
) -> None:
    """
    https://issues.redhat.com/browse/RHINENG-16619

    metadata:
      requirements: inv-staleness-post, inv-produce-event-messages
      assignee: fstavela
      importance: high
      title: Test that staleness MQ event messages preserve request_id in message headers and data
    """
    time1 = datetime.now(tz=UTC)
    if request_id is not None:
        with temp_headers(
            host_inventory.apis.account_staleness.raw_api, {"x-rh-insights-request-id": request_id}
        ):
            host_inventory.apis.account_staleness.create_staleness(
                **gen_staleness_settings(want_sample=False), wait_for_host_events=False
            )
    else:
        host_inventory.apis.account_staleness.create_staleness(
            **gen_staleness_settings(want_sample=False), wait_for_host_events=False
        )

    insights_ids = [host.insights_id for host in prepare_hosts]
    msgs = host_inventory.kafka.wait_for_filtered_host_messages(
        HostWrapper.insights_id, insights_ids
    )
    time2 = datetime.now(tz=UTC)

    check_api_update_events(
        msgs, time1, time2, host_inventory.apis.rest_identity, request_id=request_id
    )
