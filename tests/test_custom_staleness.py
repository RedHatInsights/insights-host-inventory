import time
from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import pytest

from app.logging import threadctx
from app.models import db
from jobs.host_reaper import run as host_reaper_run
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_staleness_url

CUSTOM_STALENESS_DELETE = {
    "conventional_time_to_stale": 104400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1,
}

CUSTOM_STALENESS_NO_HOSTS_TO_DELETE = {
    "conventional_time_to_stale": 104400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1209600,
}

CUSTOM_STALENESS_HOST_BECAME_STALE = {
    "conventional_time_to_stale": 1,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1209600,
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
        mock_datetime.now.return_value = datetime.now() - timedelta(minutes=1)
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
    db_get_hosts,
    db_create_multiple_hosts,
    api_get,
    api_post,
    flask_app,
    event_producer,
    mocker,
    models_datetime_mock,
    num_hosts,
):
    with flask_app.app.app_context():
        mocker.patch.object(event_producer, "write_event")
        _now = models_datetime_mock
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

        # Wait for thread to finish
        time.sleep(1.0)

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
    models_datetime_mock,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with flask_app.app.app_context():
        mocker.patch.object(event_producer, "write_event")
        _now = models_datetime_mock
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

        # Wait for thread to finish
        time.sleep(1.0)

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
    models_datetime_mock,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with flask_app.app.app_context():
        mocker.patch.object(event_producer, "write_event")
        _now = models_datetime_mock
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

        # Wait for thread to finish
        time.sleep(1.0)

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
    models_datetime_mock,
    num_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_HOST_BECAME_STALE)
    with flask_app.app.app_context():
        mocker.patch.object(event_producer, "write_event")
        _now = models_datetime_mock
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

        # Wait for thread to finish
        time.sleep(1.0)

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
