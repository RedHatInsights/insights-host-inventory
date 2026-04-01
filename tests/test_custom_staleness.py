from __future__ import annotations

from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Query

from api.host_query import staleness_timestamps
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.culling import Timestamps
from app.models import Host
from app.models import db
from app.serialization import _serialize_per_reporter_staleness
from app.staleness_serialization import AttrDict
from app.staleness_serialization import build_staleness_sys_default
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.api_utils import create_host_with_reporter
from tests.helpers.api_utils import per_reporter_last_check_in_iso
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


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attrdict_from_custom_staleness(config: dict[str, int]) -> AttrDict:
    """Match keys used by ``_compute_timestamps_from_date`` for account custom staleness."""
    return AttrDict(
        {
            "conventional_time_to_stale": config["conventional_time_to_stale"],
            "conventional_time_to_stale_warning": config["conventional_time_to_stale_warning"],
            "conventional_time_to_delete": config["conventional_time_to_delete"],
        }
    )


def _assert_host_level_staleness_matches(host: Host, st_obj: Timestamps, staleness: AttrDict) -> None:
    """Host row timestamps must match ``get_staleness_timestamps`` for its ``last_check_in`` and config."""
    expected = get_staleness_timestamps(host, st_obj, staleness)
    assert _utc(host.stale_timestamp) == _utc(expected["stale_timestamp"])
    assert _utc(host.stale_warning_timestamp) == _utc(expected["stale_warning_timestamp"])
    assert _utc(host.deletion_timestamp) == _utc(expected["culled_timestamp"])


@patch("tests.helpers.api_utils.db.session.commit")
def test_create_host_with_reporter_defaults_stale_timestamp_to_last_check_in_plus_conventional_delay(
    _mock_commit,
) -> None:
    """When ``stale_timestamp`` is omitted, derive it from ``last_check_in`` and the conventional stale delay."""
    last_check_in = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    captured_kwargs: dict[str, Any] = {}

    def fake_db_create_host(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace()

    host = create_host_with_reporter(
        db_create_host=fake_db_create_host,
        reporter="some-reporter",
        last_check_in=last_check_in,
    )

    expected_stale_timestamp = last_check_in + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)

    extra = captured_kwargs["extra_data"]
    assert extra["reporter"] == "some-reporter"
    assert host.last_check_in == last_check_in
    assert host.stale_timestamp == expected_stale_timestamp


