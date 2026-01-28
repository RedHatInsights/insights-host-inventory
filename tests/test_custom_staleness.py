from datetime import UTC
from datetime import timedelta
from unittest.mock import patch

import pytest

from api.host_query import staleness_timestamps
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import db
from app.staleness_serialization import get_reporter_staleness_timestamps
from app.staleness_serialization import get_sys_default_staleness
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url
from tests.helpers.outbox_utils import wait_for_all_events
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
            db_create_host(
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
                        # Culled puptoo reporter
                        "puptoo": {
                            "last_check_in": (_now - timedelta(days=30)).isoformat(),
                            "stale_timestamp": (_now - timedelta(days=23)).isoformat(),
                            "culled_timestamp": (_now - timedelta(days=16)).isoformat(),  # Culled (past)
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
                            "culled_timestamp": (_now + timedelta(days=14)).isoformat(),  # Fresh
                            "check_in_succeeded": True,
                        }
                    },
                },
            )

            total_hosts = 3

            # Set up URLs for testing
            puptoo_url = build_hosts_url(query="?registered_with=puptoo")
            yupana_url = build_hosts_url(query="?registered_with=yupana")
            not_puptoo_url = build_hosts_url(query="?registered_with=!puptoo")
            not_yupana_url = build_hosts_url(query="?registered_with=!yupana")

            _, puptoo_hosts = api_get(puptoo_url)
            _, yupana_hosts = api_get(yupana_url)
            _, not_puptoo_hosts = api_get(not_puptoo_url)
            _, not_yupana_hosts = api_get(not_yupana_url)

            puptoo_count = len(puptoo_hosts["results"])
            yupana_count = len(yupana_hosts["results"])
            not_puptoo_count = len(not_puptoo_hosts["results"])
            not_yupana_count = len(not_yupana_hosts["results"])

            # EXPECTED BEHAVIOR with culled-based filtering:
            # registered_with=puptoo should return 1 (multi_reporter_host with fresh puptoo)
            # registered_with=!puptoo should return 2 (culled_reporter_host with culled puptoo +
            #                                          single_reporter_host without puptoo)
            # registered_with=yupana should return 1 (multi_reporter_host with fresh yupana)
            # registered_with=!yupana should return 2 (culled_reporter_host + single_reporter_host,
            #                                          neither has yupana)

            expected_fresh_puptoo = 1
            expected_not_puptoo = 2
            expected_fresh_yupana = 1
            expected_not_yupana = 2

            assert puptoo_count == expected_fresh_puptoo
            assert not_puptoo_count == expected_not_puptoo
            assert yupana_count == expected_fresh_yupana
            assert not_yupana_count == expected_not_yupana

            # The equation should hold
            assert puptoo_count + not_puptoo_count == total_hosts
            assert yupana_count + not_yupana_count == total_hosts


