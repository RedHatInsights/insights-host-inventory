import json

import pytest

from app.queue.queue import handle_message
from app.utils import HostWrapper
from tests.helpers.api_utils import FACTS
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_staleness_timestamps
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


@pytest.fixture(scope="function")
def mq_create_or_update_host(flask_app, event_producer_mock):
    def _mq_create_or_update_host(
        host_data, platform_metadata=None, return_all_data=False, event_producer=event_producer_mock
    ):
        message = wrap_message(host_data.data(), platform_metadata=platform_metadata)
        handle_message(json.dumps(message), event_producer)
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
        fqdn = "host1.domain.test" if i in (1, 2) else f"host{i}.domain.test"
        display_name = f"host{i}"
        host = minimal_host(insights_id=generate_uuid(), display_name=display_name, fqdn=fqdn, facts=FACTS)
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
def event_producer_mock(flask_app):
    flask_app.event_producer = MockEventProducer()
    yield flask_app.event_producer
    flask_app.event_producer = None


@pytest.fixture(scope="function")
def event_datetime_mock(mocker):
    mock = mocker.patch("app.queue.events.datetime", **{"now.return_value": now()})
    return mock.now.return_value
