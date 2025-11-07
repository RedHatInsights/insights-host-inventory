from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import pytest

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.logging import threadctx
from app.models import db
from jobs.host_reaper import run as host_reaper_run
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


def test_delete_all_type_of_hosts(
    flask_app,
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_hosts,
):
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
    flask_app,
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_hosts,
):
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
            _ = db_create_host(
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
            _ = db_create_host(
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
