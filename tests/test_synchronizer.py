from unittest import mock

import pytest

from app import db
from app import threadctx
from host_synchronizer import run as host_synchronizer_run
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import assert_synchronize_event_is_valid
from tests.helpers.test_utils import get_staleness_timestamps


@pytest.mark.host_synchronizer
def test_synchronize_host_event(
    event_producer_mock, event_datetime_mock, db_create_host, db_get_host, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(stale_timestamp=staleness_timestamps["culled"], reporter="some reporter")
    created_host = db_create_host(host=host)

    assert db_get_host(created_host.id)

    threadctx.request_id = None
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
        event_producer=event_producer_mock, key=str(created_host.id), host=created_host, timestamp=event_datetime_mock
    )


@pytest.mark.host_synchronizer
def test_synchronize_multiple_host_events(event_producer, kafka_producer, db_create_multiple_hosts, inventory_config):
    host_count = 25

    db_create_multiple_hosts(how_many=host_count)

    threadctx.request_id = None
    inventory_config.script_chunk_size = 3

    event_count = host_synchronizer_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    assert event_count == host_count
    assert event_producer._kafka_producer.produce.call_count == host_count
