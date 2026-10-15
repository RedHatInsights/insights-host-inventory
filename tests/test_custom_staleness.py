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

from api.filtering.db_filters import _staleness_filter
from api.filtering.db_filters import per_reporter_staleness_filter
from api.filtering.db_filters import staleness_to_conditions
from app.common import inventory_config
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.culling import Timestamps
from app.models import Host
from app.models import db
from app.serialization import _serialize_per_reporter_staleness
from app.staleness_serialization import AttrDict
from app.staleness_serialization import get_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from app.staleness_states import HostStalenessStatesDbFilters
from lib.host_repository import find_non_culled_hosts
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_host_with_reporter
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

# ``get_staleness_timestamps`` still accepts ``Timestamps`` for API compatibility; these
# unit tests only need a minimal config for ``Timestamps.from_config``.
_MINIMAL_TS_CONFIG = SimpleNamespace(
    culling_stale_warning_offset_delta=timedelta(hours=1),
    culling_culled_offset_delta=timedelta(days=30),
)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attrdict_from_custom_staleness(config: dict[str, int]) -> AttrDict:
    """Match ``conventional_time_to_*`` keys read by ``get_staleness_timestamps`` for custom staleness."""
    return AttrDict(
        {
            "conventional_time_to_stale": config["conventional_time_to_stale"],
            "conventional_time_to_stale_warning": config["conventional_time_to_stale_warning"],
            "conventional_time_to_delete": config["conventional_time_to_delete"],
        }
    )


@patch("tests.helpers.api_utils.db.session.commit")
def test_create_host_with_reporter_sets_last_check_in(_mock_commit) -> None:
    """``create_host_with_reporter`` persists PRS and ``last_check_in`` only (no staleness columns)."""
    last_check_in = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    captured_kwargs: dict[str, Any] = {}

    def fake_db_create_host(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(last_check_in=None)

    host = create_host_with_reporter(
        db_create_host=fake_db_create_host,
        reporter="some-reporter",
        last_check_in=last_check_in,
    )

    extra = captured_kwargs["extra_data"]
    assert extra["reporter"] == "some-reporter"
    assert "stale_timestamp" not in extra
    assert host.last_check_in == last_check_in


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
    puptoo_data = fresh_last_check_in.isoformat()

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
            "per_reporter_staleness": {"rhsm-conduit": fresh_last_check_in.isoformat()},
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


def test_registered_with_staleness_filter_iso_string_values(
    db_create_staleness_culling: Callable[..., object],
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
) -> None:
    """registered_with + not_culled with ISO string last_check_in values in JSONB."""
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
            "per_reporter_staleness": {"puptoo": future_dt.isoformat()},
        },
    )
    id_a, id_b = str(host_a.id), str(host_b.id)

    _, resp = api_get(build_hosts_url(query="?registered_with=puptoo"))
    result_ids = {h["id"] for h in resp["results"]}
    assert id_a in result_ids
    assert id_b in result_ids
    assert len(resp["results"]) == 2


def test_per_reporter_staleness_timestamps_match_host_level_timestamps(
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
            "per_reporter_staleness": {"puptoo": last_check_in.isoformat()},
        },
    )
    host.last_check_in = last_check_in
    host.per_reporter_staleness["puptoo"] = last_check_in.isoformat()
    db.session.commit()

    # Get host from database and calculate timestamps
    db_host = db_get_hosts([str(host.id)]).first()
    staleness = get_sys_default_staleness()
    staleness_timestamps_obj = Timestamps.from_config(inventory_config())

    date_to_use = datetime.fromisoformat(db_host.per_reporter_staleness["puptoo"])
    date_to_use = date_to_use.replace(tzinfo=UTC) if date_to_use.tzinfo is None else date_to_use.astimezone(UTC)

    # Explicit last_check_in path (reporter-specific reference instant)
    calculated = get_staleness_timestamps(
        db_host,
        staleness,
        last_check_in=date_to_use,
    )

    # Default path: rely on host.last_check_in internally (no last_check_in argument)
    db_host.last_check_in = date_to_use
    calculated_from_host = get_staleness_timestamps(db_host, staleness)
    assert calculated_from_host == calculated

    # Calculate expected timestamps
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


