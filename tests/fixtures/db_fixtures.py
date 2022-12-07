import os

import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from app.models import Host
from app.models import HostGroupAssoc
from tests.helpers.db_utils import db_group
from tests.helpers.db_utils import minimal_db_host
from tests.helpers.db_utils import minimal_db_host_dict
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment
from tests.helpers.test_utils import SYSTEM_IDENTITY


@pytest.fixture(scope="session")
def database_name():
    db_data = {
        "INVENTORY_DB_NAME": os.getenv("INVENTORY_DB_NAME", "insights"),
        "INVENTORY_DB_PASS": os.getenv("INVENTORY_DB_PASS", "insights"),
        "INVENTORY_DB_USER": os.getenv("INVENTORY_DB_USER", "insights"),
        "INVENTORY_DB_HOST": os.getenv("INVENTORY_DB_HOST", "localhost"),
        "INVENTORY_DB_PORT": os.getenv("INVENTORY_DB_PORT", "5432"),
    }
    db_data["INVENTORY_DB_NAME"] += "-test"
    with set_environment(db_data):
        yield


@pytest.fixture(scope="session")
def database(database_name):
    config = Config(RuntimeEnvironment.TEST)
    if not database_exists(config.db_uri):
        create_database(config.db_uri)

    yield config.db_uri

    drop_database(config.db_uri)


@pytest.fixture(scope="function")
def db_get_host(flask_app):
    def _db_get_host(host_id):
        return Host.query.get(host_id)

    return _db_get_host


@pytest.fixture(scope="function")
def db_get_hosts(flask_app):
    def _db_get_hosts(host_ids):
        return Host.query.filter(Host.id.in_(host_ids))

    return _db_get_hosts


@pytest.fixture(scope="function")
def db_get_host_by_insights_id(flask_app):
    def _db_get_host_by_insights_id(insights_id):
        return Host.query.filter(Host.canonical_facts["insights_id"].astext == insights_id).one()

    return _db_get_host_by_insights_id


@pytest.fixture(scope="function")
def db_create_host(flask_app):
    def _db_create_host(identity=SYSTEM_IDENTITY, host=None, extra_data=None):
        extra_data = extra_data or {}
        host = host or minimal_db_host(org_id=identity["org_id"], account=identity["account_number"], **extra_data)
        db.session.add(host)
        db.session.commit()
        return host

    return _db_create_host


@pytest.fixture(scope="function")
def db_create_multiple_hosts(flask_app):
    def _db_create_multiple_hosts(identity=SYSTEM_IDENTITY, hosts=None, how_many=10, extra_data=None):
        extra_data = extra_data or {}
        created_hosts = []
        if type(hosts) == list:
            for host in hosts:
                db.session.add(host)
                created_hosts.append(host)
        else:
            for _ in range(how_many):
                host = minimal_db_host(org_id=identity["org_id"], **extra_data)
                db.session.add(host)
                created_hosts.append(host)

        db.session.commit()

        return created_hosts

    return _db_create_multiple_hosts


@pytest.fixture(scope="function")
def db_create_bulk_hosts(flask_app):
    def _db_create_bulk_hosts(identity=SYSTEM_IDENTITY, how_many=10, extra_data=None):
        extra_data = extra_data or {}
        host_dicts = []

        for _ in range(how_many):
            hd = minimal_db_host_dict(org_id=identity["org_id"], **extra_data)
            host_dicts.append(hd)

        db.engine.execute(Host.__table__.insert(), host_dicts)

    return _db_create_bulk_hosts


@pytest.fixture(scope="function")
def db_create_host_in_unknown_state(db_create_host):
    host = minimal_db_host()
    host.stale_timestamp = None
    host.reporter = None
    return db_create_host(host=host)


@pytest.fixture(scope="function")
def models_datetime_mock(mocker):
    mock = mocker.patch("app.models.datetime", **{"now.return_value": now()})
    return mock.now.return_value


@pytest.fixture(scope="function")
def db_create_group(flask_app):
    def _db_create_group(identity=SYSTEM_IDENTITY, group=None, extra_data=None):
        extra_data = extra_data or {}
        group = group or db_group(org_id=identity["org_id"], account=identity["account_number"], **extra_data)
        db.session.add(group)
        db.session.commit()
        return group

    return _db_create_group


@pytest.fixture(scope="function")
def db_create_host_group_assoc(flask_app):
    def _db_create_host_group_assoc(identity=SYSTEM_IDENTITY, host_group=None):
        host_group = host_group or HostGroupAssoc(org_id=identity["org_id"], account=identity["account_number"])
        db.session.add(host_group)
        db.session.commit()
        return host_group

    return _db_create_host_group_assoc
