import time
from unittest import mock

from app import db
from app import threadctx
from host_reaper import run as host_reaper_run


CUSTOM_STALENESS_DELETE_ONLY_IMMUTABLE = {
    "conventional_staleness_delta": 86400,
    "conventional_stale_warning_delta": 604800,
    "conventional_deletion_delta": 1209600,
    "immutable_staleness_delta": 172800,
    "immutable_stale_warning_delta": 10368000,
    "immutable_deletion_delta": 1,
}

CUSTOM_STALENESS_DELETE_ONLY_CONVENTIONAL = {
    "conventional_staleness_delta": 86400,
    "conventional_stale_warning_delta": 604800,
    "conventional_deletion_delta": 1,
    "immutable_staleness_delta": 172800,
    "immutable_stale_warning_delta": 10368000,
    "immutable_deletion_delta": 15552000,
}

CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE = {
    "conventional_staleness_delta": 86400,
    "conventional_stale_warning_delta": 604800,
    "conventional_deletion_delta": 1,
    "immutable_staleness_delta": 172800,
    "immutable_stale_warning_delta": 10368000,
    "immutable_deletion_delta": 1,
}

CUSTOM_STALENESS_NO_HOSTS_TO_DELETE = {
    "conventional_staleness_delta": 86400,
    "conventional_stale_warning_delta": 604800,
    "conventional_deletion_delta": 1209600,
    "immutable_staleness_delta": 172800,
    "immutable_stale_warning_delta": 10368000,
    "immutable_deletion_delta": 15552000,
}


def test_delete_only_immutable_hosts(
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_ONLY_IMMUTABLE)

    immutable_hosts = db_create_multiple_hosts(how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}})
    immutable_hosts = [host.id for host in immutable_hosts]
    conventional_hosts = db_create_multiple_hosts(how_many=2)
    conventional_hosts = [host.id for host in conventional_hosts]

    time.sleep(1)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )
    assert 0 == len(db_get_hosts(immutable_hosts).all())
    assert 2 == len(db_get_hosts(conventional_hosts).all())


def test_delete_only_conventional_hosts(
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_ONLY_CONVENTIONAL)

    immutable_hosts = db_create_multiple_hosts(how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}})
    immutable_hosts = [host.id for host in immutable_hosts]
    conventional_hosts = db_create_multiple_hosts(how_many=2)
    conventional_hosts = [host.id for host in conventional_hosts]

    time.sleep(1)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )
    assert 2 == len(db_get_hosts(immutable_hosts).all())
    assert 0 == len(db_get_hosts(conventional_hosts).all())


def test_delete_conventional_immutable_hosts(
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_DELETE_CONVENTIONAL_IMMUTABLE)

    immutable_hosts = db_create_multiple_hosts(how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}})
    immutable_hosts = [host.id for host in immutable_hosts]
    conventional_hosts = db_create_multiple_hosts(how_many=2)
    conventional_hosts = [host.id for host in conventional_hosts]

    time.sleep(1)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )
    assert 0 == len(db_get_hosts(immutable_hosts).all())
    assert 0 == len(db_get_hosts(conventional_hosts).all())


def test_no_hosts_to_delete(
    db_create_staleness_culling,
    inventory_config,
    db_create_multiple_hosts,
    event_producer_mock,
    db_get_hosts,
):
    db_create_staleness_culling(**CUSTOM_STALENESS_NO_HOSTS_TO_DELETE)

    immutable_hosts = db_create_multiple_hosts(how_many=2, extra_data={"system_profile_facts": {"host_type": "edge"}})
    immutable_hosts = [host.id for host in immutable_hosts]
    conventional_hosts = db_create_multiple_hosts(how_many=2)
    conventional_hosts = [host.id for host in conventional_hosts]

    time.sleep(1)

    threadctx.request_id = None
    host_reaper_run(
        inventory_config,
        mock.Mock(),
        db.session,
        event_producer_mock,
        shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
    )
    assert 2 == len(db_get_hosts(immutable_hosts).all())
    assert 2 == len(db_get_hosts(conventional_hosts).all())
