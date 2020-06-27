from datetime import timedelta
from random import randint

from app.models import Host
from lib.host_repository import find_existing_host
from tests.utils import ACCOUNT
from tests.utils import generate_uuid
from tests.utils import now


def minimal_db_host(**values):
    data = {
        "account": ACCOUNT,
        "canonical_facts": {"insights_id": generate_uuid()},
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test-reporter",
        **values,
    }
    return Host(**data)


def db_host(**values):
    data = {
        "account": ACCOUNT,
        "display_name": "test-display-name",
        "ansible_host": "test-ansible-host",
        "canonical_facts": {
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "bios_uuid": generate_uuid(),
            "fqdn": "test-fqdn",
            "satellite_id": generate_uuid(),
            "rhel_machine_id": generate_uuid(),
            "ip_addresses": ["10.0.0.1"],
            "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
        },
        "facts": {"ns1": {"key1": "value1"}},
        "tags": {"ns1": {"key1": ["val1", "val2"], "key2": ["val1"]}, "SPECIAL": {"tag": ["ToFind"]}},
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))).isoformat(),
        "reporter": "test-reporter",
        **values,
    }
    return Host(**data)


def assert_host_exists_in_db(host_id, search_canonical_facts, account=ACCOUNT):
    found_host = find_existing_host(account, search_canonical_facts)

    assert host_id == found_host.id
