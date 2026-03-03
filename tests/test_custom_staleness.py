from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Query

from api.host_query import staleness_timestamps
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Host
from app.models import db
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from app.serialization import _serialize_per_reporter_staleness
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_host_with_reporter
from tests.helpers.api_utils import create_reporter_data
from tests.helpers.outbox_utils import wait_for_all_events
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now

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

CUSTOM_STALENESS_HOST_BECAME_STALE = {
    "conventional_time_to_stale": 1,
    "conventional_time_to_stale_warning": CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS,
    "conventional_time_to_delete": CONVENTIONAL_TIME_TO_DELETE_SECONDS,
}


@pytest.mark.parametrize("num_hosts", [1, 2, 3])
def test_async_update_host_create_custom_staleness(
    db_get_hosts, db_create_multiple_hosts, api_get, api_post, flask_app, event_producer, mocker, num_hosts
):
    with (
        patch("app.models.utils.datetime") as mock_datetime,
    ):
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_NO_HOSTS_TO_DELETE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_before_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            staleness_url = build_staleness_url()
            status, _ = api_post(staleness_url, CUSTOM_STALENESS_HOST_BECAME_STALE)
            assert status == 201

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_after_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            # Call event_producer
            assert event_producer.write_event.call_count == num_hosts


@pytest.mark.parametrize("num_hosts", [1, 2, 3])
def test_async_update_host_delete_custom_staleness(
    db_create_staleness_culling,
    db_get_hosts,
    db_create_multiple_hosts,
    api_get,
    api_delete_staleness,
    flask_app,
    event_producer,
    mocker,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with (
        patch("app.models.utils.datetime") as mock_datetime,
    ):
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_before_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            status, _ = api_delete_staleness()
            assert status == 204

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_NO_HOSTS_TO_DELETE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_after_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            # Call event_producer
            assert event_producer.write_event.call_count == num_hosts


@pytest.mark.parametrize("num_hosts", [1, 2, 3])
def test_async_update_host_update_custom_staleness(
    db_create_staleness_culling,
    db_get_hosts,
    db_create_multiple_hosts,
    api_get,
    api_patch,
    flask_app,
    event_producer,
    mocker,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with (
        patch("app.models.utils.datetime") as mock_datetime,
    ):
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_before_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            staleness_url = build_staleness_url()
            status, _ = api_patch(staleness_url, CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)
            assert status == 200

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_NO_HOSTS_TO_DELETE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_after_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            # Call event_producer
            assert event_producer.write_event.call_count == num_hosts


@pytest.mark.parametrize("num_hosts", [1, 2, 3])
def test_async_update_host_update_custom_staleness_no_modified_on_change(
    db_create_staleness_culling,
    db_get_hosts,
    db_create_multiple_hosts,
    api_patch,
    flask_app,
    event_producer,
    mocker,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with (
        patch("app.models.utils.datetime") as mock_datetime,
    ):
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now
            hosts_before_update = db_create_multiple_hosts(how_many=num_hosts)

            for reporter in hosts_before_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_before_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp

            staleness_url = build_staleness_url()
            status, _ = api_patch(staleness_url, CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)
            assert status == 200

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            host_ids = [str(host.id) for host in hosts_before_update]

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                stale_timestamp = _now + timedelta(
                    seconds=CUSTOM_STALENESS_NO_HOSTS_TO_DELETE["conventional_time_to_stale"]
                )
                stale_timestamp = stale_timestamp.isoformat()
                assert hosts_after_update[0].per_reporter_staleness[reporter]["stale_timestamp"] == stale_timestamp
                assert hosts_after_update[0].modified_on == hosts_before_update[0].modified_on

            # Call event_producer
            assert event_producer.write_event.call_count == num_hosts


# ================================
# NESTED FORMAT TESTS (these can be removed after RHINENG-21703 is completed)
# ================================


def test_registered_with_filter_handles_multi_reporter_hosts(
    db_create_staleness_culling,
    db_create_host,
    api_get,
    flask_app,
    event_producer,
    mocker,
):
    """Test registered_with filter behavior when a host has multiple reporters.

    This test creates hosts with multiple reporters, makes some culled via timestamp manipulation,
    and verifies that the registered_with filter correctly handles culled vs fresh reporters.
    """

    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as mock_datetime:
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now

            # Create a host with multiple reporters, including culled_timestamp
            _ = db_create_host(
                extra_data={
                    "reporter": "puptoo",  # Primary reporter
                    "per_reporter_staleness": {
                        # Fresh puptoo reporter (not culled)
                        "puptoo": {
                            "last_check_in": _now.isoformat(),
                            "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                            "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                            "check_in_succeeded": True,
                        },
                        # Fresh yupana reporter (not culled)
                        "yupana": {
                            "last_check_in": _now.isoformat(),
                            "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                            "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                            "check_in_succeeded": True,
                        },
                    },
                },
            )

    # Create a host with culled reporters
    db_create_host(
        extra_data={
            "reporter": "puptoo",
            "per_reporter_staleness": {
                "puptoo": {
                    "last_check_in": (_now - timedelta(days=30)).isoformat(),
                    "stale_timestamp": (_now - timedelta(days=23)).isoformat(),
                    "culled_timestamp": (_now - timedelta(days=16)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    )

    # Create a host with no puptoo/yupana (different reporter)
    db_create_host(
        extra_data={
            "reporter": "rhsm-conduit",
            "per_reporter_staleness": {
                "rhsm-conduit": {
                    "last_check_in": _now.isoformat(),
                    "stale_timestamp": (_now + timedelta(days=7)).isoformat(),
                    "culled_timestamp": (_now + timedelta(days=14)).isoformat(),
                    "check_in_succeeded": True,
                }
            },
        },
    )

    # Test filtering
    _, puptoo_hosts = api_get(build_hosts_url(query="?registered_with=puptoo"))
    _, yupana_hosts = api_get(build_hosts_url(query="?registered_with=yupana"))
    _, not_puptoo_hosts = api_get(build_hosts_url(query="?registered_with=!puptoo"))
    _, not_yupana_hosts = api_get(build_hosts_url(query="?registered_with=!yupana"))

    assert len(puptoo_hosts["results"]) == 1
    assert len(not_puptoo_hosts["results"]) == 2
    assert len(yupana_hosts["results"]) == 1
    assert len(not_yupana_hosts["results"]) == 2
    assert len(puptoo_hosts["results"]) + len(not_puptoo_hosts["results"]) == 3
    assert len(yupana_hosts["results"]) + len(not_yupana_hosts["results"]) == 3


def test_registered_with_filter_with_only_last_check_in(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    """
    Test that filtering works as expected
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    _now = now()
    fresh_last_check_in = _now
    puptoo_data = create_reporter_data(fresh_last_check_in, CUSTOM_STALENESS_HOST_BECAME_STALE)

    fresh_host = db_create_host(
        extra_data={"reporter": "puptoo", "per_reporter_staleness": {"puptoo": puptoo_data}},
    )
    fresh_host.last_check_in = fresh_last_check_in
    fresh_host.per_reporter_staleness["puptoo"]["last_check_in"] = fresh_last_check_in.isoformat()
    fresh_host_id = str(fresh_host.id)
    db.session.commit()

    other_host = db_create_host(
        extra_data={
            "reporter": "rhsm-conduit",
            "per_reporter_staleness": {
                "rhsm-conduit": create_reporter_data(fresh_last_check_in, CUSTOM_STALENESS_HOST_BECAME_STALE)
            },
        },
    )
    other_host.last_check_in = fresh_last_check_in
    other_host_id = str(other_host.id)
    db.session.commit()

    _, puptoo_hosts = api_get(build_hosts_url(query="?registered_with=puptoo"))
    _, not_puptoo_hosts = api_get(build_hosts_url(query="?registered_with=!puptoo"))

    assert len(puptoo_hosts["results"]) == 1
    assert len(not_puptoo_hosts["results"]) == 1
    assert fresh_host_id in {h["id"] for h in puptoo_hosts["results"]}
    assert other_host_id in {h["id"] for h in not_puptoo_hosts["results"]}


def test_calculated_timestamps_match_stored_timestamps(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    db_get_hosts: Callable[..., Query],
) -> None:
    """Verify calculated timestamps match expected values from last_check_in."""
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    _now = now()
    # Create a test host - normalize to UTC
    last_check_in = _now.astimezone(UTC) if _now.tzinfo else _now.replace(tzinfo=UTC)
    host = db_create_host(
        extra_data={
            "reporter": "puptoo",
            "per_reporter_staleness": {
                "puptoo": create_reporter_data(last_check_in, CUSTOM_STALENESS_HOST_BECAME_STALE)
            },
        },
    )
    host.last_check_in = last_check_in
    host.per_reporter_staleness["puptoo"]["last_check_in"] = last_check_in.isoformat()
    db.session.commit()

    # Get host from database and calculate timestamps
    db_host = db_get_hosts([str(host.id)]).first()
    staleness = get_sys_default_staleness()
    staleness_timestamps_obj = staleness_timestamps()
    calculated = get_reporter_staleness_timestamps(db_host, staleness_timestamps_obj, staleness, "puptoo")

    # Calculate expected timestamps
    from datetime import datetime as dt

    date_to_use = dt.fromisoformat(db_host.per_reporter_staleness["puptoo"]["last_check_in"])
    date_to_use = date_to_use.replace(tzinfo=UTC) if date_to_use.tzinfo is None else date_to_use.astimezone(UTC)

    expected = {
        "stale_timestamp": staleness_timestamps_obj.stale_timestamp(
            date_to_use, staleness["conventional_time_to_stale"]
        ),
        "stale_warning_timestamp": staleness_timestamps_obj.stale_warning_timestamp(
            date_to_use, staleness["conventional_time_to_stale_warning"]
        ),
        "culled_timestamp": staleness_timestamps_obj.culled_timestamp(
            date_to_use, staleness["conventional_time_to_delete"]
        ),
    }

    # Verify calculated timestamps match expected (within 2 seconds tolerance)
    for key in ["stale_timestamp", "stale_warning_timestamp", "culled_timestamp"]:
        calculated_ts = calculated[key]
        if calculated_ts.tzinfo is None:
            calculated_ts = calculated_ts.replace(tzinfo=UTC)
        else:
            calculated_ts = calculated_ts.astimezone(UTC)
        diff_seconds = abs((calculated_ts - expected[key]).total_seconds())
        assert diff_seconds <= 2


def test_registered_with_filter_missing_last_check_in(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    """
    Test that filtering works as expected when last_check_in is missing.
    Tests both positive (registered_with=puptoo) and negative (registered_with=!puptoo) filters.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    _now = now()
    # Create a host with reporter but missing last_check_in
    host_without_last_check_in_id = str(
        db_create_host(
            extra_data={
                "reporter": "puptoo",
                "per_reporter_staleness": {"puptoo": {"check_in_succeeded": True}},
            },
        ).id
    )

    # Normal host for comparison
    normal_host_id = str(
        create_host_with_reporter(
            db_create_host, "puptoo", _now, CUSTOM_STALENESS_HOST_BECAME_STALE, include_timestamps=False
        ).id
    )

    # Create a host with a different reporter for negative filter test
    other_host_id = str(
        db_create_host(
            extra_data={
                "reporter": "yupana",
                "per_reporter_staleness": {
                    "yupana": create_reporter_data(
                        _now,
                        CUSTOM_STALENESS_HOST_BECAME_STALE,
                        include_timestamps=False,
                    ),
                },
            },
        ).id
    )

    # Test positive filter: registered_with=puptoo
    _, puptoo_hosts = api_get(build_hosts_url(query="?registered_with=puptoo"))
    assert normal_host_id in {h["id"] for h in puptoo_hosts["results"]}
    assert host_without_last_check_in_id not in {h["id"] for h in puptoo_hosts["results"]}

    # Test negative filter: registered_with=!puptoo
    _, data = api_get(build_hosts_url(query="?registered_with=!puptoo"))
    assert data is not None
    returned_ids = {h["id"] for h in data["results"]}
    assert host_without_last_check_in_id not in returned_ids
    assert other_host_id in returned_ids


def test_rhsm_only_hosts_get_far_future_timestamp_in_sql_queries(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    _now = now()
    # Create an RHSM-only host
    rhsm_only_host_id = str(
        db_create_host(
            extra_data={
                "reporter": "rhsm-system-profile-bridge",
                "per_reporter_staleness": {
                    "rhsm-system-profile-bridge": create_reporter_data(
                        _now - timedelta(days=100),  # Very old check-in, but should stay fresh forever
                        CUSTOM_STALENESS_HOST_BECAME_STALE,
                    )
                },
            },
        ).id
    )

    # Create a host with RHSM + other reporter
    rhsm_with_other_id = str(
        db_create_host(
            extra_data={
                "reporter": "rhsm-system-profile-bridge",
                "per_reporter_staleness": {
                    "rhsm-system-profile-bridge": create_reporter_data(_now, CUSTOM_STALENESS_HOST_BECAME_STALE),
                    "puptoo": create_reporter_data(_now, CUSTOM_STALENESS_HOST_BECAME_STALE),
                },
            },
        ).id
    )

    old_check_in = _now - timedelta(days=100)
    create_host_with_reporter(
        db_create_host,
        "puptoo",
        old_check_in,
        CUSTOM_STALENESS_HOST_BECAME_STALE,
    )

    _, fresh_hosts = api_get(build_hosts_url(query="?staleness=fresh"))

    assert rhsm_only_host_id in {h["id"] for h in fresh_hosts["results"]}
    assert rhsm_with_other_id in {h["id"] for h in fresh_hosts["results"]}

    # RHSM-only host does NOT appear in "stale" or "stale_warning" staleness
    _, stale_hosts = api_get(build_hosts_url(query="?staleness=stale"))
    _, stale_warning_hosts = api_get(build_hosts_url(query="?staleness=stale_warning"))

    assert rhsm_only_host_id not in {h["id"] for h in stale_hosts["results"]}
    assert rhsm_only_host_id not in {h["id"] for h in stale_warning_hosts["results"]}


def test_serialize_per_reporter_staleness_datetime_string_format(flask_app):
    """Test that the per-reporter staleness serialization works with the datetime string format."""
    with flask_app.app.app_context():
        last_check_in_str = "2024-06-15T10:00:00+00:00"
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {"puptoo": last_check_in_str}
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        puptoo = result["puptoo"]
        assert isinstance(puptoo, dict)
        assert puptoo["last_check_in"] == last_check_in_str
        assert "stale_timestamp" in puptoo
        assert "stale_warning_timestamp" in puptoo
        assert "culled_timestamp" in puptoo


def test_serialize_per_reporter_staleness_stay_fresh_forever_string_format(flask_app):
    """
    When should_host_stay_fresh_forever(host) is True and per_reporter_staleness uses string format,
    the output has far-future timestamps.
    """
    with flask_app.app.app_context():
        last_check_in_str = "2024-06-15T10:00:00+00:00"
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="rhsm-system-profile-bridge",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {"rhsm-system-profile-bridge": last_check_in_str}
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        bridge = result["rhsm-system-profile-bridge"]
        assert isinstance(bridge, dict)
        assert bridge["last_check_in"] == last_check_in_str
        far_future_str = FAR_FUTURE_STALE_TIMESTAMP.isoformat()
        assert bridge["stale_timestamp"] == far_future_str
        assert bridge["stale_warning_timestamp"] == far_future_str
        assert bridge["culled_timestamp"] == far_future_str


def test_serialize_per_reporter_staleness_datetime_object_format(flask_app):
    """Test that per_reporter_staleness with a datetime object (not string) serializes correctly."""
    with flask_app.app.app_context():
        last_check_in_dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {"puptoo": last_check_in_dt}
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        puptoo = result["puptoo"]
        assert isinstance(puptoo, dict)
        assert puptoo["last_check_in"] == "2024-06-15T10:00:00+00:00"
        assert "stale_timestamp" in puptoo
        assert "stale_warning_timestamp" in puptoo
        assert "culled_timestamp" in puptoo


def test_serialize_per_reporter_staleness_mixed_formats(flask_app):
    """One reporter uses old format (dict), another uses new format (string); both serialize correctly."""
    with flask_app.app.app_context():
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": {
                "last_check_in": "2024-06-15T10:00:00+00:00",
                "check_in_succeeded": True,
            },
            "yupana": "2024-06-16T12:00:00+00:00",
        }
        staleness = get_sys_default_staleness()
        st = staleness_timestamps()

        result = _serialize_per_reporter_staleness(host, staleness, st)

        puptoo = result["puptoo"]
        assert puptoo["last_check_in"] == "2024-06-15T10:00:00+00:00"
        assert "stale_timestamp" in puptoo and "culled_timestamp" in puptoo

        yupana = result["yupana"]
        assert yupana["last_check_in"] == "2024-06-16T12:00:00+00:00"
        assert "stale_timestamp" in yupana and "culled_timestamp" in yupana
