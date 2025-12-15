# mypy: disallow-untyped-defs

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch
from uuid import UUID

import pytest
from confluent_kafka import KafkaException
from connexion import FlaskApp
from pytest_mock import MockFixture
from sqlalchemy.orm import Query

from app.config import Config
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.culling import should_host_stay_fresh_forever
from app.logging import threadctx
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.models import Staleness
from app.models import db
from app.queue.event_producer import EventProducer
from jobs.host_reaper import run as host_reaper_run
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.mq_utils import assert_delete_notification_is_valid
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid

CUSTOM_STALENESS_DELETE = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": 1,
}

CUSTOM_STALENESS_NO_HOSTS_TO_DELETE = {
    "conventional_time_to_stale": CONVENTIONAL_TIME_TO_STALE_SECONDS,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


@pytest.mark.host_reaper
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.parametrize(
    "is_host_grouped",
    (True, False),
)
@pytest.mark.parametrize(
    "reporter,should_be_removed",
    (
        ("puptoo", True),
        ("rhsm-system-profile-bridge", False),
    ),
)
def test_culled_host_is_removed(
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    event_datetime_mock: datetime,
    notification_event_producer_mock: MockEventProducer,
    inventory_config: Config,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
    db_create_group: Callable[..., Group],
    db_create_host_group_assoc: Callable[..., HostGroupAssoc],
    host_type: str,
    is_host_grouped: bool,
    reporter: str,
    should_be_removed: bool,
) -> None:
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1, tzinfo=UTC)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        system_profile = {"host_type": host_type} if host_type == "edge" else {}
        host = minimal_db_host(reporter=reporter, system_profile_facts=system_profile)
        created_host = db_create_host(host=host)

        if is_host_grouped:
            group = db_create_group("test_group")
            db_create_host_group_assoc(created_host.id, group.id)

    assert db_get_host(created_host.id)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer=event_producer_mock,
        notification_event_producer=notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    if should_be_removed:
        assert not db_get_host(created_host.id)
        assert_delete_event_is_valid(
            event_producer=event_producer_mock,
            host=created_host,
            timestamp=event_datetime_mock,
            identity=None,
        )
        assert_delete_notification_is_valid(
            notification_event_producer=notification_event_producer_mock, host=created_host
        )
    else:
        assert db_get_host(created_host.id)
        assert event_producer_mock.event is None
        assert notification_event_producer_mock.event is None


@pytest.mark.host_reaper
@pytest.mark.parametrize("host_type", ["conventional", "edge"])
@pytest.mark.parametrize(
    "is_host_grouped",
    (True, False),
)
@pytest.mark.parametrize("reporter", ["puptoo", "rhsm-system-profile-bridge"])
def test_non_culled_host_is_not_removed(
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    inventory_config: Config,
    db_create_host: Callable[..., Host],
    db_get_hosts: Callable[..., Query],
    db_create_group: Callable[..., Group],
    db_create_host_group_assoc: Callable[..., HostGroupAssoc],
    host_type: str,
    is_host_grouped: bool,
    reporter: str,
) -> None:
    created_hosts = []

    for time_delta in (
        0,  # Fresh host
        CONVENTIONAL_TIME_TO_STALE_SECONDS,  # Stale host
        CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,  # Stale warning host
    ):
        with patch("app.models.utils.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now(UTC) - timedelta(seconds=time_delta)
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            system_profile = {"host_type": host_type} if host_type == "edge" else {}
            host = minimal_db_host(reporter=reporter, system_profile_facts=system_profile)
            created_host = db_create_host(host=host)

            if is_host_grouped:
                group = db_create_group("test_group")
                db_create_host_group_assoc(created_host.id, group.id)

            created_hosts.append(created_host)

    created_host_ids = sorted(host.id for host in created_hosts)
    retrieved_hosts = db_get_hosts(created_host_ids)

    assert created_host_ids == sorted(host.id for host in retrieved_hosts)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    retrieved_hosts = db_get_hosts(created_host_ids)

    assert created_host_ids == sorted(host.id for host in retrieved_hosts)
    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None


@pytest.mark.host_reaper
def test_reaper_shutdown_handler(
    flask_app: FlaskApp,
    inventory_config: Config,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_get_hosts: Callable[..., Query],
) -> None:
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        created_host_ids = []

        host_count = 3
        for _ in range(host_count):
            host_data = minimal_db_host(reporter="puptoo")
            created_host = db_create_host(host=host_data)
            created_host_ids.append(created_host.id)

    created_hosts = db_get_hosts(created_host_ids)
    assert created_hosts.count() == host_count

    fake_event_producer = mock.Mock()

    threadctx.request_id = None
    inventory_config.host_delete_chunk_size = 1

    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        fake_event_producer,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.side_effect": (False, False, True)}),
        application=flask_app,
    )

    remaining_hosts = db_get_hosts(created_host_ids)
    assert remaining_hosts.count() == 1
    assert fake_event_producer.write_event.call_count == 2