def test_get_staleness_timestamps_last_check_in_arg_overrides_host_last_check_in(
    db_create_host: Callable[..., Host],
) -> None:
    """
    ``last_check_in=`` must win over ``host.last_check_in``.

    ``test_calculated_timestamps_match_stored_timestamps`` only checks the explicit
    argument and host field when they match after assignment; this covers divergent values.
    """
    host_last = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    override = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    host = db_create_host()
    host.last_check_in = host_last
    db.session.commit()

    staleness = _attrdict_from_custom_staleness(
        {"conventional_time_to_stale": 10, "conventional_time_to_stale_warning": 20, "conventional_time_to_delete": 30}
    )

    result = get_staleness_timestamps(host, staleness, last_check_in=override)

    assert result["stale_timestamp"] == override + timedelta(seconds=10)
    assert result["stale_warning_timestamp"] == override + timedelta(seconds=20)
    assert result["culled_timestamp"] == override + timedelta(seconds=30)


def test_get_staleness_timestamps_raises_when_reference_instant_missing(
    db_create_host: Callable[..., Host],
) -> None:
    """No ``last_check_in`` argument and ``host.last_check_in`` is None."""
    host = db_create_host()
    host.last_check_in = None
    db.session.commit()

    staleness = _attrdict_from_custom_staleness(
        {"conventional_time_to_stale": 1, "conventional_time_to_stale_warning": 2, "conventional_time_to_delete": 3}
    )

    with pytest.raises(ValueError, match="last_check_in is required"):
        get_staleness_timestamps(host, staleness)


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
                "per_reporter_staleness": {"yupana": _now.isoformat()},
            },
        ).id
    )

    normal_host_id = str(create_host_with_reporter(db_create_host, "puptoo", _now).id)

    other_host_id = str(
        db_create_host(
            extra_data={
                "reporter": "yupana",
                "per_reporter_staleness": {"yupana": _now.isoformat()},
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
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {"puptoo": last_check_in_str}
        staleness = get_sys_default_staleness()

        result = _serialize_per_reporter_staleness(host, staleness)

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
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {"puptoo": last_check_in_dt}
        staleness = get_sys_default_staleness()

        result = _serialize_per_reporter_staleness(host, staleness)

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
            org_id=USER_IDENTITY["org_id"],
        )
        host.per_reporter_staleness = {
            "puptoo": "2024-06-15T10:00:00+00:00",
            "yupana": "2024-06-16T12:00:00+00:00",
        }
        staleness = get_sys_default_staleness()

        result = _serialize_per_reporter_staleness(host, staleness)

        puptoo = result["puptoo"]
        assert puptoo["last_check_in"] == "2024-06-15T10:00:00+00:00"
        assert "stale_timestamp" in puptoo and "culled_timestamp" in puptoo

        yupana = result["yupana"]
        assert yupana["last_check_in"] == "2024-06-16T12:00:00+00:00"
        assert "stale_timestamp" in yupana and "culled_timestamp" in yupana


def test_staleness_db_filter_fresh_uses_org_defaults_when_columns_null(db_create_host):
    """``_staleness_filter``: NULL staleness columns + recent check-in counts as fresh."""
    host = db_create_host()
    expr = _staleness_filter(["fresh"], host.org_id)
    assert Host.query.filter(Host.id == host.id).filter(*expr).count() == 1


def test_staleness_db_filter_not_fresh_when_columns_null_and_last_check_in_old(db_create_host):
    host = db_create_host()
    host.last_check_in = datetime.now(tz=UTC) - timedelta(days=40)
    db.session.commit()

    expr = _staleness_filter(["fresh"], host.org_id)
    assert Host.query.filter(Host.id == host.id).filter(*expr).count() == 0


def test_staleness_db_filter_stale_mid_window_when_columns_null(db_create_host):
    host = db_create_host()
    host.last_check_in = datetime.now(tz=UTC) - timedelta(days=3)
    db.session.commit()

    expr = _staleness_filter(["stale"], host.org_id)
    assert Host.query.filter(Host.id == host.id).filter(*expr).count() == 1


def test_staleness_db_filter_stale_warning_when_columns_null(db_create_host):
    """``_staleness_filter``: past ``conventional_time_to_stale_warning`` but before delete window."""
    host = db_create_host()
    host.last_check_in = datetime.now(tz=UTC) - timedelta(days=10)
    db.session.commit()

    expr = _staleness_filter(["stale_warning"], host.org_id)
    assert Host.query.filter(Host.id == host.id).filter(*expr).count() == 1


def test_staleness_db_filter_culled_when_columns_null_and_last_check_in_old(db_create_host):
    host = db_create_host()
    host.last_check_in = datetime.now(tz=UTC) - timedelta(days=40)
    db.session.commit()

    expr = _staleness_filter(["culled"], host.org_id)
    assert Host.query.filter(Host.id == host.id).filter(*expr).count() == 1


def test_find_non_culled_excludes_compute_on_read_culled(db_create_host):
    host = db_create_host()
    host.last_check_in = datetime.now(tz=UTC) - timedelta(days=40)
    db.session.commit()

    base = Host.query.filter(Host.id == host.id)
    assert find_non_culled_hosts(base, host.org_id).count() == 0


@pytest.fixture
def staleness_test_hosts(db_create_host):
    now_dt = datetime.now(tz=UTC)
    fresh_host = db_create_host()
    fresh_host.last_check_in = now_dt

    stale_host = db_create_host()
    stale_host.last_check_in = now_dt - timedelta(days=3)

    warn_host = db_create_host()
    warn_host.last_check_in = now_dt - timedelta(days=10)

    culled_host = db_create_host()
    culled_host.last_check_in = now_dt - timedelta(days=40)

    null_host = db_create_host()
    null_host.last_check_in = None

    db.session.commit()

    return {
        "fresh": fresh_host,
        "stale": stale_host,
        "warn": warn_host,
        "culled": culled_host,
        "null": null_host,
        "org_id": fresh_host.org_id,
        "all_ids": [fresh_host.id, stale_host.id, warn_host.id, culled_host.id, null_host.id],
    }


def test_staleness_db_filter_consecutive_fresh_stale(staleness_test_hosts):
    """(1) Consecutive pair [fresh, stale] matches fresh and stale but not stale_warning or culled."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "stale"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["fresh"].id, staleness_test_hosts["stale"].id}


def test_staleness_db_filter_consecutive_stale_warning(staleness_test_hosts):
    """(2) Consecutive pair [stale, stale_warning] matches those windows but not fresh or culled."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["stale", "stale_warning"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["stale"].id, staleness_test_hosts["warn"].id}


def test_staleness_db_filter_all_three_non_culled(staleness_test_hosts):
    """(3) All three non-culled states [fresh, stale, stale_warning] matches any non-culled host."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "stale", "stale_warning"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {
        staleness_test_hosts["fresh"].id,
        staleness_test_hosts["stale"].id,
        staleness_test_hosts["warn"].id,
    }


def test_staleness_db_filter_non_consecutive_fresh_stale_warning(staleness_test_hosts):
    """(4) Non-consecutive [fresh, stale_warning] matches fresh and stale_warning but not stale or culled."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "stale_warning"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["fresh"].id, staleness_test_hosts["warn"].id}


def test_staleness_db_filter_all_four_states_excludes_null(staleness_test_hosts):
    """(5) All four states match hosts with non-NULL check-in, excluding NULL check-in hosts."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "stale", "stale_warning", "culled"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {
        staleness_test_hosts["fresh"].id,
        staleness_test_hosts["stale"].id,
        staleness_test_hosts["warn"].id,
        staleness_test_hosts["culled"].id,
    }
    assert staleness_test_hosts["null"].id not in matched_ids


def test_staleness_db_filter_mixed_unknown_and_recognized(staleness_test_hosts):
    """(6) Mixed inputs containing unknown alongside recognized states handle unknown
    separately and do not pass to combined_filter.
    """
    org_id = staleness_test_hosts["org_id"]
    with patch.object(
        HostStalenessStatesDbFilters,
        "combined_filter",
        autospec=True,
        side_effect=HostStalenessStatesDbFilters.combined_filter,
    ) as mock_combined:
        expr = _staleness_filter(["fresh", "unknown"], org_id)
        assert mock_combined.call_count == 1
        assert mock_combined.call_args[0][1] == ["fresh"]

    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["fresh"].id}


def test_staleness_db_filter_singleton_unknown(staleness_test_hosts):
    """(7) The singleton ["unknown"] case continues to work as before (returns non-culled hosts)."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["unknown"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {
        staleness_test_hosts["fresh"].id,
        staleness_test_hosts["stale"].id,
        staleness_test_hosts["warn"].id,
    }
    assert staleness_test_hosts["culled"].id not in matched_ids
    assert staleness_test_hosts["null"].id not in matched_ids


def test_staleness_db_filter_empty_list(staleness_test_hosts):
    """Empty staleness list produces no matches."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter([], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == set()


def test_staleness_to_conditions_merges_consecutive_states():
    """Verify staleness_to_conditions merges consecutive states into a single range condition."""
    staleness = get_sys_default_staleness()

    # Consecutive pair [fresh, stale] -> 1 condition: (warn_boundary, None)
    captured = []
    list(
        staleness_to_conditions(
            staleness,
            ["fresh", "stale"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is not None
    assert captured[0][1] is None

    # Consecutive pair [stale, stale_warning] -> 1 condition: (culled_boundary, stale_boundary)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["stale", "stale_warning"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is not None
    assert captured[0][1] is not None

    # Consecutive three [fresh, stale, stale_warning] -> 1 condition: (culled_boundary, None)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["fresh", "stale", "stale_warning"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is not None
    assert captured[0][1] is None

    # All four states [fresh, stale, stale_warning, culled] -> 1 condition: (None, None)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["fresh", "stale", "stale_warning", "culled"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is None
    assert captured[0][1] is None

    # Non-consecutive states [fresh, stale_warning] -> 2 conditions
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["fresh", "stale_warning"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 2

    # Other states like not_culled -> 1 condition
    captured.clear()
    list(staleness_to_conditions(staleness, ["not_culled"], lambda gt, lte: captured.append((gt, lte))))
    assert len(captured) == 1
    assert captured[0][0] is not None
    assert captured[0][1] is None


@pytest.fixture
def reporter_test_hosts(db_create_host):
    now_dt = datetime.now(tz=UTC)
    reporter = "puptoo"

    fresh_host = db_create_host(
        extra_data={"reporter": reporter, "per_reporter_staleness": {reporter: now_dt.isoformat()}}
    )
    fresh_host.last_check_in = now_dt

    stale_host = db_create_host(
        extra_data={
            "reporter": reporter,
            "per_reporter_staleness": {reporter: (now_dt - timedelta(days=3)).isoformat()},
        }
    )
    stale_host.last_check_in = now_dt - timedelta(days=3)

    warn_host = db_create_host(
        extra_data={
            "reporter": reporter,
            "per_reporter_staleness": {reporter: (now_dt - timedelta(days=10)).isoformat()},
        }
    )
    warn_host.last_check_in = now_dt - timedelta(days=10)

    culled_host = db_create_host(
        extra_data={
            "reporter": reporter,
            "per_reporter_staleness": {reporter: (now_dt - timedelta(days=40)).isoformat()},
        }
    )
    culled_host.last_check_in = now_dt - timedelta(days=40)

    db.session.commit()

    return {
        "fresh": fresh_host,
        "stale": stale_host,
        "warn": warn_host,
        "culled": culled_host,
        "org_id": fresh_host.org_id,
        "reporter": reporter,
        "all_ids": [fresh_host.id, stale_host.id, warn_host.id, culled_host.id],
    }


def test_per_reporter_staleness_filter_consecutive_states(reporter_test_hosts):
    """Verify per_reporter_staleness_filter with consecutive states merges conditions
    and returns correct hosts.
    """
    org_id = reporter_test_hosts["org_id"]
    reporter = reporter_test_hosts["reporter"]
    all_ids = reporter_test_hosts["all_ids"]

    # [fresh, stale] matches fresh and stale hosts
    expr = per_reporter_staleness_filter(["fresh", "stale"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["fresh"].id, reporter_test_hosts["stale"].id}

    # [stale, stale_warning] matches stale and stale_warning hosts
    expr = per_reporter_staleness_filter(["stale", "stale_warning"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["stale"].id, reporter_test_hosts["warn"].id}

    # [fresh, stale, stale_warning] matches non-culled reporter hosts
    expr = per_reporter_staleness_filter(["fresh", "stale", "stale_warning"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {
        reporter_test_hosts["fresh"].id,
        reporter_test_hosts["stale"].id,
        reporter_test_hosts["warn"].id,
    }

    # Non-consecutive [fresh, stale_warning] matches fresh and warn hosts
    expr = per_reporter_staleness_filter(["fresh", "stale_warning"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["fresh"].id, reporter_test_hosts["warn"].id}


def test_staleness_db_filter_consecutive_stale_warning_culled(staleness_test_hosts):
    """Consecutive pair [stale_warning, culled] matches stale_warning and culled hosts."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["stale_warning", "culled"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["warn"].id, staleness_test_hosts["culled"].id}


def test_staleness_db_filter_consecutive_stale_to_culled(staleness_test_hosts):
    """Consecutive run [stale, stale_warning, culled] matches stale, stale_warning, and culled."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["stale", "stale_warning", "culled"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {
        staleness_test_hosts["stale"].id,
        staleness_test_hosts["warn"].id,
        staleness_test_hosts["culled"].id,
    }


def test_staleness_db_filter_disjoint_runs_fresh_and_culled(staleness_test_hosts):
    """Non-consecutive states [fresh, culled] create disjoint conditions and match only those hosts."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "culled"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {staleness_test_hosts["fresh"].id, staleness_test_hosts["culled"].id}


def test_staleness_db_filter_merged_run_plus_disjoint_state(staleness_test_hosts):
    """Run [fresh, stale] combined with disjoint [culled] matches fresh, stale, and culled."""
    org_id = staleness_test_hosts["org_id"]
    expr = _staleness_filter(["fresh", "stale", "culled"], org_id)
    matched_ids = {h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr).all()}
    assert matched_ids == {
        staleness_test_hosts["fresh"].id,
        staleness_test_hosts["stale"].id,
        staleness_test_hosts["culled"].id,
    }


