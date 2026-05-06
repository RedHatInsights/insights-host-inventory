import json
from collections.abc import Callable
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import pytest
from connexion import FlaskApp
from pytest_mock import MockFixture

from api.staleness_query import get_staleness_obj
from app.config import Config
from app.models import Host
from app.models import db
from app.queue.event_producer import EventProducer
from app.queue.export_service_mq import ExportServiceConsumer
from app.queue.host_mq import HostAppMessageConsumer
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import SystemProfileMessageConsumer
from app.queue.host_mq import WorkspaceMessageConsumer
from app.queue.host_mq import write_add_update_event_message
from app.serialization import serialize_staleness_to_dict
from app.utils import HostWrapper
from tests.helpers.api_utils import FACTS
from tests.helpers.api_utils import TAGS
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import MockFuture
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import base_host
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import get_staleness_timestamps
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.fixture(scope="function")
def mq_create_or_update_host(
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
) -> Callable:
    def _mq_create_or_update_host(
        host_data,
        platform_metadata=None,
        return_all_data=False,
        event_producer=event_producer_mock,
        consumer_class=IngressMessageConsumer,
        operation_args=None,
        notification_event_producer=notification_event_producer_mock,
        identity=SYSTEM_IDENTITY,
    ):
        if not platform_metadata:
            platform_metadata = get_platform_metadata(identity=identity)

        message = wrap_message(host_data.data(), platform_metadata=platform_metadata, operation_args=operation_args)
        consumer = consumer_class(None, flask_app, event_producer_mock, notification_event_producer)
        result = consumer.handle_message(json.dumps(message))
        db.session.commit()
        write_add_update_event_message(event_producer, notification_event_producer, result)
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
            insights_id=generate_uuid(),
            subscription_manager_id=generate_uuid(),
            display_name=f"host{i}",
            fqdn=fqdn,
            facts=FACTS,
            tags=TAGS[i - 1],
        )
        created_host = mq_create_or_update_host(host)

        if i == 2:
            # Update second host to duplicate the FQDN of the first.
            # We do this in the loop as to not change the create/update order.
            host = minimal_host(
                insights_id=created_host.insights_id,
                display_name=created_host.display_name,
                subscription_manager_id=created_host.subscription_manager_id,
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
def mq_create_edge_host(mq_create_or_update_host):
    host = base_host(
        insights_id=generate_uuid(),
        subscription_manager_id=generate_uuid(),
        display_name="host-edge",
        fqdn="host-edge.domain.test",
        facts=FACTS,
        tags=TAGS[0],
        system_profile={
            "arch": "x86_64",
            "insights_client_version": "3.0.1-2.el4_2",
            "host_type": "edge",
            "sap": {"sap_system": True, "sids": ["ABC", "DEF"]},
        },
    )

    return mq_create_or_update_host(host)


@pytest.fixture(scope="function")
def mq_create_hosts_in_all_states(mq_create_or_update_host):
    staleness_states = get_staleness_timestamps().keys()
    created_hosts = {}
    for state in staleness_states:
        host = minimal_host(insights_id=generate_uuid(), reporter="some reporter", facts=FACTS)
        created_hosts[state] = mq_create_or_update_host(host)

    return created_hosts


@pytest.fixture(scope="function")
def mq_create_deleted_hosts(flask_app: FlaskApp, mq_create_or_update_host):
    """Hosts are compute-on-read culled: ``last_check_in`` is past org ``conventional_time_to_delete``."""
    staleness_states = get_staleness_timestamps().keys()
    created_hosts = {}

    with flask_app.app.app_context():
        org_id = SYSTEM_IDENTITY["org_id"]
        staleness = serialize_staleness_to_dict(get_staleness_obj(org_id))
        delete_seconds = staleness["conventional_time_to_delete"]
        last_check_in_culled = datetime.now(tz=UTC) - timedelta(seconds=delete_seconds + 3600)

    for state in staleness_states:
        host = minimal_host(
            insights_id=generate_uuid(),
            reporter="some reporter",
            facts=FACTS,
        )
        hw = mq_create_or_update_host(host)
        with flask_app.app.app_context():
            row = db.session.query(Host).filter_by(id=UUID(str(hw.id)), org_id=hw.org_id).one()
            row.last_check_in = last_check_in_culled
            db.session.commit()
        created_hosts[state] = hw

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
def event_producer(flask_app: FlaskApp, kafka_producer) -> Generator[EventProducer]:  # noqa: ARG001
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
def event_producer_mock(flask_app: FlaskApp, mocker: MockFixture) -> Generator[MockEventProducer]:
    flask_app.app.event_producer = MockEventProducer()
    mocker.patch("lib.host_delete.kafka_available")
    yield flask_app.app.event_producer
    flask_app.app.event_producer = None


@pytest.fixture(scope="function")
def notification_event_producer_mock(flask_app: FlaskApp, mocker: MockFixture) -> Generator[MockEventProducer]:
    flask_app.app.notification_event_producer = MockEventProducer()
    mocker.patch("lib.host_delete.kafka_available")
    yield flask_app.app.notification_event_producer
    flask_app.app.notification_event_producer = None


@pytest.fixture(scope="function")
def ingress_message_consumer_mock(mocker):
    yield IngressMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mocker.Mock())


@pytest.fixture(scope="function")
def system_profile_consumer_mock(mocker):
    yield SystemProfileMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mocker.Mock())


@pytest.fixture(scope="function")
def export_service_consumer_mock(mocker):
    yield ExportServiceConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mocker.Mock())


@pytest.fixture(scope="function")
def workspace_message_consumer_mock(mocker):
    mocker.patch("app.queue.host_mq._pg_notify_workspace")
    yield WorkspaceMessageConsumer(mocker.Mock(), mocker.Mock(), mocker.Mock(), mocker.Mock())


@pytest.fixture(scope="function")
def host_app_consumer(flask_app, event_producer, mocker):
    """Fixture to create HostAppMessageConsumer for testing."""
    yield HostAppMessageConsumer(mocker.Mock(), flask_app, event_producer, mocker.Mock())


@pytest.fixture(scope="function")
def future_mock():
    yield MockFuture()


@pytest.fixture(scope="function")
def event_datetime_mock(mocker):
    mock = mocker.patch("app.queue.events.datetime", **{"now.return_value": now()})
    return mock.now.return_value


@pytest.fixture(scope="function")
def mq_create_or_update_host_subman_id(
    flask_app: FlaskApp,
    inventory_config: Config,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
):
    inventory_config.use_sub_man_id_for_host_id = True
    flask_app.app.config["USE_SUBMAN_ID"] = True

    def _mq_create_or_update_host_subman_id(
        host_data,
        platform_metadata=None,
        return_all_data=False,
        event_producer=event_producer_mock,
        operation_args=None,
        consumer_class=IngressMessageConsumer,
        notification_event_producer=notification_event_producer_mock,
    ):
        if not platform_metadata:
            platform_metadata = get_platform_metadata()

        message = wrap_message(host_data.data(), platform_metadata=platform_metadata, operation_args=operation_args)
        consumer = consumer_class(None, flask_app, event_producer_mock, notification_event_producer)
        result = consumer.handle_message(json.dumps(message))
        db.session.commit()
        write_add_update_event_message(event_producer, notification_event_producer_mock, result)
        event = json.loads(event_producer.event)

        if return_all_data:
            return event_producer_mock.key, event, event_producer.headers

        # add facts object since it's not returned by event message
        return HostWrapper({**event["host"], **{"facts": host_data.facts}})

    return _mq_create_or_update_host_subman_id
