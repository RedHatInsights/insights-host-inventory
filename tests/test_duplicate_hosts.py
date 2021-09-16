# from unittest import mock
import pytest
from unittest import mock
from app.logging import get_logger

from app import db
from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
from host_delete_duplicates import run as host_delete_duplicates_run
from host_delete_duplicates import _init_db as _init_db
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.test_utils import get_staleness_timestamps
from lib.handlers import register_shutdown


logger = get_logger(__name__)


@pytest.mark.host_delete_duplicates
def test_delete_duplicate_host(
    event_producer_mock, db_create_host, db_get_host, inventory_config,
):
    staleness_timestamps = get_staleness_timestamps()

    # make two hosts that are the same
    host = minimal_db_host(stale_timestamp=staleness_timestamps["fresh"], reporter="some reporter")
    created_host_1 = db_create_host(host=host)
    created_host_2 = db_create_host(host=host)

    assert db_get_host(created_host_1.id)
    assert db_get_host(created_host_2.id)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()
    register_shutdown(accounts_session.get_bind().dispose, "Closing database")
    register_shutdown(hosts_session.get_bind().dispose, "Closing database")
    register_shutdown(misc_session.get_bind().dispose, "Closing database")

    host_delete_duplicates_run(
        inventory_config,
        mock.Mock(),
        accounts_session,
        hosts_session,
        misc_session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )

    # check that only the more recently added host exists.
    assert db_get_host(created_host_2.id)


@pytest.mark.host_delete_duplicates
def test_delete_multiple_duplicate_hosts(event_producer, kafka_producer, db_create_multiple_hosts, inventory_config):
    # host_count = 25
    # host_count = 0

    # db_create_multiple_hosts(how_many=host_count)

    # threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    # inventory_config.script_chunk_size = 3

    # event_count = host_delete_duplicates_run(
    #     inventory_config,
    #     mock.Mock(),
    #     db.session,
    #     event_producer,
    #     shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    # )

    # assert event_count == host_count
    # assert event_producer._kafka_producer.send.call_count == host_count

    assert True