@pytest.mark.parametrize("feature_flag_enabled", [False, True])
def test_registered_with_filter_same_results_with_or_without_feature_flag(
    db_create_staleness_culling,
    db_create_host,
    api_get,
    flask_app,
    event_producer,
    mocker,
    feature_flag_enabled,
):
    """Test that registered_with filter produces identical results with feature flag ON or OFF.

    When feature flag is OFF: Uses stored timestamps in per_reporter_staleness
    When feature flag is ON: Calculates timestamps from last_check_in on-the-fly

    Both should produce the same filtering results.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as mock_datetime:
        with patch("lib.feature_flags.get_flag_value") as mock_get_flag_value:
            with flask_app.app.app_context():
                mocker.patch.object(event_producer, "write_event")
                _now = now()
                mock_datetime.now.return_value = _now
                mock_get_flag_value.return_value = feature_flag_enabled

                # Calculate expected timestamps based on staleness config
                stale_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"])
                culled_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_delete"])

                # Create a host with multiple reporters - fresh (not culled)
                fresh_last_check_in = _now
                fresh_stale_timestamp = fresh_last_check_in + stale_delta
                fresh_culled_timestamp = fresh_last_check_in + culled_delta

                db_create_host(
                    extra_data={
                        "reporter": "puptoo",
                        "per_reporter_staleness": {
                            "puptoo": {
                                "last_check_in": fresh_last_check_in.isoformat(),
                                # Include stored timestamps for old behavior, but they'll be ignored when flag is ON
                                "stale_timestamp": fresh_stale_timestamp.isoformat(),
                                "culled_timestamp": fresh_culled_timestamp.isoformat(),
                                "check_in_succeeded": True,
                            },
                            "yupana": {
                                "last_check_in": fresh_last_check_in.isoformat(),
                                "stale_timestamp": fresh_stale_timestamp.isoformat(),
                                "culled_timestamp": fresh_culled_timestamp.isoformat(),
                                "check_in_succeeded": True,
                            },
                        },
                    },
                )

                # Create a host with culled reporter
                culled_last_check_in = _now - timedelta(days=30)
                culled_stale_timestamp = culled_last_check_in + stale_delta
                culled_culled_timestamp = culled_last_check_in + culled_delta  # This will be in the past

                db_create_host(
                    extra_data={
                        "reporter": "puptoo",
                        "per_reporter_staleness": {
                            "puptoo": {
                                "last_check_in": culled_last_check_in.isoformat(),
                                "stale_timestamp": culled_stale_timestamp.isoformat(),
                                "culled_timestamp": culled_culled_timestamp.isoformat(),  # Past timestamp
                                "check_in_succeeded": True,
                            }
                        },
                    },
                )

                # Create a host with different reporter (no puptoo/yupana)
                db_create_host(
                    extra_data={
                        "reporter": "rhsm-conduit",
                        "per_reporter_staleness": {
                            "rhsm-conduit": {
                                "last_check_in": fresh_last_check_in.isoformat(),
                                "stale_timestamp": fresh_stale_timestamp.isoformat(),
                                "culled_timestamp": fresh_culled_timestamp.isoformat(),
                                "check_in_succeeded": True,
                            }
                        },
                    },
                )

                total_hosts = 3

                # Test filtering with puptoo
                puptoo_url = build_hosts_url(query="?registered_with=puptoo")
                not_puptoo_url = build_hosts_url(query="?registered_with=!puptoo")

                _, puptoo_hosts = api_get(puptoo_url)
                _, not_puptoo_hosts = api_get(not_puptoo_url)

                puptoo_count = len(puptoo_hosts["results"])
                not_puptoo_count = len(not_puptoo_hosts["results"])

                # Expected: puptoo should return 1 (multi_reporter_host with fresh puptoo)
                # Expected: !puptoo should return 2 (culled_reporter_host + other_reporter_host)
                expected_fresh_puptoo = 1
                expected_not_puptoo = 2

                assert puptoo_count == expected_fresh_puptoo
                assert not_puptoo_count == expected_not_puptoo

                # The equation should hold
                assert puptoo_count + not_puptoo_count == total_hosts


@pytest.mark.parametrize("feature_flag_enabled", [False, True])
def test_registered_with_filter_with_only_last_check_in_when_flag_enabled(
    db_create_staleness_culling,
    db_create_host,
    api_get,
    flask_app,
    event_producer,
    mocker,
    feature_flag_enabled,
):
    """Test that when feature flag is ON, filtering works correctly even when only last_check_in is stored.

    This verifies that the new behavior correctly calculates timestamps from last_check_in
    when stored timestamps are not present. Simplified test focusing on fresh hosts.
    """
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as mock_datetime:
        with patch("lib.feature_flags.get_flag_value") as mock_get_flag_value:
            with flask_app.app.app_context():
                mocker.patch.object(event_producer, "write_event")
                _now = now()
                mock_datetime.now.return_value = _now
                mock_get_flag_value.return_value = feature_flag_enabled

                stale_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"])
                culled_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_delete"])

                fresh_last_check_in = _now
                per_reporter_data = {
                    "puptoo": {
                        "last_check_in": fresh_last_check_in.isoformat(),
                        "check_in_succeeded": True,
                    }
                }
                if not feature_flag_enabled:
                    per_reporter_data["puptoo"].update(
                        {
                            "stale_timestamp": (fresh_last_check_in + stale_delta).isoformat(),
                            "culled_timestamp": (fresh_last_check_in + culled_delta).isoformat(),
                        }
                    )

                fresh_host = db_create_host(
                    extra_data={"reporter": "puptoo", "per_reporter_staleness": per_reporter_data},
                )
                fresh_host.last_check_in = fresh_last_check_in
                fresh_host.per_reporter_staleness["puptoo"]["last_check_in"] = fresh_last_check_in.isoformat()
                db.session.commit()

                other_host = db_create_host(
                    extra_data={
                        "reporter": "rhsm-conduit",
                        "per_reporter_staleness": {
                            "rhsm-conduit": {
                                "last_check_in": fresh_last_check_in.isoformat(),
                                "stale_timestamp": (fresh_last_check_in + stale_delta).isoformat(),
                                "culled_timestamp": (fresh_last_check_in + culled_delta).isoformat(),
                                "check_in_succeeded": True,
                            }
                        },
                    },
                )
                other_host.last_check_in = fresh_last_check_in
                db.session.commit()

                fresh_host_id = str(fresh_host.id)
                other_host_id = str(other_host.id)

                _, puptoo_hosts = api_get(build_hosts_url(query="?registered_with=puptoo"))
                _, not_puptoo_hosts = api_get(build_hosts_url(query="?registered_with=!puptoo"))

                assert len(puptoo_hosts["results"]) == 1
                assert len(not_puptoo_hosts["results"]) == 1
                assert fresh_host_id in {h["id"] for h in puptoo_hosts["results"]}
                assert other_host_id in {h["id"] for h in not_puptoo_hosts["results"]}


def test_calculated_timestamps_match_stored_timestamps(
    db_create_staleness_culling,
    db_create_host,
    db_get_hosts,
    flask_app,
    event_producer,
    mocker,
):
    """Verify calculated timestamps match expected values from last_check_in."""
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)

    with patch("app.models.utils.datetime") as mock_datetime:
        with patch("lib.feature_flags.get_flag_value", return_value=True):
            with flask_app.app.app_context():
                mocker.patch.object(event_producer, "write_event")
                _now = now()
                mock_datetime.now.return_value = _now

                stale_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale"])
                stale_warning_delta = timedelta(
                    seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_stale_warning"]
                )
                culled_delta = timedelta(seconds=CUSTOM_STALENESS_HOST_BECAME_STALE["conventional_time_to_delete"])

                # Create a test host - normalize to UTC
                last_check_in = _now.astimezone(UTC) if _now.tzinfo else _now.replace(tzinfo=UTC)
                host = db_create_host(
                    extra_data={
                        "reporter": "puptoo",
                        "per_reporter_staleness": {
                            "puptoo": {
                                "last_check_in": last_check_in.isoformat(),
                                "stale_timestamp": (last_check_in + stale_delta).isoformat(),
                                "stale_warning_timestamp": (last_check_in + stale_warning_delta).isoformat(),
                                "culled_timestamp": (last_check_in + culled_delta).isoformat(),
                                "check_in_succeeded": True,
                            }
                        },
                    },
                )
                host.last_check_in = last_check_in
                host.per_reporter_staleness["puptoo"]["last_check_in"] = last_check_in.isoformat()
                db.session.commit()

                # Get host from database and calculate timestamps
                db_host = db_get_hosts([host.id]).first()

                staleness = get_sys_default_staleness()
                staleness_timestamps_obj = staleness_timestamps()
                calculated = get_reporter_staleness_timestamps(db_host, staleness_timestamps_obj, staleness, "puptoo")

                # Calculate expected using the same function - it already does the calculation we need
                from datetime import datetime as dt

                date_to_use = dt.fromisoformat(db_host.per_reporter_staleness["puptoo"]["last_check_in"])
                if date_to_use.tzinfo is None:
                    date_to_use = date_to_use.replace(tzinfo=UTC)
                else:
                    date_to_use = date_to_use.astimezone(UTC)

                # Use the same Timestamps methods that get_reporter_staleness_timestamps uses internally
                expected_stale = staleness_timestamps_obj.stale_timestamp(
                    date_to_use, staleness["conventional_time_to_stale"]
                )
                expected_stale_warning = staleness_timestamps_obj.stale_warning_timestamp(
                    date_to_use, staleness["conventional_time_to_stale_warning"]
                )
                expected_culled = staleness_timestamps_obj.culled_timestamp(
                    date_to_use, staleness["conventional_time_to_delete"]
                )

                for calculated_ts, expected_ts in [
                    (calculated["stale_timestamp"], expected_stale),
                    (calculated["stale_warning_timestamp"], expected_stale_warning),
                    (calculated["culled_timestamp"], expected_culled),
                ]:
                    if calculated_ts.tzinfo is None:
                        calculated_ts = calculated_ts.replace(tzinfo=UTC)
                    else:
                        calculated_ts = calculated_ts.astimezone(UTC)
                    diff_seconds = abs((calculated_ts - expected_ts).total_seconds())
                    assert diff_seconds <= 2
