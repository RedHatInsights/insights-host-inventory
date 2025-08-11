from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import pytest
import pytz
from confluent_kafka import KafkaException

from app.culling import should_host_stay_fresh_forever
from app.logging import threadctx
from app.models import Host
from app.models import db
from host_reaper import run as host_reaper_run
from tests.helpers.api_utils import build_facts_url
from tests.helpers.api_utils import build_host_tags_url
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.api_utils import build_tags_count_url
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import assert_delete_event_is_valid
from tests.helpers.mq_utils import assert_delete_notification_is_valid
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_staleness_timestamps


def test_dont_get_only_culled(api_get):
    url = build_hosts_url(query="?staleness=culled")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_fail_patch_culled_host(mq_create_deleted_hosts, api_patch):
    culled_host = mq_create_deleted_hosts["culled"]

    url = build_hosts_url(host_list_or_id=[culled_host])
    response_status, _ = api_patch(url, {"display_name": "patched"})

    assert response_status == 404


def test_patch_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_hosts_url(host_list_or_id=[fresh_host])
    response_status, _ = api_patch(url, {"display_name": "patched"})

    assert response_status == 200


def test_patch_facts_ignores_culled(mq_create_deleted_hosts, api_patch):
    culled_host = mq_create_deleted_hosts["culled"]
    url = build_facts_url(host_list_or_id=[culled_host], namespace="ns1")
    response_status, _ = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 404


def test_patch_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_patch):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list_or_id=[fresh_host], namespace="ns1")
    response_status, response_data = api_patch(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_put_facts_ignores_culled(mq_create_deleted_hosts, api_put):
    culled_host = mq_create_deleted_hosts["culled"]

    url = build_facts_url(host_list_or_id=[culled_host], namespace="ns1")

    response_status, _ = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 404


def test_put_facts_works_on_non_culled(mq_create_hosts_in_all_states, api_put):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    url = build_facts_url(host_list_or_id=[fresh_host], namespace="ns1")
    response_status, _ = api_put(url, {"ARCHITECTURE": "patched"})

    assert response_status == 200


def test_delete_ignores_culled(mq_create_deleted_hosts, api_delete_host):
    culled_host = mq_create_deleted_hosts["culled"]

    response_status, _ = api_delete_host(culled_host.id)

    assert response_status == 404


def test_delete_works_on_non_culled(mq_create_hosts_in_all_states, api_delete_host):
    fresh_host = mq_create_hosts_in_all_states["fresh"]

    response_status, _ = api_delete_host(fresh_host.id)

    assert response_status == 200


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_get_host_by_id_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_hosts_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_tags_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_host_tags_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_tags_count_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_tags_count_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.skip(reason="bypass until the issue, https://github.com/spec-first/connexion/issues/1920 is resolved")
def test_system_profile_doesnt_use_staleness_parameter(mq_create_hosts_in_all_states, api_get):
    created_hosts = mq_create_hosts_in_all_states

    url = build_system_profile_url(host_list_or_id=created_hosts)
    response_status, _ = api_get(url, query_parameters={"staleness": "fresh"})

    assert response_status == 400


@pytest.mark.host_reaper
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
    flask_app,
    event_producer_mock,
    event_datetime_mock,
    notification_event_producer_mock,
    db_create_host,
    db_get_host,
    db_create_group,
    db_create_host_group_assoc,
    inventory_config,
    is_host_grouped,
    reporter,
    should_be_removed,
):
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(
            year=2023, month=4, day=2, hour=1, minute=1, second=1, tzinfo=pytz.utc
        )
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        staleness_timestamps = get_staleness_timestamps()

        host = minimal_db_host(stale_timestamp=staleness_timestamps["culled"], reporter=reporter)
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
def test_culled_edge_host_is_not_removed(
    flask_app, event_producer_mock, notification_event_producer_mock, db_create_host, db_get_host, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()

    host = minimal_db_host(
        stale_timestamp=staleness_timestamps["culled"],
        reporter="some reporter",
        system_profile_facts={"host_type": "edge"},
    )
    created_host_id = db_create_host(host=host).id

    assert db_get_host(created_host_id)

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

    assert db_get_host(created_host_id)
    assert event_producer_mock.event is None
    assert notification_event_producer_mock.event is None


@pytest.mark.host_reaper
def test_non_culled_host_is_not_removed(
    flask_app, event_producer_mock, notification_event_producer_mock, db_create_host, db_get_hosts, inventory_config
):
    staleness_timestamps = get_staleness_timestamps()
    created_hosts = []

    for stale_timestamp in (
        staleness_timestamps["stale_warning"],
        staleness_timestamps["stale"],
        staleness_timestamps["fresh"],
    ):
        host = minimal_db_host(stale_timestamp=stale_timestamp, reporter="some reporter")
        created_host = db_create_host(host=host)
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
    flask_app, db_create_host, db_get_hosts, inventory_config, notification_event_producer_mock
):
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        staleness_timestamps = get_staleness_timestamps()
        created_host_ids = []

        host_count = 3
        for _ in range(host_count):
            host_data = minimal_db_host(stale_timestamp=staleness_timestamps["culled"], reporter="puptoo")
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
    flask_app,
    event_producer_mock,
    notification_event_producer_mock,
    db_create_host_in_unknown_state,
    db_get_host,
    inventory_config,
):
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


def assert_system_culling_data(response_host, expected_stale_timestamp, expected_reporter):
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
    flask_app,
    produce_side_effects,
    event_producer,
    notification_event_producer,
    db_create_multiple_hosts,
    db_get_hosts,
    inventory_config,
    mocker,
):
    with patch("app.models.utils.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(year=2023, month=4, day=2, hour=1, minute=1, second=1)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mocker.patch("lib.host_delete.kafka_available")

        event_producer._kafka_producer.produce.side_effect = produce_side_effects

        staleness_timestamps = get_staleness_timestamps()

        host_count = 3
        created_hosts = db_create_multiple_hosts(
            how_many=host_count, extra_data={"stale_timestamp": staleness_timestamps["culled"], "reporter": "puptoo"}
        )
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
def test_host_with_rhsm_conduit_and_other_reporters_can_be_culled(db_create_host):
    """Test that hosts with rhsm-system-profile-bridge AND other reporters can still be culled normally."""

    # Create a host with rhsm-system-profile-bridge AND other reporters
    past_time = datetime.now(UTC) - timedelta(days=30)

    mixed_reporter_host = Host(
        canonical_facts={"subscription_manager_id": generate_uuid()},
        display_name="mixed-reporter-host",
        reporter="rhsm-system-profile-bridge",
        stale_timestamp=past_time,
        org_id=USER_IDENTITY["org_id"],
    )
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


@pytest.mark.parametrize(
    "reporters",
    [
        ["rhsm-system-profile-bridge"],  # Should be excluded
        ["rhsm-system-profile-bridge", "puptoo"],  # Should NOT be excluded
        ["rhsm-system-profile-bridge", "cloud-connector", "yuptoo"],  # Should NOT be excluded
        ["puptoo"],  # Should NOT be excluded
    ],
)
def test_host_reaper_filter_logic_parametrized(reporters):
    """Parametrized test for host reaper filter logic."""
    host = Host(
        canonical_facts={"subscription_manager_id": generate_uuid()},
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
