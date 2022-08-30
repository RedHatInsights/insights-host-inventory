import json
from unittest import mock

import pytest

from app import db
from app import threadctx
from app.payload_tracker import UNKNOWN_REQUEST_ID_VALUE
from app.queue.events import build_event
from app.queue.events import EventType
from rebuild_events_topic import run as rebuild_events_run
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import create_kafka_consumer_mock
from tests.helpers.test_utils import generate_uuid


def test_no_delete_when_hosts_present(mocker, db_create_host, inventory_config):
    event_producer_mock = mock.Mock()
    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    event_list = []

    for _ in range(4):
        host = minimal_db_host()
        db_create_host(host=host)
        event_list.append(build_event(EventType.created, host))

    consumer_mock = create_kafka_consumer_mock(mocker, inventory_config, 1, 0, 1, event_list)

    rebuild_events_run(
        inventory_config,
        mock.Mock(),
        db.session,
        consumer_mock,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    assert event_producer_mock.write_event.call_count == 0


@pytest.mark.parametrize("num_existing", (0, 3, 4))
@pytest.mark.parametrize("num_missing", (1, 3, 5))
def test_creates_delete_event_when_missing_from_db(
    mocker, db_create_host, inventory_config, num_existing, num_missing
):
    event_producer_mock = mock.Mock()
    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    event_list = []
    existing_hosts_created = 0
    missing_hosts_id_list = []

    # Set up DB and event queue
    while existing_hosts_created < num_existing or len(missing_hosts_id_list) < num_missing:
        if existing_hosts_created < num_existing:
            host = minimal_db_host()
            db_create_host(host=host)
            event_list.append(build_event(EventType.created, host))
            existing_hosts_created += 1
        if len(missing_hosts_id_list) < num_missing:
            missing_host = minimal_db_host()
            missing_host.id = generate_uuid()
            event_list.append(build_event(EventType.updated, missing_host))
            missing_hosts_id_list.append(missing_host.id)

    consumer_mock = create_kafka_consumer_mock(mocker, inventory_config, 1, 0, 1, event_list)

    rebuild_events_run(
        inventory_config,
        mock.Mock(),
        db.session,
        consumer_mock,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    assert event_producer_mock.write_event.call_count == num_missing

    for i in range(num_missing):
        produced_event = json.loads(event_producer_mock.write_event.call_args_list[i][0][0])
        assert produced_event["type"] == "delete"
        assert produced_event["id"] in missing_hosts_id_list
