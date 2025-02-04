from datetime import datetime
from datetime import timedelta
from unittest import mock
from unittest.mock import patch

from app.logging import threadctx
from app.models import db
from host_reaper import run as host_reaper_run

CUSTOM_STALENESS_DELETE_ONLY_IMMUTABLE = {
    "conventional_time_to_stale": 86400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1209600,
    "immutable_time_to_stale": 172800,
    "immutable_time_to_stale_warning": 10368000,
    "immutable_time_to_delete": 1,
}

CUSTOM_STALENESS_DELETE_ONLY_CONVENTIONAL = {
    "conventional_time_to_stale": 86400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1,
    "immutable_time_to_stale": 172800,
    "immutable_time_to_stale_warning": 10368000,
    "immutable_time_to_delete": 15552000,
}

CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE = {
    "conventional_time_to_stale": 86400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1,
    "immutable_time_to_stale": 172800,
    "immutable_time_to_stale_warning": 10368000,
    "immutable_time_to_delete": 1,
}

CUSTOM_STALENESS_NO_HOSTS_TO_DELETE = {
    "conventional_time_to_stale": 86400,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1209600,
    "immutable_time_to_stale": 172800,
    "immutable_time_to_stale_warning": 10368000,
    "immutable_time_to_delete": 15552000,
}

CUSTOM_STALENESS_HOST_BECAME_STALE = {
    "conventional_time_to_stale": 1,
    "conventional_time_to_stale_warning": 604800,
    "conventional_time_to_delete": 1209600,
    "immutable_time_to_stale": 1,
    "immutable_time_to_stale_warning": 10368000,
    "immutable_time_to_delete": 15552000,
}


def test_delete_only_immutable_hosts(
    flask_app,
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_ONLY_IMMUTABLE)

    with patch("app.models.datetime") as mock_datetime:
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
    assert len(db_get_hosts(immutable_hosts).all()) == 0
    assert len(db_get_hosts(conventional_hosts).all()) == 2


def test_delete_only_conventional_hosts(
    flask_app,
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_ONLY_CONVENTIONAL)

    with patch("app.models.datetime") as mock_datetime:
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
    assert len(db_get_hosts(conventional_hosts).all()) == 0


def test_delete_conventional_immutable_hosts(
    flask_app,
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    notification_event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE)

    with patch("app.models.datetime") as mock_datetime:
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

    with patch("app.models.datetime") as mock_datetime:
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
