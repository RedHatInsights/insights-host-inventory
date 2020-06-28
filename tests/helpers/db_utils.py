from datetime import timedelta
from random import randint

from sqlalchemy.exc import InvalidRequestError

from app.models import db
from app.models import Host
from lib.host_repository import find_existing_host
from tests.helpers.test_utils import ACCOUNT
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now

DB_FACTS_NAMESPACE = "ns1"
DB_FACTS = {DB_FACTS_NAMESPACE: {"key1": "value1"}}
DB_NEW_FACTS = {"newfact1": "newvalue1", "newfact2": "newvalue2"}


def clean_tables():
    def _clean_tables():
        try:
            db.session.expire_all()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()
        except InvalidRequestError:
            # Ensures the tables are truncated even if the test expects a SQLException throw
            db.session.rollback()
            return _clean_tables()

    _clean_tables()


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


def get_expected_facts_after_update(method, namespace, facts, new_facts):
    if method == "add":
        facts[namespace].update(new_facts)
    elif method == "replace":
        facts[namespace] = new_facts

    return facts


def assert_host_exists_in_db(host_id, search_canonical_facts, account=ACCOUNT):
    found_host = find_existing_host(account, search_canonical_facts)

    assert host_id == found_host.id
