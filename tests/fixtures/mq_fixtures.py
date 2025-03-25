import json
from datetime import datetime
from datetime import timezone
from unittest.mock import patch

import pytest

from app.models import db
from app.queue.event_producer import EventProducer
from app.queue.host_mq import add_host
from app.queue.host_mq import handle_message
from app.queue.host_mq import write_add_update_event_message
from app.utils import HostWrapper
from tests.helpers.api_utils import FACTS
from tests.helpers.api_utils import TAGS
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import MockFuture
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import get_staleness_timestamps
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.fixture(scope="function")
def mq_create_or_update_host(
    flask_app,  # noqa: ARG001
    event_producer_mock,
    notification_event_producer_mock,
):
    def _mq_create_or_update_host(
        host_data,
        platform_metadata=None,
        return_all_data=False,
        event_producer=event_producer_mock,
        message_operation=add_host,
        operation_args=None,
        notification_event_producer=notification_event_producer_mock,
    ):
        if not platform_metadata:
            platform_metadata = get_platform_metadata()

        message = wrap_message(host_data.data(), platform_metadata=platform_metadata, operation_args=operation_args)
        result = handle_message(json.dumps(message), notification_event_producer, message_operation)
        db.session.commit()
        write_add_update_event_message(event_producer, notification_event_producer_mock, result)
        event = json.loads(event_producer.event)

        if return_all_data:
            return event_producer_mock.key, event, event_producer.headers

        # add facts object since it's not returned by event message
        return HostWrapper({**event["host"], **{"facts": host_data.facts}})

    return _mq_create_or_update_host


@pytest.fixture(scope="function")
def mq_create_three_specific_hosts(mq_create_or_update_host):
    created_hosts = []
    for i in range(1, 4):
        fqdn = f"host{i}.domain.test"
        host = base_host(
            insights_id=generate_uuid(), display_name=f"host{i}", fqdn=fqdn, facts=FACTS, tags=TAGS[i - 1]
        )
        created_host = mq_create_or_update_host(host)

        if i == 2:
            # Update second host to duplicate the FQDN of the first.
            # We do this in the loop as to not change the create/update order.
            host = minimal_host(
                insights_id=created_host.insights_id,
                display_name=created_host.display_name,
                fqdn=created_hosts[0].fqdn,
                facts=FACTS,
                tags=created_host.tags,
            )
            created_host = mq_create_or_update_host(host)

        created_hosts.append(created_host)

    return created_hosts


@pytest.fixture(scope="function")
def mq_create_four_specific_hosts(mq_create_three_specific_hosts, mq_create_or_update_host):
    created_hosts = mq_create_three_specific_hosts
    host = minimal_host(insights_id=generate_uuid(), display_name=created_hosts[0].display_name)
    created_host = mq_create_or_update_host(host)
    created_hosts.append(created_host)

    return created_hosts


@pytest.fixture(scope="function")
def mq_create_hosts_in_all_states(mq_create_or_update_host):
    staleness_timestamps = get_staleness_timestamps()
    created_hosts = {}
    for state, timestamp in staleness_timestamps.items():
        host = minimal_host(
            insights_id=generate_uuid(), stale_timestamp=timestamp.isoformat(), reporter="some reporter", facts=FACTS
        )
        created_hosts[state] = mq_create_or_update_host(host)

    return created_hosts


@pytest.fixture(scope="function")
def mq_create_deleted_hosts(mq_create_or_update_host):
    with patch("app.models.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(
            year=2023, month=4, day=2, hour=1, minute=1, second=1, tzinfo=timezone.utc
        )
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        staleness_timestamps = get_staleness_timestamps()
        created_hosts = {}
        for state, timestamp in staleness_timestamps.items():
            host = minimal_host(
                insights_id=generate_uuid(),
                stale_timestamp=timestamp.isoformat(),
                reporter="some reporter",
                facts=FACTS,
            )
            created_hosts[state] = mq_create_or_update_host(host)

        return created_hosts


@pytest.fixture(scope="function")
def kafka_producer(mocker):
    kafka_producer = mocker.patch("app.queue.event_producer.KafkaProducer")
    yield kafka_producer


# Creating a second kafka producer so the event producer and the
# notification event producer can act separately in the tests
@pytest.fixture(scope="function")
def notification_kafka_producer(mocker):
    kafka_producer = mocker.patch("app.queue.event_producer.KafkaProducer")
    yield kafka_producer


@pytest.fixture(scope="function")
def event_producer(flask_app, kafka_producer):  # noqa: ARG001
    config = flask_app.app.config["INVENTORY_CONFIG"]
    flask_app.app.event_producer = EventProducer(config, config.event_topic)
    yield flask_app.app.event_producer
    flask_app.app.event_producer = None


@pytest.fixture(scope="function")
def notification_event_producer(flask_app, notification_kafka_producer):  # noqa: ARG001
    config = flask_app.app.config["INVENTORY_CONFIG"]
    flask_app.app.notification_event_producer = EventProducer(config, config.notification_topic)
    yield flask_app.app.notification_event_producer
    flask_app.app.notification_event_producer = None


@pytest.fixture(scope="function")
def event_producer_mock(flask_app, mocker):
    flask_app.app.event_producer = MockEventProducer()
    mocker.patch("lib.host_delete.kafka_available")
    yield flask_app.app.event_producer
    flask_app.app.event_producer = None


@pytest.fixture(scope="function")
def notification_event_producer_mock(flask_app, mocker):
    flask_app.app.notification_event_producer = MockEventProducer()
    mocker.patch("lib.host_delete.kafka_available")
    yield flask_app.app.notification_event_producer
    flask_app.app.notification_event_producer = None


@pytest.fixture(scope="function")
def future_mock():
    yield MockFuture()


@pytest.fixture(scope="function")
def event_datetime_mock(mocker):
    mock = mocker.patch("app.queue.events.datetime", **{"now.return_value": now()})
    return mock.now.return_value


@pytest.fixture(scope="function")
def mq_create_or_update_host_subman_id(
    flask_app,  # noqa: ARG001
    event_producer_mock,
    notification_event_producer_mock,
):
    config = flask_app.app.config["INVENTORY_CONFIG"]
    config.use_sub_man_id_for_host_id = True
    flask_app.app.config["USE_SUBMAN_ID"] = config.use_sub_man_id_for_host_id

    def _mq_create_or_update_host_subman_id(
        host_data,
        platform_metadata=None,
        return_all_data=False,
        event_producer=event_producer_mock,
        message_operation=add_host,
        operation_args=None,
        notification_event_producer=notification_event_producer_mock,
    ):
        if not platform_metadata:
            platform_metadata = get_platform_metadata()

        message = wrap_message(host_data.data(), platform_metadata=platform_metadata, operation_args=operation_args)
        result = handle_message(json.dumps(message), notification_event_producer, message_operation)
        db.session.commit()
        write_add_update_event_message(event_producer, notification_event_producer_mock, result)
        event = json.loads(event_producer.event)

        if return_all_data:
            return event_producer_mock.key, event, event_producer.headers

        # add facts object since it's not returned by event message
        return HostWrapper({**event["host"], **{"facts": host_data.facts}})

    return _mq_create_or_update_host_subman_id
