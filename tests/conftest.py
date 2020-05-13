import json
from typing import List
from typing import Union

import pytest
from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists
from sqlalchemy_utils import drop_database

from app import create_app
from app import db
from app.config import Config
from app.config import RuntimeEnvironment
from app.models import Host
from app.utils import HostWrapper
from tests.test_utils import get_required_headers
from tests.test_utils import HOST_URL
from tests.test_utils import inject_qs
from tests.test_utils import SHARED_SECRET
from tests.test_utils import validate_host


@pytest.fixture(scope="session")
def database():
    config = Config(RuntimeEnvironment.server, "testing")
    if not database_exists(config.db_uri):
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
def create_or_update_host(flask_client, subtests):
    def _create(
        host_data: Union[HostWrapper, List[HostWrapper]],
        status=207,
        host_status=None,
        url=HOST_URL,
        auth_type="account_number",
        skip_host_validation=False,
    ):
        with subtests.test(msg="Creating or updating hosts"):
            if not isinstance(host_data, List):
                host_data = [host_data]

            payload = [item.data() if isinstance(item, HostWrapper) else item for item in host_data]

            response = flask_client.post(url, data=json.dumps(payload), headers=get_required_headers(auth_type))
            assert response.status_code == status

            host_response = json.loads(response.data)

            if skip_host_validation or response.status_code > 299:
                return host_response

            host_status = host_status or [201]
            if not isinstance(host_status, List):
                host_status = [host_status]

            for _key, _host in enumerate(host_data):
                _host = _host if isinstance(_host, HostWrapper) else HostWrapper(_host)
                assert host_response["data"][_key]["status"] == host_status[_key]
                if host_response["data"][_key]["status"] < 299:
                    validate_host(host_response["data"][_key]["host"], _host)

            if len(payload) == 1:
                return host_response["data"][0]["host"]
            return [_host["host"] for _host in host_response["data"]]

    return _create


@pytest.fixture(scope="function")
def get_host(flask_client, subtests):
    def _get(url, status=200, **query_parameters):
        with subtests.test(msg="Retrieving a host"):
            url = inject_qs(url, **query_parameters)
            response = flask_client.get(url, headers=get_required_headers())
            assert response.status_code == status

            return json.loads(response.data)

    return _get


@pytest.fixture(scope="function")
def get_host_from_db(flask_app):
    def _get(host_id):
        return Host.query.filter(Host.id == host_id).first()

    return _get


@pytest.fixture(scope="function")
def paging_test(get_host, subtests):
    def _base_paging_test(url, expected_number_of_hosts):
        def _test_get_page(page, expected_count=1):
            test_url = inject_qs(url, page=page, per_page="1")
            response = get_host(test_url, 200)

            assert len(response["results"]) == expected_count
            assert response["count"] == expected_count
            assert response["total"] == expected_number_of_hosts

        if expected_number_of_hosts == 0:
            _test_get_page(1, expected_count=0)
            return

        i = 0

        # Iterate through the pages
        for i in range(1, expected_number_of_hosts + 1):
            with subtests.test(pagination_test=i):
                _test_get_page(str(i))

        # Go one page past the last page and look for an error
        i = i + 1
        with subtests.test(pagination_test=i):
            test_url = inject_qs(url, page=str(i), per_page="1")
            get_host(test_url, 404)

    return _base_paging_test


@pytest.fixture(scope="function")
def invalid_paging_parameters_test(get_host, subtests):
    def _invalid_paging_parameters_test(base_url):
        paging_parameters = ["per_page", "page"]
        invalid_values = ["-1", "0", "notanumber"]
        for paging_parameter in paging_parameters:
            for invalid_value in invalid_values:
                with subtests.test(paging_parameter=paging_parameter, invalid_value=invalid_value):
                    test_url = inject_qs(base_url, **{paging_parameter: invalid_value})
                    get_host(test_url, 400)

    return _invalid_paging_parameters_test


@pytest.fixture(scope="function")
def mock_env_token(monkeypatch):
    monkeypatch.setenv("INVENTORY_SHARED_SECRET", SHARED_SECRET)