def test_staleness_db_filter_order_invariance_and_duplicates(staleness_test_hosts):
    """Filter handles out-of-order and duplicated states identically to canonical ordered list."""
    org_id = staleness_test_hosts["org_id"]
    expr_shuffled = _staleness_filter(["stale", "fresh", "stale"], org_id)
    matched_shuffled = {
        h.id for h in Host.query.filter(Host.id.in_(staleness_test_hosts["all_ids"])).filter(*expr_shuffled).all()
    }
    assert matched_shuffled == {staleness_test_hosts["fresh"].id, staleness_test_hosts["stale"].id}


def test_staleness_to_conditions_additional_combinations():
    """Verify staleness_to_conditions for remaining runs, ordering invariance, and duplicates."""
    staleness = get_sys_default_staleness()

    # Consecutive pair [stale_warning, culled] -> 1 condition: (None, warn_boundary)
    captured = []
    list(
        staleness_to_conditions(
            staleness,
            ["stale_warning", "culled"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is None
    assert captured[0][1] is not None

    # Consecutive run [stale, stale_warning, culled] -> 1 condition: (None, stale_boundary)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["stale", "stale_warning", "culled"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is None
    assert captured[0][1] is not None

    # Disjoint run [fresh, stale, culled] -> 2 conditions: (warn_boundary, None) and (None, culled_boundary)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["fresh", "stale", "culled"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 2
    assert captured[0][0] is not None and captured[0][1] is None
    assert captured[1][0] is None and captured[1][1] is not None

    # Order invariance and duplicates [stale, fresh, stale] -> 1 merged condition: (warn_boundary, None)
    captured.clear()
    list(
        staleness_to_conditions(
            staleness,
            ["stale", "fresh", "stale"],
            lambda gt, lte: captured.append((gt, lte)),
        )
    )
    assert len(captured) == 1
    assert captured[0][0] is not None
    assert captured[0][1] is None


def test_per_reporter_staleness_filter_additional_runs(reporter_test_hosts):
    """Verify per_reporter_staleness_filter with runs involving culled, disjoint runs, and ordering."""
    org_id = reporter_test_hosts["org_id"]
    reporter = reporter_test_hosts["reporter"]
    all_ids = reporter_test_hosts["all_ids"]

    # [stale_warning, culled] matches warn host (culled host is excluded by positive reporter filter)
    expr = per_reporter_staleness_filter(["stale_warning", "culled"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["warn"].id}

    # [stale, stale_warning, culled] matches stale and warn hosts
    expr = per_reporter_staleness_filter(["stale", "stale_warning", "culled"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["stale"].id, reporter_test_hosts["warn"].id}

    # Out-of-order and duplicated [stale, fresh, stale] matches fresh and stale hosts
    expr = per_reporter_staleness_filter(["stale", "fresh", "stale"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {reporter_test_hosts["fresh"].id, reporter_test_hosts["stale"].id}

    # Reverse-order [stale_warning, stale, fresh] matches all non-culled reporter hosts
    expr = per_reporter_staleness_filter(["stale_warning", "stale", "fresh"], reporter, org_id)
    matched = {h.id for h in Host.query.filter(Host.id.in_(all_ids)).filter(*expr).all()}
    assert matched == {
        reporter_test_hosts["fresh"].id,
        reporter_test_hosts["stale"].id,
        reporter_test_hosts["warn"].id,
    }
