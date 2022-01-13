from copy import deepcopy
from random import choice
from random import randint
from unittest import mock

import pytest

from app import threadctx
from app import UNKNOWN_REQUEST_ID_VALUE
from app.logging import get_logger
from app.models import ProviderType
from host_delete_duplicates import _init_db as _init_db
from host_delete_duplicates import main as host_delete_duplicates_main
from host_delete_duplicates import run as host_delete_duplicates_run
from lib.db import multi_session_guard
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.db_utils import update_host_in_db
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_staleness_timestamps

ELEVATED_IDS = ("provider_id", "insights_id", "subscription_manager_id")
CANONICAL_FACTS = ("fqdn", "satellite_id", "bios_uuid", "ip_addresses", "mac_addresses")
logger = get_logger(__name__)


@pytest.mark.host_delete_duplicates
def test_delete_duplicate_host(
    event_producer_mock, db_create_host, db_get_host, inventory_config, patch_kafka_available
):
    # make two hosts that are the same
    canonical_facts = {
        "provider_type": ProviderType.AWS,  # Doesn't matter
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

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([accounts_session, hosts_session, misc_session]):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        num_deleted = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            accounts_session,
            hosts_session,
            misc_session,
            event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    print("deleted this many hosts:")
    print(num_deleted)

    assert num_deleted == 1
    assert db_get_host(created_new_host.id)
    assert not db_get_host(old_host_id)


@pytest.mark.host_delete_duplicates
def test_delete_dupe_more_hosts_than_chunk_size(
    event_producer_mock, db_get_host, db_create_multiple_hosts, db_create_host, inventory_config, patch_kafka_available
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

    chunk_size = inventory_config.script_chunk_size
    num_hosts = chunk_size * 3 + 15

    # create host before big chunk. Hosts are ordered by modified date so creation
    # order is important
    old_host_1 = minimal_db_host(canonical_facts=canonical_facts_1)
    new_host_1 = minimal_db_host(canonical_facts=canonical_facts_1)

    created_old_host_1 = db_create_host(host=old_host_1)

    created_new_host_1 = db_create_host(host=new_host_1)

    # create big chunk of hosts
    db_create_multiple_hosts(how_many=num_hosts)

    # create another host after
    old_host_2 = minimal_db_host(canonical_facts=canonical_facts_2)
    new_host_2 = minimal_db_host(canonical_facts=canonical_facts_2)

    created_old_host_2 = db_create_host(host=old_host_2)

    created_new_host_2 = db_create_host(host=new_host_2)

    assert created_old_host_1.id != created_new_host_1.id
    assert created_old_host_2.id != created_new_host_2.id

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([accounts_session, hosts_session, misc_session]):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        num_deleted = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            accounts_session,
            hosts_session,
            misc_session,
            event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )
    assert num_deleted == 2

    assert db_get_host(created_new_host_1.id)
    assert not db_get_host(created_old_host_1.id)

    assert db_get_host(created_new_host_2.id)
    assert not db_get_host(created_old_host_2.id)


@pytest.mark.host_delete_duplicates
def test_no_hosts_delete_when_no_dupes(
    event_producer_mock, db_get_host, db_create_multiple_hosts, inventory_config, patch_kafka_available
):
    num_hosts = 100
    created_hosts = db_create_multiple_hosts(how_many=num_hosts)
    created_host_ids = [str(host.id) for host in created_hosts]

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE

    Session = _init_db(inventory_config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()

    with multi_session_guard([accounts_session, hosts_session, misc_session]):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        num_deleted = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            accounts_session,
            hosts_session,
            misc_session,
            event_producer_mock,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )
    assert num_deleted == 0

    for id in created_host_ids:
        assert db_get_host(id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_customer_scenario_1(
    event_producer, db_create_host, db_get_host, inventory_config, patch_kafka_available
):
    staleness_timestamps = get_staleness_timestamps()

    rhsm_id = generate_uuid()
    bios_uuid = generate_uuid()
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": rhsm_id,
        "bios_uuid": bios_uuid,
        "satellite_id": rhsm_id,
        "fqdn": "rn001018",
        "ip_addresses": ["10.230.230.3"],
        "mac_addresses": ["00:50:56:ab:5a:22", "00:00:00:00:00:00"],
    }
    host_data = {
        "stale_timestamp": staleness_timestamps["stale_warning"],
        "reporter": "puptoo",
        "canonical_facts": canonical_facts,
    }
    host1 = minimal_db_host(**host_data)
    created_host1 = db_create_host(host=host1)

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.30"]
    host_data["canonical_facts"].pop("bios_uuid")
    host_data["stale_timestamp"] = staleness_timestamps["stale"]
    host2 = minimal_db_host(**host_data)
    created_host2 = db_create_host(host=host2)

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.3"]
    host3 = minimal_db_host(**host_data)
    created_host3 = db_create_host(host=host3)

    host_data["reporter"] = "yupana"
    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.1"]
    host_data["canonical_facts"]["mac_addresses"] = ["00:50:56:ab:5a:22"]
    host_data["canonical_facts"]["bios_uuid"] = bios_uuid
    host_data["canonical_facts"]["fqdn"] = "rn001018.bcbst.com"
    host_data["stale_timestamp"] = staleness_timestamps["fresh"]
    host4 = minimal_db_host(**host_data)
    created_host4 = db_create_host(host=host4)

    host_data["reporter"] = "puptoo"
    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.15"]
    host_data["canonical_facts"]["mac_addresses"] = ["00:50:56:ab:5a:22", "00:00:00:00:00:00"]
    host_data["canonical_facts"].pop("bios_uuid")
    host_data["canonical_facts"]["fqdn"] = "rn001018"
    host5 = minimal_db_host(**host_data)
    created_host5 = db_create_host(host=host5)

    assert db_get_host(created_host1.id)
    assert db_get_host(created_host2.id)
    assert db_get_host(created_host3.id)
    assert db_get_host(created_host4.id)
    assert db_get_host(created_host5.id)

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    with multi_session_guard(sessions):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert deleted_hosts_count == 4
    assert not db_get_host(created_host1.id)
    assert not db_get_host(created_host2.id)
    assert not db_get_host(created_host3.id)
    assert not db_get_host(created_host4.id)
    assert db_get_host(created_host5.id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_customer_scenario_2(
    event_producer, db_create_host, db_get_host, inventory_config, patch_kafka_available
):
    staleness_timestamps = get_staleness_timestamps()

    rhsm_id = generate_uuid()
    bios_uuid = generate_uuid()
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": rhsm_id,
        "bios_uuid": bios_uuid,
        "satellite_id": rhsm_id,
        "fqdn": "rozrhjrad01.base.srvco.net",
        "ip_addresses": ["10.230.230.10", "10.230.230.13"],
        "mac_addresses": ["00:50:56:ac:56:45", "00:50:56:ac:48:61", "00:00:00:00:00:00"],
    }
    host_data = {
        "stale_timestamp": staleness_timestamps["stale_warning"],
        "reporter": "puptoo",
        "canonical_facts": canonical_facts,
    }
    host1 = minimal_db_host(**host_data)
    created_host1 = db_create_host(host=host1)

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.3", "10.230.230.4"]
    host2 = minimal_db_host(**host_data)
    created_host2 = db_create_host(host=host2)

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.1", "10.230.230.4"]
    host_data["stale_timestamp"] = staleness_timestamps["fresh"]
    host3 = minimal_db_host(**host_data)
    created_host3 = db_create_host(host=host3)

    assert db_get_host(created_host1.id)
    assert db_get_host(created_host2.id)
    assert db_get_host(created_host3.id)

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    with multi_session_guard(sessions):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )
    assert deleted_hosts_count == 2
    assert not db_get_host(created_host1.id)
    assert not db_get_host(created_host2.id)
    assert db_get_host(created_host3.id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("tested_id", ELEVATED_IDS)
def test_delete_duplicates_elevated_ids_matching(
    event_producer, db_create_host, db_get_host, inventory_config, tested_id, patch_kafka_available
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
        if tested_id == "subscription_manager_id":
            facts.pop("insights_id", None)
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

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    with multi_session_guard(sessions):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert deleted_hosts_count == host_count * 3 - 1
    for i in range(len(created_hosts) - 1):
        assert not db_get_host(created_hosts[i].id)
    assert db_get_host(created_hosts[-1].id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("tested_id", ELEVATED_IDS)
def test_delete_duplicates_elevated_ids_not_matching(
    event_producer, db_create_host, db_get_host, inventory_config, tested_id, patch_kafka_available
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
    if tested_id == "subscription_manager_id":
        canonical_facts.pop("insights_id", None)

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

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    with multi_session_guard(sessions):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert deleted_hosts_count == 0
    for host in created_hosts:
        assert db_get_host(host.id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_without_elevated_matching(
    event_producer, db_create_host, db_get_host, inventory_config, patch_kafka_available
):
    canonical_facts = {
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
        "ip_addresses": ["10.0.0.1"],
        "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
    }

    host_count = 10
    created_hosts = []

    # Hosts with less canonical facts
    for fact in canonical_facts:
        facts = {fact: canonical_facts[fact]}
        host = minimal_db_host(canonical_facts=facts)
        created_hosts.append(db_create_host(host=host))

    # # Hosts with more canonical facts
    # for fact in ELEVATED_IDS:
    #     facts = deepcopy(canonical_facts)
    #     facts[fact] = generate_uuid()
    #     if fact == "provider_id":
    #         facts["provider_type"] = "aws"
    #     host = minimal_db_host(canonical_facts=facts)
    #     created_hosts.append(db_create_host(host=host))  <-- Issue with missing elevated ID

    # Hosts with the same amount of canonical facts
    for _ in range(host_count):
        host = minimal_db_host(canonical_facts=canonical_facts)
        created_hosts.append(db_create_host(host=host))

    for host in created_hosts:
        assert db_get_host(host.id)

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    with multi_session_guard(sessions):
        patch_kafka_available("host_delete_duplicates.kafka_available")
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    # Issue with missing elevated ID
    # assert deleted_hosts_count == host_count + len(canonical_facts) + len(ELEVATED_IDS) - 1
    assert deleted_hosts_count == host_count + len(canonical_facts) - 1
    for i in range(len(created_hosts) - 1):
        assert not db_get_host(created_hosts[i].id)
    assert db_get_host(created_hosts[-1].id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("tested_fact", CANONICAL_FACTS)
def test_delete_duplicates_without_elevated_not_matching(
    event_producer, db_create_host, db_get_host, inventory_config, tested_fact, patch_kafka_available
):
    def _generate_fact(fact_name):
        if fact_name == "fqdn":
            return generate_random_string()
        if fact_name == "ip_addresses":
            return [f"{randint(1, 255)}.{randint(0, 255)}.{randint(0, 255)}.{randint(1, 255)}"]
        if fact_name == "mac_addresses":
            hex_chars = "0123456789abcdef"
            addr = ":".join([f"{choice(hex_chars)}{choice(hex_chars)}" for _ in range(6)])
            return [addr]
        return generate_uuid()

    canonical_facts = {
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
        "ip_addresses": ["0.0.0.0"],
        "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
    }

    host_count = 10
    created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(host_count):
        facts = deepcopy(canonical_facts)
        facts[tested_fact] = _generate_fact(tested_fact)
        host = minimal_db_host(canonical_facts=facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with less canonical facts
    for _ in range(host_count):
        facts = {tested_fact: _generate_fact(tested_fact)}
        host = minimal_db_host(canonical_facts=facts)
        created_hosts.append(db_create_host(host=host))

    # Hosts with more canonical facts
    for fact in ELEVATED_IDS:
        facts = deepcopy(canonical_facts)
        facts[tested_fact] = _generate_fact(tested_fact)
        facts[fact] = generate_uuid()
        if fact == "provider_id":
            facts["provider_type"] = "aws"
        host = minimal_db_host(canonical_facts=facts)
        created_hosts.append(db_create_host(host=host))

    for host in created_hosts:
        assert db_get_host(host.id)

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    patch_kafka_available("host_delete_duplicates.kafka_available")
    with multi_session_guard(sessions):
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert deleted_hosts_count == 0
    for host in created_hosts:
        assert db_get_host(host.id)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_last_modified(
    event_producer, db_create_multiple_hosts, db_get_host, inventory_config, patch_kafka_available
):
    """Test that the deletion script always keeps host with the latest 'modified_on' date"""
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
    created_host_ids = [host.id for host in db_create_multiple_hosts(hosts=hosts)]
    updated_host = update_host_in_db(choice(created_host_ids), display_name="new-display-name")
    for host_id in created_host_ids:
        assert db_get_host(host_id)

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    patch_kafka_available("host_delete_duplicates.kafka_available")
    with multi_session_guard(sessions):
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )

    assert deleted_hosts_count == host_count - 1
    for host_id in created_host_ids:
        if host_id != updated_host.id:
            assert not db_get_host(host_id)
        else:
            assert db_get_host(host_id)


@pytest.mark.host_delete_duplicates
@pytest.mark.parametrize("script_function", ["run", "main"])
def test_delete_duplicates_multiple_scenarios(
    event_producer,
    db_create_host,
    db_create_multiple_hosts,
    db_get_host,
    inventory_config,
    script_function,
    patch_kafka_available,
):
    chunk_size = inventory_config.script_chunk_size

    # Customer scenario
    staleness_timestamps = get_staleness_timestamps()

    rhsm_id = generate_uuid()
    bios_uuid = generate_uuid()
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": rhsm_id,
        "bios_uuid": bios_uuid,
        "satellite_id": rhsm_id,
        "fqdn": "rozrhjrad01.base.srvco.net",
        "ip_addresses": ["10.230.230.10", "10.230.230.13"],
        "mac_addresses": ["00:50:56:ac:56:45", "00:50:56:ac:48:61", "00:00:00:00:00:00"],
    }
    host_data = {
        "stale_timestamp": staleness_timestamps["stale_warning"],
        "reporter": "puptoo",
        "canonical_facts": canonical_facts,
    }
    customer_host1 = minimal_db_host(**host_data)
    customer_created_host1 = db_create_host(host=customer_host1).id

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.3", "10.230.230.4"]
    customer_host2 = minimal_db_host(**host_data)
    customer_created_host2 = db_create_host(host=customer_host2).id

    host_data["canonical_facts"]["ip_addresses"] = ["10.230.230.1", "10.230.230.4"]
    host_data["stale_timestamp"] = staleness_timestamps["fresh"]
    customer_host3 = minimal_db_host(**host_data)
    customer_created_host3 = db_create_host(host=customer_host3).id

    assert db_get_host(customer_created_host1)
    assert db_get_host(customer_created_host2)
    assert db_get_host(customer_created_host3)

    # Matching elevated ID
    def _gen_canonical_facts():
        return {
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "bios_uuid": generate_uuid(),
            "satellite_id": generate_uuid(),
            "fqdn": generate_random_string(),
        }

    elevated_matching_host_count = 10
    elevated_id = generate_uuid()
    elevated_matching_created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(elevated_matching_host_count):
        canonical_facts = _gen_canonical_facts()
        canonical_facts["insights_id"] = elevated_id
        host = minimal_db_host(canonical_facts=canonical_facts)
        elevated_matching_created_hosts.append(db_create_host(host=host).id)

    # Hosts with less canonical facts
    for _ in range(elevated_matching_host_count):
        canonical_facts = {"insights_id": elevated_id}
        host = minimal_db_host(canonical_facts=canonical_facts)
        elevated_matching_created_hosts.append(db_create_host(host=host).id)

    # Create a lot of hosts to test that the script deletes duplicates in multiple chunks
    db_create_multiple_hosts(how_many=chunk_size)

    # Hosts with more canonical facts
    for _ in range(elevated_matching_host_count):
        canonical_facts = _gen_canonical_facts()
        canonical_facts["insights_id"] = elevated_id
        canonical_facts["ip_addresses"] = [f"10.0.0.{randint(1, 255)}"]
        host = minimal_db_host(canonical_facts=canonical_facts)
        elevated_matching_created_hosts.append(db_create_host(host=host).id)

    for host in elevated_matching_created_hosts:
        assert db_get_host(host)

    # Elevated IDs not matching
    elevated_not_matching_canonical_facts = _gen_canonical_facts()
    elevated_not_matching_host_count = 10
    elevated_not_matching_created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(elevated_not_matching_host_count):
        elevated_not_matching_canonical_facts["insights_id"] = generate_uuid()
        host = minimal_db_host(canonical_facts=elevated_not_matching_canonical_facts)
        elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    # Hosts with less canonical facts
    for _ in range(elevated_not_matching_host_count):
        facts = {"insights_id": generate_uuid()}
        host = minimal_db_host(canonical_facts=facts)
        elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    # Hosts with more canonical facts
    for _ in range(elevated_not_matching_host_count):
        elevated_not_matching_canonical_facts["insights_id"] = generate_uuid()
        elevated_not_matching_canonical_facts["ip_addresses"] = ["10.0.0.10"]
        host = minimal_db_host(canonical_facts=elevated_not_matching_canonical_facts)
        elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    for host in elevated_not_matching_created_hosts:
        assert db_get_host(host)

    # Without elevated IDs - canonical facts matching
    without_elevated_matching_canonical_facts = {
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
        "ip_addresses": ["10.0.0.1"],
        "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
    }

    without_elevated_matching_host_count = 10
    without_elevated_matching_created_hosts = []

    # Hosts with less canonical facts
    for fact in without_elevated_matching_canonical_facts:
        facts = {fact: without_elevated_matching_canonical_facts[fact]}
        host = minimal_db_host(canonical_facts=facts)
        without_elevated_matching_created_hosts.append(db_create_host(host=host).id)

    # Create a lot of hosts to test that the script deletes duplicates in multiple chunks
    db_create_multiple_hosts(how_many=chunk_size)

    # Hosts with the same amount of canonical facts
    for _ in range(without_elevated_matching_host_count):
        host = minimal_db_host(canonical_facts=without_elevated_matching_canonical_facts)
        without_elevated_matching_created_hosts.append(db_create_host(host=host).id)

    for host in without_elevated_matching_created_hosts:
        assert db_get_host(host)

    # Without elevated IDs - canonical facts not matching
    without_elevated_not_matching_canonical_facts = {
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
        "ip_addresses": ["0.0.0.0"],
        "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
    }

    without_elevated_not_matching_host_count = 10
    without_elevated_not_matching_created_hosts = []

    # Hosts with the same amount of canonical facts
    for _ in range(without_elevated_not_matching_host_count):
        facts = deepcopy(without_elevated_not_matching_canonical_facts)
        facts["fqdn"] = generate_random_string()
        host = minimal_db_host(canonical_facts=facts)
        without_elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    # Hosts with less canonical facts
    for _ in range(without_elevated_not_matching_host_count):
        facts = {"fqdn": generate_random_string()}
        host = minimal_db_host(canonical_facts=facts)
        without_elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    # Hosts with more canonical facts
    for fact in ELEVATED_IDS:
        facts = deepcopy(without_elevated_not_matching_canonical_facts)
        facts["fqdn"] = generate_random_string()
        facts[fact] = generate_uuid()
        if fact == "provider_id":
            facts["provider_type"] = "aws"
        host = minimal_db_host(canonical_facts=facts)
        without_elevated_not_matching_created_hosts.append(db_create_host(host=host).id)

    for host in without_elevated_not_matching_created_hosts:
        assert db_get_host(host)

    patch_kafka_available("host_delete_duplicates.kafka_available")

    if script_function == "run":
        Session = _init_db(inventory_config)
        sessions = [Session() for _ in range(3)]
        with multi_session_guard(sessions):
            deleted_hosts_count = host_delete_duplicates_run(
                inventory_config,
                mock.Mock(),
                *sessions,
                event_producer,
                shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
            )
        assert deleted_hosts_count == elevated_matching_host_count * 3 + without_elevated_matching_host_count + len(
            without_elevated_matching_canonical_facts
        )
    else:
        host_delete_duplicates_main(mock.Mock())

    assert not db_get_host(customer_created_host1)
    assert not db_get_host(customer_created_host2)
    assert db_get_host(customer_created_host3)

    for i in range(len(elevated_matching_created_hosts) - 1):
        assert not db_get_host(elevated_matching_created_hosts[i])
    assert db_get_host(elevated_matching_created_hosts[-1])

    for host in elevated_not_matching_created_hosts:
        assert db_get_host(host)

    for i in range(len(without_elevated_matching_created_hosts) - 1):
        assert not db_get_host(without_elevated_matching_created_hosts[i])
    assert db_get_host(without_elevated_matching_created_hosts[-1])

    for host in without_elevated_not_matching_created_hosts:
        assert db_get_host(host)


@pytest.mark.host_delete_duplicates
def test_delete_duplicates_multiple_accounts(
    event_producer, db_create_host, db_get_host, inventory_config, patch_kafka_available
):
    canonical_facts = {
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "bios_uuid": generate_uuid(),
        "satellite_id": generate_uuid(),
        "fqdn": generate_random_string(),
    }
    host1 = minimal_db_host(canonical_facts=canonical_facts, account="111111")
    created_host1 = db_create_host(host=host1).id
    host2 = minimal_db_host(canonical_facts=canonical_facts, account="222222")
    created_host2 = db_create_host(host=host2).id

    Session = _init_db(inventory_config)
    sessions = [Session() for _ in range(3)]
    patch_kafka_available("host_delete_duplicates.kafka_available")
    with multi_session_guard(sessions):
        deleted_hosts_count = host_delete_duplicates_run(
            inventory_config,
            mock.Mock(),
            *sessions,
            event_producer,
            shutdown_handler=mock.Mock(**{"shut_down.return_value": False}),
        )
    assert deleted_hosts_count == 0
    assert db_get_host(created_host1)
    assert db_get_host(created_host2)