@pytest.mark.parametrize("num_hosts", [1, 2, 3])
def test_async_update_host_create_custom_staleness(
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
    """Create hosts under NO_HOSTS_TO_DELETE, then PATCH staleness to HOST_BECAME_STALE; async job runs."""
    db_create_staleness_culling(**CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)
    with (
        patch("app.models.utils.datetime") as mock_datetime,
    ):
        with flask_app.app.app_context():
            mocker.patch.object(event_producer, "write_event")
            _now = now()
            mock_datetime.now.return_value = _now
            mocker.patch("app.models.host._time_now", side_effect=lambda: _now)
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            st_obj = staleness_timestamps()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                v = hosts_before_update[0].per_reporter_staleness[reporter]
                assert isinstance(v, str)
                assert v == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_before_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_NO_HOSTS_TO_DELETE),
            )
            stale_timestamp_before = hosts_before_update[0].stale_timestamp

            staleness_url = build_staleness_url()
            status, _ = api_patch(staleness_url, CUSTOM_STALENESS_HOST_BECAME_STALE)
            assert status in (200, 201)

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                v = hosts_after_update[0].per_reporter_staleness[reporter]
                assert isinstance(v, str)
                assert v == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_after_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_HOST_BECAME_STALE),
            )
            assert hosts_after_update[0].stale_timestamp != stale_timestamp_before

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
            mocker.patch("app.models.host._time_now", side_effect=lambda: _now)
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            st_obj = staleness_timestamps()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                prs = hosts_before_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_before_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_HOST_BECAME_STALE),
            )
            stale_before = hosts_before_update[0].stale_timestamp

            status, _ = api_delete_staleness()
            assert status == 204

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                prs = hosts_after_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()

            sys_staleness = build_staleness_sys_default(hosts_after_update[0].org_id)
            _assert_host_level_staleness_matches(hosts_after_update[0], st_obj, sys_staleness)
            assert hosts_after_update[0].stale_timestamp != stale_before

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
            mocker.patch("app.models.host._time_now", side_effect=lambda: _now)
            created_hosts = db_create_multiple_hosts(how_many=num_hosts)
            host_url = build_hosts_url()
            response_status, response_data = api_get(host_url)
            assert response_status == 200
            assert len(response_data["results"]) == len(created_hosts)

            host_ids = [host["id"] for host in response_data["results"]]
            hosts_before_update = db_get_hosts(host_ids).all()
            st_obj = staleness_timestamps()
            for reporter in hosts_before_update[0].per_reporter_staleness:
                prs = hosts_before_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_before_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_HOST_BECAME_STALE),
            )
            stale_timestamp_before = hosts_before_update[0].stale_timestamp

            staleness_url = build_staleness_url()
            status, _ = api_patch(staleness_url, CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)
            assert status == 200

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                prs = hosts_after_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_after_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_NO_HOSTS_TO_DELETE),
            )
            assert hosts_after_update[0].stale_timestamp != stale_timestamp_before

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
            mocker.patch("app.models.host._time_now", side_effect=lambda: _now)
            hosts_before_update = db_create_multiple_hosts(how_many=num_hosts)
            st_obj = staleness_timestamps()

            for reporter in hosts_before_update[0].per_reporter_staleness:
                prs = hosts_before_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()

            _assert_host_level_staleness_matches(
                hosts_before_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_HOST_BECAME_STALE),
            )
            stale_timestamp_before = hosts_before_update[0].stale_timestamp
            modified_on_before = hosts_before_update[0].modified_on

            staleness_url = build_staleness_url()
            status, _ = api_patch(staleness_url, CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)
            assert status == 200

            # Wait for thread to finish - poll until event_producer.write_event is called
            wait_for_all_events(event_producer, num_hosts)

            host_ids = [str(host.id) for host in hosts_before_update]

            hosts_after_update = db_get_hosts(host_ids).all()
            for reporter in hosts_after_update[0].per_reporter_staleness:
                prs = hosts_after_update[0].per_reporter_staleness[reporter]
                assert isinstance(prs, str)
                assert prs == _now.isoformat()
            _assert_host_level_staleness_matches(
                hosts_after_update[0],
                st_obj,
                _attrdict_from_custom_staleness(CUSTOM_STALENESS_NO_HOSTS_TO_DELETE),
            )
            assert hosts_after_update[0].stale_timestamp != stale_timestamp_before
            assert hosts_after_update[0].modified_on == modified_on_before

            # Call event_producer
            assert event_producer.write_event.call_count == num_hosts


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

            _ = db_create_host(
                extra_data={
                    "reporter": "puptoo",
                    "per_reporter_staleness": {
                        "puptoo": _now.isoformat(),
                        "yupana": _now.isoformat(),
                    },
                },
            )

    db_create_host(
        extra_data={
            "reporter": "puptoo",
            "per_reporter_staleness": {"puptoo": (_now - timedelta(days=30)).isoformat()},
        },
    )

    db_create_host(
        extra_data={
            "reporter": "rhsm-conduit",
            "per_reporter_staleness": {"rhsm-conduit": _now.isoformat()},
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
    puptoo_data = per_reporter_last_check_in_iso(fresh_last_check_in)

    fresh_host = db_create_host(
        extra_data={"reporter": "puptoo", "per_reporter_staleness": {"puptoo": puptoo_data}},
    )
    fresh_host.last_check_in = fresh_last_check_in
    fresh_host.per_reporter_staleness["puptoo"] = fresh_last_check_in.isoformat()
    fresh_host_id = str(fresh_host.id)
    db.session.commit()

    other_host = db_create_host(
        extra_data={
            "reporter": "rhsm-conduit",
            "per_reporter_staleness": {"rhsm-conduit": per_reporter_last_check_in_iso(fresh_last_check_in)},
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


def test_registered_with_staleness_filter_flat_format(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    """registered_with + not_culled with flat per_reporter_staleness (ISO last_check_in strings)."""
    staleness_config = {
        "conventional_time_to_stale": 7 * 24 * 3600,
        "conventional_time_to_stale_warning": 14 * 24 * 3600,
        "conventional_time_to_delete": 30 * 24 * 3600,
    }
    db_create_staleness_culling(**staleness_config)

    future_dt = datetime.now(UTC) + timedelta(days=1)
    future_check_in = future_dt.isoformat()

    host_a = db_create_host(
        extra_data={
            "reporter": "puptoo",
            "per_reporter_staleness": {"puptoo": future_check_in},
        },
    )
    host_b = db_create_host(
        extra_data={
            "reporter": "puptoo",
            "per_reporter_staleness": {"puptoo": per_reporter_last_check_in_iso(future_dt)},
        },
    )
    id_a, id_b = str(host_a.id), str(host_b.id)

    _, resp = api_get(build_hosts_url(query="?registered_with=puptoo"))
    result_ids = {h["id"] for h in resp["results"]}
    assert id_a in result_ids
    assert id_b in result_ids
    assert len(resp["results"]) == 2


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
            "per_reporter_staleness": {"puptoo": per_reporter_last_check_in_iso(last_check_in)},
        },
    )
    host.last_check_in = last_check_in
    host.per_reporter_staleness["puptoo"] = last_check_in.isoformat()
    db.session.commit()

    # Get host from database and calculate timestamps
    db_host = db_get_hosts([str(host.id)]).first()
    staleness = get_sys_default_staleness()
    staleness_timestamps_obj = staleness_timestamps()
    calculated = get_reporter_staleness_timestamps(db_host, staleness_timestamps_obj, staleness, "puptoo")

    # Calculate expected timestamps
    from datetime import datetime as dt

    date_to_use = dt.fromisoformat(db_host.per_reporter_staleness["puptoo"])
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


def test_registered_with_filter_puptoo_reporter_without_puptoo_prs(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    """
    Host is puptoo but per_reporter_staleness has no puptoo entry (only another reporter).
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    _now = now()
    host_without_puptoo_prs_id = str(
        db_create_host(
            extra_data={
                "reporter": "puptoo",
                "per_reporter_staleness": {"yupana": per_reporter_last_check_in_iso(_now)},
            },
        ).id
    )

    normal_host_id = str(
        create_host_with_reporter(
            db_create_host,
            "puptoo",
            _now,
            stale_timestamp=_now + timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"]),
        ).id
    )

    other_host_id = str(
        db_create_host(
            extra_data={
                "reporter": "yupana",
                "per_reporter_staleness": {"yupana": per_reporter_last_check_in_iso(_now)},
            },
        ).id
    )

    # Test positive filter: registered_with=puptoo
    _, puptoo_hosts = api_get(build_hosts_url(query="?registered_with=puptoo"))
    assert normal_host_id in {h["id"] for h in puptoo_hosts["results"]}
    assert host_without_puptoo_prs_id not in {h["id"] for h in puptoo_hosts["results"]}

    # !puptoo: hosts not registered with puptoo (includes malformed puptoo reporter / no puptoo PRS key)
    _, data = api_get(build_hosts_url(query="?registered_with=!puptoo"))
    assert data is not None
    returned_ids = {h["id"] for h in data["results"]}
    assert normal_host_id not in returned_ids
    assert host_without_puptoo_prs_id in returned_ids
    assert other_host_id in returned_ids


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


def test_serialize_per_reporter_staleness_multiple_flat_reporters(flask_app):
    """Several reporters with flat stored values all serialize to full staleness dicts."""
    with flask_app.app.app_context():
        host = Host(
            subscription_manager_id=generate_uuid(),
            reporter="puptoo",
            stale_timestamp=datetime.now(UTC),
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": "2024-06-15T10:00:00+00:00",
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
