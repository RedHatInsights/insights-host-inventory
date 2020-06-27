import json

import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import create_app
from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from app.models import Host
from app.queue.queue import handle_message
from tests.utils import now
from tests.utils.api_utils import do_request
from tests.utils.api_utils import HOST_URL
from tests.utils.db_utils import minimal_db_host
from tests.utils.mq_utils import MockEventProducer
from tests.utils.mq_utils import wrap_message


@pytest.fixture(scope="session")
def database():
    config = Config(RuntimeEnvironment.TEST)
    if not database_exists(config.db_uri):
        create_database(config.db_uri)

    yield config.db_uri

    drop_database(config.db_uri)


@pytest.fixture(scope="session")
def new_flask_app(database):
    app = create_app(RuntimeEnvironment.TEST)
    app.testing = True

    return app


@pytest.fixture(scope="function")
def flask_app(new_flask_app):
    with new_flask_app.app_context() as ctx:
        new_flask_app.event_producer = MockEventProducer()
        db.create_all()
        ctx.push()

        yield new_flask_app

        ctx.pop()
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_client(flask_app):
    return flask_app.test_client()


@pytest.fixture(scope="function")
def api_create_or_update_host(flask_client):
    def _api_create_or_update_host(host_data, query_parameters=None, extra_headers=None, auth_type="account_number"):
        data = [item.data() for item in host_data]
        return do_request(flask_client.post, HOST_URL, data, query_parameters, extra_headers, auth_type)

    return _api_create_or_update_host


@pytest.fixture(scope="function")
def api_patch_host(flask_client):
    def _api_patch_host(url, host_data, query_parameters=None, extra_headers=None):
        return do_request(flask_client.patch, url, host_data, query_parameters, extra_headers)

    return _api_patch_host


@pytest.fixture(scope="function")
def api_put_host(flask_client):
    def _api_put_host(url, host_data, query_parameters=None, extra_headers=None):
        return do_request(flask_client.put, url, host_data, query_parameters, extra_headers)

    return _api_put_host


@pytest.fixture(scope="function")
def api_get_host(flask_client):
    def _api_get_host(url, query_parameters=None, extra_headers=None):
        return do_request(flask_client.get, url, query_parameters=query_parameters, extra_headers=extra_headers)

    return _api_get_host


@pytest.fixture(scope="function")
def api_delete_host(flask_client):
    def _api_delete_host(host_id, query_parameters=None, extra_headers=None):
        url = f"{HOST_URL}/{host_id}"
        return do_request(flask_client.delete, url, query_parameters=query_parameters, extra_headers=extra_headers)

    return _api_delete_host


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
def mq_create_or_update_host(flask_app, event_producer_mock):
    def _mq_create_or_update_host(host_data, platform_metadata=None, event_producer=event_producer_mock):
        message = wrap_message(host_data=host_data, platform_metadata=platform_metadata)
        handle_message(json.dumps(message), event_producer)

        return event_producer_mock.key, json.loads(event_producer.event), event_producer.headers

    return _mq_create_or_update_host


@pytest.fixture(scope="function")
def event_producer_mock(flask_app):
    return flask_app.event_producer


@pytest.fixture(scope="function")
def event_datetime_mock(mocker):
    mock = mocker.patch("app.queue.events.datetime", **{"now.return_value": now()})
    return mock.now.return_value
