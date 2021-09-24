import json
from unittest import mock

from app import db
from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
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

    for _ in range(5):
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

    assert event_producer_mock.call_count == 0


def test_creates_delete_event_when_missing_from_db(mocker, db_create_host, inventory_config):
    event_producer_mock = mock.Mock()
    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    event_list = []

    for _ in range(4):
        host = minimal_db_host()
        db_create_host(host=host)
        event_list.append(build_event(EventType.created, host))

    missing_host = minimal_db_host()
    missing_host.id = generate_uuid()
    event_list.append(build_event(EventType.updated, missing_host))
    consumer_mock = create_kafka_consumer_mock(mocker, inventory_config, 1, 0, 1, event_list)

    rebuild_events_run(
        inventory_config,
        mock.Mock(),
        db.session,
        consumer_mock,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    produced_event = json.loads(event_producer_mock.write_event.call_args_list[0][0][0])

    assert produced_event["type"] == "delete"
    assert produced_event["id"] == missing_host.id
