import logging
from datetime import datetime
from datetime import timedelta
from random import randint
from typing import Any

from sqlalchemy.exc import InvalidRequestError

from app.auth.identity import Identity
from app.models import Group
from app.models import Host
from app.models import HostAppDataAdvisor
from app.models import HostAppDataCompliance
from app.models import HostAppDataMalware
from app.models import HostAppDataPatch
from app.models import HostAppDataRemediations
from app.models import HostAppDataVulnerability
from app.models import Staleness
from app.models import db
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from lib.host_repository import find_existing_host
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import now

DB_FACTS_NAMESPACE = "ns1"
DB_FACTS = {DB_FACTS_NAMESPACE: {"key1": "value1"}}
DB_NEW_FACTS = {"newfact1": "newvalue1", "newfact2": "newvalue2"}
APP_DATA_MODELS = {
    "advisor": HostAppDataAdvisor,
    "vulnerability": HostAppDataVulnerability,
    "patch": HostAppDataPatch,
    "remediations": HostAppDataRemediations,
    "compliance": HostAppDataCompliance,
    "malware": HostAppDataMalware,
}

logger = logging.getLogger(__name__)


def clean_tables():
    def _clean_tables():
        logger.warning("cleaning database tables")
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


def minimal_db_host(**values) -> Host:
    data = minimal_db_host_dict(**values)
    return Host(**data)


def minimal_db_host_dict(**values) -> dict[str, Any]:
    data = {
        "insights_id": generate_uuid(),
        "reporter": "test-reporter",
        **values,
    }
    if "org_id" in values:
        data["org_id"] = values.get("org_id")
    else:
        data["org_id"] = USER_IDENTITY["org_id"]

    return data


def db_host(**values):
    data = {
        "account": USER_IDENTITY["account_number"],
        "org_id": USER_IDENTITY["org_id"],
        "display_name": "test-display-name",
        "ansible_host": "test-ansible-host",
        "insights_id": generate_uuid(),
        "subscription_manager_id": generate_uuid(),
        "bios_uuid": generate_uuid(),
        "fqdn": "test-fqdn",
        "satellite_id": generate_uuid(),
        "ip_addresses": ["10.0.0.1"],
        "mac_addresses": ["aa:bb:cc:dd:ee:ff"],
        "facts": {"ns1": {"key1": "value1"}},
        "tags": {"ns1": {"key1": ["val1", "val2"], "key2": ["val1"]}, "SPECIAL": {"tag": ["ToFind"]}},
        "stale_timestamp": (now() + timedelta(days=randint(1, 7))),
        "reporter": "test-reporter",
        **values,
    }
    return Host(**data)


def db_group(**values):
    data = db_group_dict(**values)
    return Group(**data)


def db_group_dict(**values):
    data = {**values}
    if "org_id" in values:
        data["org_id"] = values.get("org_id")
    else:
        data["org_id"] = USER_IDENTITY["org_id"]

    return data


def db_staleness_culling(**values):
    data = {**values}
    if "org_id" in values:
        data["org_id"] = values.get("org_id")
    else:
        data["org_id"] = USER_IDENTITY["org_id"]

    return Staleness(**data)


def create_reference_host_in_db(insights_id, reporter, system_profile, stale_timestamp):
    host = Host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=insights_id,
        display_name="display_name",
        reporter=reporter,
        stale_timestamp=stale_timestamp,
    )
    db.session.add(host)
    db.session.flush()
    if system_profile:
        host.update_system_profile(system_profile)
    db.session.commit()
    return host


def get_expected_facts_after_update(method, namespace, facts, new_facts):
    if method == "add":
        facts[namespace].update(new_facts)
    elif method == "replace":
        facts[namespace] = new_facts

    return facts


def assert_host_missing_from_db(search_canonical_facts, identity=USER_IDENTITY):
    identity = Identity(identity)
    assert not find_existing_host(identity, search_canonical_facts)


def assert_host_exists_in_db(host_id, search_canonical_facts, identity=USER_IDENTITY):
    identity = Identity(identity)
    found_host = find_existing_host(identity, search_canonical_facts)

    assert found_host
    assert str(host_id) == str(found_host.id)


def create_rhsm_only_host(
    stale_timestamp: datetime | None = None,
    stale_warning_timestamp: datetime | None = None,
    deletion_timestamp: datetime | None = None,
) -> Host:
    """Create a host that is RHSM-only (only has rhsm-system-profile-bridge reporter)"""
    # Use the far future timestamp as default if not specified
    stale_ts = stale_timestamp if stale_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP
    stale_warning_ts = stale_warning_timestamp if stale_warning_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP
    deletion_ts = deletion_timestamp if deletion_timestamp is not None else FAR_FUTURE_STALE_TIMESTAMP

    host = minimal_db_host(
        subscription_manager_id=generate_uuid(),
        reporter="rhsm-system-profile-bridge",
        per_reporter_staleness={
            "rhsm-system-profile-bridge": {
                "last_check_in": now().isoformat(),
                "stale_timestamp": stale_ts.isoformat(),
                "stale_warning_timestamp": stale_warning_ts.isoformat(),
                "culled_timestamp": deletion_ts.isoformat(),
                "check_in_succeeded": True,
            }
        },
    )
    # Set timestamps directly as properties after object creation
    host.stale_timestamp = stale_ts
    host.stale_warning_timestamp = stale_warning_ts
    host.deletion_timestamp = deletion_ts
    return host


def db_create_host_app_data(host_id, org_id, app_name: str, **data):
    if app_name not in APP_DATA_MODELS:
        raise ValueError(f"Unknown app_name: {app_name}. Valid options: {list(APP_DATA_MODELS.keys())}")

    model_class = APP_DATA_MODELS[app_name]
    app_data = model_class(
        host_id=host_id,
        org_id=org_id,
        last_updated=now(),
        **data,
    )
    db.session.add(app_data)
    db.session.commit()
    return app_data
