import pytest

from app import db
from app.models import Host
from tests.helpers.db_utils import minimal_db_host


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
    def _db_create_host(host=None, extra_data=None):
        extra_data = extra_data or {}
        host = host or minimal_db_host(**extra_data)
        db.session.add(host)
        db.session.commit()
        return host

    return _db_create_host


@pytest.fixture(scope="function")
def db_create_multiple_hosts(flask_app):
    def _db_create_multiple_hosts(hosts=None, how_many=10, extra_data=None):
        extra_data = extra_data or {}
        created_hosts = []
        if type(hosts) == list:
            for host in hosts:
                db.session.add(host)
                created_hosts.append(host)
        else:
            for _ in range(how_many):
                host = minimal_db_host(**extra_data)
                db.session.add(host)
                created_hosts.append(host)

        db.session.commit()

        return created_hosts

    return _db_create_multiple_hosts


@pytest.fixture(scope="function")
def db_create_host_in_unknown_state(db_create_host):
    host = minimal_db_host()
    host.stale_timestamp = None
    host.reporter = None
    return db_create_host(host)
