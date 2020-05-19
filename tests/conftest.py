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
from tests.test_utils import get_required_headers
from tests.test_utils import HOST_URL
from tests.test_utils import inject_qs


@pytest.fixture(scope="session")
def database():
    config = Config(RuntimeEnvironment.server, "testing")
    if database_exists(config.db_uri):
        drop_database(config.db_uri)

    create_database(config.db_uri)

    yield

    drop_database(config.db_uri)


@pytest.fixture(scope="function")
def flask_app(database):
    app = create_app(config_name="testing")

    # binds the app to the current context
    with app.app_context() as ctx:
        db.create_all()
        ctx.push()

        yield app

        ctx.pop()
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def flask_client(flask_app):
    flask_app.testing = True
    return flask_app.test_client()


@pytest.fixture(scope="function")
def api_create_or_update_host(flask_client):
    def _api_create_or_update_host(host_data, query_parameters=None, auth_type="account_number"):
        payload = [item.data() for item in host_data]

        url = inject_qs(HOST_URL, **query_parameters) if query_parameters else HOST_URL

        response = flask_client.post(url, data=json.dumps(payload), headers=get_required_headers(auth_type))

        return response.status_code, json.loads(response.data)

    return _api_create_or_update_host


@pytest.fixture(scope="function")
def api_get_host(flask_client):
    def _api_get_host(url, query_parameters=None):
        url = inject_qs(url, **query_parameters) if query_parameters else url

        response = flask_client.get(url, headers=get_required_headers())

        return response.status_code, json.loads(response.data)

    return _api_get_host


@pytest.fixture(scope="function")
def get_host_from_db(flask_app):
    def _get_host_from_db(host_id):
        return Host.query.get(host_id)

    return _get_host_from_db
