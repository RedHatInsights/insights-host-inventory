#!/usr/bin/env python
import json
import tempfile
import uuid
from base64 import b64encode
from datetime import datetime
from datetime import timezone
from struct import unpack
from unittest import main
from unittest import TestCase
from urllib.parse import parse_qs
from urllib.parse import quote_plus as url_quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from sqlalchemy_utils import create_database
from sqlalchemy_utils import database_exists

from app import Config
from app import create_app
from app import db
from app.auth.identity import Identity
from app.environment import RuntimeEnvironment
from app.queue.queue import handle_message
from app.utils import HostWrapper
from tests.test_utils import MockEventProducer
from tests.test_utils import set_environment

HOST_URL = "/api/inventory/v1/hosts"
TAGS_URL = "/api/inventory/v1/tags"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
ACCOUNT = "000501"
SHARED_SECRET = "SuperSecretStuff"


def quote(*args, **kwargs):
    return url_quote(str(args[0]), *args[1:], safe="", **kwargs)


def quote_everything(string):
    encoded = string.encode()
    codes = unpack(f"{len(encoded)}B", encoded)
    return "".join(f"%{code:02x}" for code in codes)


def generate_uuid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


def test_data(**values):
    data = {
        "account": ACCOUNT,
        "display_name": "hi",
        # "insights_id": "1234-56-789",
        # "rhel_machine_id": "1234-56-789",
        # "ip_addresses": ["10.10.0.1", "10.0.0.2"],
        "ip_addresses": ["10.10.0.1"],
        # "mac_addresses": ["c2:00:d0:c8:61:01"],
        # "external_id": "i-05d2313e6b9a42b16"
        "facts": None,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
        **values,
    }
    if not data["facts"]:
        data["facts"] = FACTS
    return data


def build_auth_header(token):
    auth_header = {"Authorization": f"Bearer {token}"}
    return auth_header


def build_valid_auth_header():
    return build_auth_header(SHARED_SECRET)


def inject_qs(url, **kwargs):
    scheme, netloc, path, query, fragment = urlsplit(url)
    params = parse_qs(query)
    params.update(kwargs)
    new_query = urlencode(params, doseq=True)
    return urlunsplit((scheme, netloc, path, new_query, fragment))


