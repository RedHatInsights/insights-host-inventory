from unittest import mock

import pytest
from kafka.errors import KafkaError

from app import db
from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
from host_synchronizer import run as host_synchronizer_run
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import assert_synchronize_event_is_valid
from tests.helpers.test_utils import get_staleness_timestamps


@pytest.mark.host_synchronizer
def test_synchronize_host_event(
    event_producer_mock, event_datetime_mock, db_create_host, db_get_host, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(stale_timestamp=staleness_timestamps["culled"].isoformat(), reporter="some reporter")
    created_host = db_create_host(host)

    assert db_get_host(created_host.id)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    host_synchronizer_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    # check if host exist thought event synchronizer must find it to produce an update event.
    assert db_get_host(created_host.id)

    assert_synchronize_event_is_valid(
        event_producer=event_producer_mock, host=created_host, timestamp=event_datetime_mock
    )


@pytest.mark.host_synchronizer
def test_synchronize_multiple_host_events(event_producer, kafka_producer, db_create_multiple_hosts, inventory_config):
    host_count = 25

    db_create_multiple_hosts(how_many=host_count)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    inventory_config.script_chunk_size = 3

    event_count = host_synchronizer_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    assert event_count == host_count
    assert event_producer._kafka_producer.send.call_count == host_count


@pytest.mark.host_synchronizer
@pytest.mark.parametrize(
    "send_side_effects",
    ((mock.Mock(), mock.Mock(**{"get.side_effect": KafkaError()})), (mock.Mock(), KafkaError("oops"))),
)
def test_synchrnize_after_kafka_producer_error(
    send_side_effects,
    kafka_producer,
    event_producer,
    event_datetime_mock,
    db_create_multiple_hosts,
    db_get_hosts,
    inventory_config,
):
    event_producer._kafka_producer.send.side_effect = send_side_effects

    host_count = 3
    created_hosts = db_create_multiple_hosts(how_many=host_count)
    created_host_ids = [str(host.id) for host in created_hosts]

    hosts = db_get_hosts(created_host_ids)
    assert hosts.count() == host_count

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    with pytest.raises(KafkaError):
        host_synchronizer_run(
            inventory_config,
            mock.Mock(),
            db.session,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert event_producer._kafka_producer.send.call_count == (host_count - 1)