@pytest.mark.host_reaper
def test_unknown_host_is_not_removed(
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host_in_unknown_state: Host,
    inventory_config: Config,
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    created_host = db_create_host_in_unknown_state
    retrieved_host = db_get_host(created_host.id)

    assert retrieved_host
    assert retrieved_host.stale_timestamp is None
    assert retrieved_host.reporter is None

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None

    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host


def assert_system_culling_data(
    response_host: dict,
    expected_stale_timestamp: datetime,
    expected_reporter: str,
) -> None:
    assert "stale_timestamp" in response_host
    assert "stale_warning_timestamp" in response_host
    assert "culled_timestamp" in response_host
    assert "reporter" in response_host
    assert response_host["stale_timestamp"] == expected_stale_timestamp.isoformat()
    assert response_host["stale_warning_timestamp"] == (expected_stale_timestamp + timedelta(weeks=1)).isoformat()
    assert response_host["culled_timestamp"] == (expected_stale_timestamp + timedelta(weeks=2)).isoformat()
    assert response_host["reporter"] == expected_reporter


@pytest.mark.host_reaper
@pytest.mark.parametrize(
    "produce_side_effects",
    ((mock.Mock(), KafkaException()), (mock.Mock(), KafkaException("oops"))),
)
def test_reaper_stops_after_kafka_producer_error(
    flask_app: FlaskApp,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    inventory_config: Config,
    mocker: MockFixture,
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_hosts: Callable[..., Query],
    produce_side_effects: tuple[mock.Mock, Exception],
) -> None:
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mocker.patch("lib.host_delete.kafka_available")

        event_producer._kafka_producer.produce.side_effect = produce_side_effects

        host_count = 3
        created_hosts = db_create_multiple_hosts(how_many=host_count, extra_data={"reporter": "puptoo"})
        created_host_ids = [str(host.id) for host in created_hosts]

    hosts = db_get_hosts(created_host_ids)
    assert hosts.count() == host_count

    threadctx.request_id = None
    inventory_config.host_delete_chunk_size = 1

    with pytest.raises(KafkaException):
        host_reaper_run(
            inventory_config,
            mock.Mock(),
            db.session,
            event_producer,
            notification_event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

    remaining_hosts = db_get_hosts(created_host_ids)
    assert remaining_hosts.count() == 2
    assert event_producer._kafka_producer.produce.call_count == 2
    assert notification_event_producer._kafka_producer.produce.call_count == 1


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_host_with_rhsm_conduit_and_other_reporters_can_be_culled(
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    event_datetime_mock: datetime,
    inventory_config: Config,
    flask_app: FlaskApp,
) -> None:
    """Test that hosts with rhsm-system-profile-bridge AND other reporters can still be culled normally."""

    # Create a host with rhsm-system-profile-bridge AND other reporters
    past_time = datetime.now(UTC) - timedelta(days=30)

    mixed_reporter_host = Host(
        subscription_manager_id=generate_uuid(),
        insights_id=generate_uuid(),
        display_name="mixed-reporter-host",
        reporter="rhsm-system-profile-bridge",
        org_id=USER_IDENTITY["org_id"],
    )
    mixed_reporter_host.last_check_in = past_time
    mixed_reporter_host.stale_timestamp = past_time
    mixed_reporter_host.stale_warning_timestamp = past_time
    mixed_reporter_host.deletion_timestamp = past_time
    mixed_reporter_host.per_reporter_staleness = {
        "rhsm-system-profile-bridge": {
            "last_check_in": past_time.isoformat(),
            "stale_timestamp": past_time.isoformat(),
            "stale_warning_timestamp": past_time.isoformat(),
            "culled_timestamp": past_time.isoformat(),
            "check_in_succeeded": True,
        },
        "puptoo": {
            "last_check_in": past_time.isoformat(),
            "stale_timestamp": past_time.isoformat(),
            "stale_warning_timestamp": past_time.isoformat(),
            "culled_timestamp": past_time.isoformat(),
            "check_in_succeeded": True,
        },
    }

    created_mixed_host = db_create_host(host=mixed_reporter_host)

    # This host should be eligible for deletion since it has multiple reporters
    assert should_host_stay_fresh_forever(created_mixed_host) is False

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    assert not db_get_host(created_mixed_host.id)
    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=created_mixed_host,
        timestamp=event_datetime_mock,
        identity=None,
    )
    assert_delete_notification_is_valid(
        notification_event_producer=notification_event_producer_mock, host=created_mixed_host
    )


@pytest.mark.parametrize(
    "reporters",
    [
        ["rhsm-system-profile-bridge"],  # Should be excluded
        ["rhsm-system-profile-bridge", "puptoo"],  # Should NOT be excluded
        ["rhsm-system-profile-bridge", "cloud-connector", "yuptoo"],  # Should NOT be excluded
        ["puptoo"],  # Should NOT be excluded
    ],
)
def test_host_reaper_filter_logic_parametrized(reporters: list[str]) -> None:
    """Parametrized test for host reaper filter logic."""
    host = Host(
        subscription_manager_id=generate_uuid(),
        display_name="test-host",
        reporter=reporters[0],
        stale_timestamp=datetime.now(UTC),
        org_id=USER_IDENTITY["org_id"],
    )

    per_reporter_staleness = {
        reporter: {
            "last_check_in": datetime.now(UTC).isoformat(),
            "stale_timestamp": datetime.now(UTC).isoformat(),
            "check_in_succeeded": True,
        }
        for reporter in reporters
    }
    host.per_reporter_staleness = per_reporter_staleness

    # Only hosts with ONLY rhsm-system-profile-bridge should stay fresh forever
    if len(reporters) == 1 and reporters[0] == "rhsm-system-profile-bridge":
        assert should_host_stay_fresh_forever(host) is True
    else:
        assert should_host_stay_fresh_forever(host) is False


def test_delete_all_type_of_hosts(
    flask_app: FlaskApp,
    inventory_config: Config,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_hosts: Callable[..., Query],
) -> None:
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE)

    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.now(UTC) - timedelta(minutes=1)
        immutable_hosts = db_create_multiple_hosts(
            how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}, "reporter": "puptoo"}
        )
        immutable_hosts = [host.id for host in immutable_hosts]
        conventional_hosts = db_create_multiple_hosts(how_many=2, extra_data={"reporter": "puptoo"})
        conventional_hosts = [host.id for host in conventional_hosts]

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )
    assert len(db_get_hosts(immutable_hosts).all()) == 0
    assert len(db_get_hosts(conventional_hosts).all()) == 0


