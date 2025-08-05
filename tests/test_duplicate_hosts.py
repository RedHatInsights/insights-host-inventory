from __future__ import annotations

from collections.abc import Callable
from random import randint
from unittest import mock
from uuid import UUID

import pytest
from connexion import FlaskApp

from app.config import Config
from app.logging import get_logger
from app.models import Host
from app.models import ProviderType
from host_delete_duplicates import run as host_delete_duplicates_run
from jobs.common import init_db
from lib.db import multi_session_guard
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.mq_utils import MockEventProducer
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import generate_uuid

ID_FACTS = ("provider_id", "subscription_manager_id", "insights_id")
logger = get_logger(__name__)


@pytest.fixture()
def mocked_config(inventory_config: Config) -> Config:
    inventory_config.dry_run = False
    return inventory_config


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("dry_run", (True, False))
def test_delete_duplicate_host(
    inventory_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
    dry_run: bool,
):
    inventory_config.dry_run = dry_run

    # make two hosts that are the same
    canonical_facts = {
        "provider_type": ProviderType.AWS.value,  # Doesn't matter
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }
    old_host = minimal_db_host(canonical_facts=canonical_facts)
    new_host = minimal_db_host(canonical_facts=canonical_facts)

    created_old_host = db_create_host(host=old_host)
    created_new_host = db_create_host(host=new_host)

    assert created_old_host.id != created_new_host.id
    old_host_id = created_old_host.id
    assert created_old_host.canonical_facts["provider_id"] == created_new_host.canonical_facts["provider_id"]

    Session = init_db(inventory_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        num_deleted = host_delete_duplicates_run(
            inventory_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

    logger.info(f"Deleted this many hosts: {num_deleted}")

    assert num_deleted == 1
    assert db_get_host(created_new_host.id)

    if dry_run:
        assert db_get_host(old_host_id)
    else:
        assert not db_get_host(old_host_id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicate_host_more_hosts_than_chunk_size(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_host: Callable[[UUID], Host | None],
):
    canonical_facts_1 = {
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }
    canonical_facts_2 = {
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
    }

    chunk_size = mocked_config.script_chunk_size
    num_hosts = chunk_size * 3 + 15

    # create host before big chunk. Hosts are ordered by modified date so creation
    # order is important
    old_host_1 = minimal_db_host(canonical_facts=canonical_facts_1)
    new_host_1 = minimal_db_host(canonical_facts=canonical_facts_1)

    created_old_host_1 = db_create_host(host=old_host_1)
    created_new_host_1 = db_create_host(host=new_host_1)

    db_create_multiple_hosts(how_many=num_hosts)

    # create another host after
    old_host_2 = minimal_db_host(canonical_facts=canonical_facts_2)
    new_host_2 = minimal_db_host(canonical_facts=canonical_facts_2)

    created_old_host_2 = db_create_host(host=old_host_2)
    created_new_host_2 = db_create_host(host=new_host_2)

    assert created_old_host_1.id != created_new_host_1.id
    assert created_old_host_2.id != created_new_host_2.id

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        num_deleted = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )
    assert num_deleted == 2

    assert db_get_host(created_new_host_1.id)
    assert not db_get_host(created_old_host_1.id)

    assert db_get_host(created_new_host_2.id)
    assert not db_get_host(created_old_host_2.id)


@pytest.mark.host_delete_duplicates
def test_no_hosts_delete_when_no_dupes(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_host: Callable[[UUID], Host | None],
):
    num_hosts = 100
    created_hosts = db_create_multiple_hosts(how_many=num_hosts)
    created_host_ids = [host.id for host in created_hosts]

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        num_deleted = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )
    assert num_deleted == 0

    for host_id in created_host_ids:
        assert db_get_host(host_id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("tested_id", ID_FACTS)
def test_delete_duplicates_id_facts_matching(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
    tested_id: str,
):
    def _gen_canonical_facts():
        facts = {
            "provider_id": generate_uuid(),
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "bios_uuid": generate_uuid(),
            "satellite_id": generate_uuid(),
            "fqdn": generate_random_string(),
        }
        if tested_id == "provider_id":
            facts["provider_type"] = "aws"
        if tested_id in ("insights_id", "subscription_manager_id"):
            facts.pop("provider_id", None)
        if tested_id == "insights_id":
            facts.pop("subscription_manager_id", None)
        return facts

    host_count = 10
    elevated_id = generate_uuid()
    created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(host_count):
        canonical_facts = _gen_canonical_facts()
        canonical_facts[tested_id] = elevated_id
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with less canonical facts
    for _ in range(host_count):
        canonical_facts = {tested_id: elevated_id}
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with more canonical facts
    for _ in range(host_count):
        canonical_facts = _gen_canonical_facts()
        canonical_facts[tested_id] = elevated_id
        canonical_facts["ip_addresses"] = [f"10.0.0.{randint(1, 255)}"]
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    for host in created_hosts:
        assert db_get_host(host.id)

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        deleted_hosts_count = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

    assert deleted_hosts_count == host_count * 3 - 1
    for i in range(len(created_hosts) - 1):
        assert not db_get_host(created_hosts[i].id)
    assert db_get_host(created_hosts[-1].id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("tested_id", ID_FACTS)
def test_delete_duplicates_id_facts_not_matching(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID], Host | None],
    tested_id: str,
):
    canonical_facts = {
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
    }
    if tested_id == "provider_id":
        canonical_facts["provider_type"] = "aws"
    if tested_id in ("insights_id", "subscription_manager_id"):
        canonical_facts.pop("provider_id", None)
    if tested_id == "insights_id":
        canonical_facts.pop("subscription_manager_id", None)

    host_count = 10
    created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(host_count):
        canonical_facts[tested_id] = generate_uuid()
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with less canonical facts
    for _ in range(host_count):
        facts = {tested_id: generate_uuid()}
        host = minimal_db_host(canonical_facts=facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with more canonical facts
    for _ in range(host_count):
        canonical_facts[tested_id] = generate_uuid()
        canonical_facts["ip_addresses"] = ["10.0.0.10"]
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    for host in created_hosts:
        assert db_get_host(host.id)

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        deleted_hosts_count = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

    assert deleted_hosts_count == 0
    for host in created_hosts:
        assert db_get_host(host.id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_last_checked_in(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_create_multiple_hosts: Callable[..., list[Host]],
    db_get_host: Callable[[UUID], Host | None],
):
    """Test that the deletion script always keeps host with the latest 'last_check_in' date"""
    canonical_facts = {
        "provider_id": generate_uuid(),
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
        "provider_type": "aws",
    }
    host_count = 100

    hosts = [minimal_db_host(canonical_facts=canonical_facts) for _ in range(host_count)]
    created_hosts = db_create_multiple_hosts(hosts=hosts)
    host_ids = [host.id for host in created_hosts]
    updated_host = created_hosts[50]
    updated_host._update_last_check_in_date()
    db_create_host(host=updated_host)
    for host_id in host_ids:
        assert db_get_host(host_id)

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        deleted_hosts_count = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )

    assert deleted_hosts_count == host_count - 1
    for host_id in host_ids:
        if host_id != updated_host.id:
            assert not db_get_host(host_id)
        else:
            assert db_get_host(host_id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_multiple_org_ids(
    mocked_config: Config,
    flask_app: FlaskApp,
    event_producer_mock: MockEventProducer,
    notification_event_producer_mock: MockEventProducer,
    db_create_host: Callable[..., Host],
    db_get_host: Callable[[UUID, str], Host | None],
):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
    }
    host1 = minimal_db_host(canonical_facts=canonical_facts, org_id="111111")
    created_host1 = db_create_host(host=host1).id
    host2 = minimal_db_host(canonical_facts=canonical_facts, org_id="222222")
    created_host2 = db_create_host(host=host2).id

    Session = init_db(mocked_config)
    org_ids_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        deleted_hosts_count = host_delete_duplicates_run(
            mocked_config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer_mock,  # type: ignore[arg-type]
            notification_event_producer_mock,  # type: ignore[arg-type]
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            application=flask_app,
        )
    assert deleted_hosts_count == 0
    assert db_get_host(created_host1, "111111")
    assert db_get_host(created_host2, "222222")