class ApiBaseTestCase(TestCase):
    def _create_header(self, auth_header, request_id_header):
        header = auth_header.copy()
        if request_id_header is not None:
            header.update(request_id_header)
        return header

    def _get_valid_auth_header(self):
        identity = Identity(account_number=ACCOUNT)
        dict_ = {"identity": identity._asdict()}
        json_doc = json.dumps(dict_)
        auth_header = {"x-rh-identity": b64encode(json_doc.encode())}
        return auth_header

    def setUp(self):
        """
        Creates the application and a test client to make requests.
        """
        self.app = create_app(RuntimeEnvironment.TEST)
        self.app.event_producer = MockEventProducer()
        self.client = self.app.test_client

    def get(self, path, status=200, return_response_as_json=True, extra_headers={}):
        return self._response_check(
            self.client().get(path, headers={**self._get_valid_auth_header(), **extra_headers}),
            status,
            return_response_as_json,
        )

    def post(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(self.client().post, path, data, status, return_response_as_json)

    def patch(self, path, data, status=200, return_response_as_json=True, extra_headers=None):
        if extra_headers is None:
            extra_headers = {}

        return self._make_http_call(
            self.client().patch, path, data, status, return_response_as_json, extra_headers=extra_headers
        )

    def put(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(self.client().put, path, data, status, return_response_as_json)

    def delete(self, path, status=200, header=None, return_response_as_json=True):
        headers = self._create_header(self._get_valid_auth_header(), header)
        response = self.client().delete(path, headers=headers)
        return self._response_check(response, status, return_response_as_json)

    def verify_error_response(
        self, response, expected_title=None, expected_status=None, expected_detail=None, expected_type=None
    ):
        def _verify_value(field_name, expected_value):
            assert field_name in response
            if expected_value is not None:
                self.assertEqual(response[field_name], expected_value)

        _verify_value("title", expected_title)
        _verify_value("status", expected_status)
        _verify_value("detail", expected_detail)
        _verify_value("type", expected_type)

    def _make_http_call(self, http_method, path, data, status, return_response_as_json=True, extra_headers=None):
        json_data = json.dumps(data)
        headers = self._get_valid_auth_header()
        headers["content-type"] = "application/json"

        if extra_headers:
            headers = {**headers, **extra_headers}

        response = http_method(path, data=json_data, headers=headers)
        return self._response_check(response, status, return_response_as_json)

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(status, response.status_code)
        if return_response_as_json:
            return json.loads(response.data)
        else:
            return response


class DbApiTestCase(ApiBaseTestCase):
    @classmethod
    def setUpClass(cls):
        # create test database
        config = Config(RuntimeEnvironment.TEST)
        if not database_exists(config.db_uri):
            create_database(config.db_uri)

    def setUp(self):
        """
        Initializes the database by creating all tables.
        """
        super().setUp()

        # binds the app to the current context
        with self.app.app_context():
            # create all tables
            db.create_all()

    def tearDown(self):
        """
        Cleans up the database by dropping all tables.
        """
        with self.app.app_context():
            # drop all tables
            db.session.remove()
            db.drop_all()

    def _build_host_id_list_for_url(self, host_list):
        host_id_list = [str(h.id) for h in host_list]

        return ",".join(host_id_list)

    def _verify_host_status(self, response, host_index, expected_status):
        self.assertEqual(expected_status, response["data"][host_index]["status"])

    def _pluck_host_from_response(self, response, host_index):
        return response["data"][host_index]["host"]

    def _validate_host(self, received_host, expected_host, expected_id=id):
        self.assertIsNotNone(received_host["id"])
        self.assertEqual(received_host["id"], expected_id)
        self.assertEqual(received_host["account"], expected_host.account)
        self.assertEqual(received_host["insights_id"], expected_host.insights_id)
        self.assertEqual(received_host["rhel_machine_id"], expected_host.rhel_machine_id)
        self.assertEqual(received_host["subscription_manager_id"], expected_host.subscription_manager_id)
        self.assertEqual(received_host["satellite_id"], expected_host.satellite_id)
        self.assertEqual(received_host["bios_uuid"], expected_host.bios_uuid)
        self.assertEqual(received_host["fqdn"], expected_host.fqdn)
        self.assertEqual(received_host["mac_addresses"], expected_host.mac_addresses)
        self.assertEqual(received_host["ip_addresses"], expected_host.ip_addresses)
        self.assertEqual(received_host["display_name"], expected_host.display_name)
        self.assertEqual(received_host["facts"], expected_host.facts)
        self.assertEqual(received_host["ansible_host"], expected_host.ansible_host)
        self.assertIsNotNone(received_host["created"])
        self.assertIsNotNone(received_host["updated"])


class PaginationBaseTestCase(ApiBaseTestCase):
    def _base_paging_test(self, url, expected_number_of_hosts):
        def _test_get_page(page, expected_count=1):
            test_url = inject_qs(url, page=page, per_page="1")
            response = self.get(test_url, 200)

            self.assertEqual(len(response["results"]), expected_count)
            self.assertEqual(response["count"], expected_count)
            self.assertEqual(response["total"], expected_number_of_hosts)

        if expected_number_of_hosts == 0:
            _test_get_page(1, expected_count=0)
            return

        i = 0

        # Iterate through the pages
        for i in range(1, expected_number_of_hosts + 1):
            with self.subTest(pagination_test=i):
                _test_get_page(str(i))

        # Go one page past the last page and look for an error
        i = i + 1
        with self.subTest(pagination_test=i):
            test_url = inject_qs(url, page=str(i), per_page="1")
            self.get(test_url, 404)

    def _invalid_paging_parameters_test(self, base_url):
        paging_parameters = ["per_page", "page"]
        invalid_values = ["-1", "0", "notanumber"]
        for paging_parameter in paging_parameters:
            for invalid_value in invalid_values:
                with self.subTest(paging_parameter=paging_parameter, invalid_value=invalid_value):
                    test_url = inject_qs(base_url, **{paging_parameter: invalid_value})
                    self.get(test_url, 400)


class PreCreatedHostsBaseTestCase(DbApiTestCase, PaginationBaseTestCase):
    def setUp(self):
        super().setUp()
        self.added_hosts = self.create_hosts()

    def create_hosts(self):
        hosts_to_create = [
            (
                "host1",
                generate_uuid(),
                "host1.domain.test",
                [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                    {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
                    {"namespace": "no", "key": "key", "value": None},
                ],
            ),
            (
                "host2",
                generate_uuid(),
                "host1.domain.test",
                [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
            ),  # the same fqdn is intentional
            (
                "host3",
                generate_uuid(),
                "host2.domain.test",
                [
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": None, "key": "key4", "value": "val4"},
                    {"namespace": None, "key": "key5", "value": None},
                ],
            ),
        ]

        if hasattr(self, "hosts_to_create"):
            self.hosts_to_create = hosts_to_create + self.hosts_to_create
        else:
            self.hosts_to_create = hosts_to_create

        host_list = []

        mock_event_producer = MockEventProducer()

        for host in self.hosts_to_create:
            host_wrapper = HostWrapper()
            host_wrapper.account = ACCOUNT
            host_wrapper.display_name = host[0]
            host_wrapper.insights_id = generate_uuid()
            host_wrapper.rhel_machine_id = generate_uuid()
            host_wrapper.subscription_manager_id = generate_uuid()
            host_wrapper.satellite_id = generate_uuid()
            host_wrapper.bios_uuid = generate_uuid()
            host_wrapper.ip_addresses = ["10.0.0.2"]
            host_wrapper.fqdn = host[2]
            host_wrapper.mac_addresses = ["aa:bb:cc:dd:ee:ff"]
            host_wrapper.external_id = generate_uuid()
            host_wrapper.facts = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
            host_wrapper.tags = host[3]
            host_wrapper.stale_timestamp = now().isoformat()
            host_wrapper.reporter = "test"
            message = {"operation": "add_host", "data": host_wrapper.data()}

            with self.app.app_context():
                handle_message(json.dumps(message), mock_event_producer)

            response_data = json.loads(mock_event_producer.event)

            # add facts object since it's not returned by message
            host_data = {**response_data["host"], "facts": message["data"]["facts"]}
            host_list.append(HostWrapper(host_data))

        return host_list


class HealthTestCase(ApiBaseTestCase):
    """
    Tests the health check endpoint.
    """

    def test_health(self):
        """
        The health check simply returns 200 to any GET request. The response body is
        irrelevant.
        """
        response = self.client().get(HEALTH_URL)  # No identity header.
        self.assertEqual(200, response.status_code)

    def test_metrics(self):
        """
        The metrics endpoint simply returns 200 to any GET request.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            with set_environment({"prometheus_multiproc_dir": temp_dir}):
                response = self.client().get(METRICS_URL)  # No identity header.
                self.assertEqual(200, response.status_code)

    def test_version(self):
        response = self.get(VERSION_URL, 200)
        assert response["version"] is not None


if __name__ == "__main__":
    main()