def test_no_hosts_to_delete(
    flask_app: FlaskApp,
    inventory_config: Config,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_staleness_culling: Callable[..., Staleness],
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_hosts: Callable[..., Query],
) -> None:
    db_create_staleness_culling(**CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)

    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.now() - timedelta(minutes=1)
        immutable_hosts = db_create_multiple_hosts(
            how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}}
        )
        immutable_hosts = [host.id for host in immutable_hosts]
        conventional_hosts = db_create_multiple_hosts(how_many=2)
        conventional_hosts = [host.id for host in conventional_hosts]

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )
    assert len(db_get_hosts(immutable_hosts).all()) == 2
    assert len(db_get_hosts(conventional_hosts).all()) == 2


def test_host_reaper_doesnt_use_updated_timestamp(
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    event_datetime_mock: datetime,
    notification_event_producer_mock: MockEventProducer,
    inventory_config: Config,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID | str], Host | None],
) -> None:
    """Test that host reaper doesn't use 'updated' timestamp to determine if a host should be culled."""

    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1, tzinfo=UTC)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        host = minimal_db_host(reporter="puptoo")
        host.updated = datetime.now(UTC)
        created_host = db_create_host(host=host)

    retrieved_host = db_get_host(created_host.id)
    assert retrieved_host
    assert retrieved_host.updated >= datetime.now(UTC) - timedelta(seconds=1)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer=event_producer_mock,
        notification_event_producer=notification_event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        application=flask_app,
    )

    assert not db_get_host(created_host.id)
    assert_delete_event_is_valid(
        event_producer=event_producer_mock,
        host=created_host,
        timestamp=event_datetime_mock,
        identity=None,
    )
    assert_delete_notification_is_valid(
        notification_event_producer=notification_event_producer_mock, host=created_host
    )
