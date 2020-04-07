#!/usr/bin/env python
import copy
import json
import tempfile
import uuid
from base64 import b64encode
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from functools import partial
from itertools import chain
from json import dumps
from unittest import main
from unittest import mock
from unittest import TestCase
from unittest.mock import ANY
from unittest.mock import call
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.parse import quote_plus as url_quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import dateutil.parser

from api.host_query_xjoin import QUERY as HOST_QUERY
from api.tag import TAGS_QUERY
from app import create_app
from app import db
from app.auth.identity import Identity
from app.culling import Timestamps
from app.models import Host
from app.serialization import serialize_host
from app.utils import HostWrapper
from app.utils import Tag
from host_reaper import run as host_reaper_run
from lib.host_delete import delete_hosts
from lib.host_repository import canonical_fact_host_query
from lib.host_repository import canonical_facts_host_query
from tasks import msg_handler
from test_utils import rename_host_table_and_indexes
from test_utils import set_environment
from test_utils import valid_system_profile

HOST_URL = "/api/inventory/v1/hosts"
TAGS_URL = "/api/inventory/v1/tags"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]
ACCOUNT = "000501"
SHARED_SECRET = "SuperSecretStuff"
MOCK_XJOIN_HOST_RESPONSE = {
    "hosts": {
        "meta": {"total": 2},
        "data": [
            {
                "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                "account": "test",
                "display_name": "test01.rhel7.jharting.local",
                "ansible_host": "test01.rhel7.jharting.local",
                "created_on": "2019-02-10T08:07:03.354307Z",
                "modified_on": "2019-02-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test01.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                },
                "facts": None,
                "stale_timestamp": "2020-02-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
            {
                "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                "account": "test",
                "display_name": "test02.rhel7.jharting.local",
                "ansible_host": "test02.rhel7.jharting.local",
                "created_on": "2019-01-10T08:07:03.354307Z",
                "modified_on": "2019-01-10T08:07:03.354312Z",
                "canonical_facts": {
                    "fqdn": "fqdn.test02.rhel7.jharting.local",
                    "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                    "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                },
                "facts": {
                    "os": {"os.release": "Red Hat Enterprise Linux Server"},
                    "bios": {
                        "bios.vendor": "SeaBIOS",
                        "bios.release_date": "2014-04-01",
                        "bios.version": "1.11.0-2.el7",
                    },
                },
                "stale_timestamp": "2020-01-10T08:07:03.354307Z",
                "reporter": "puptoo",
            },
        ],
    }
}


def quote(*args, **kwargs):
    return url_quote(str(args[0]), *args[1:], safe="", **kwargs)


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


class MockEmitEvent:
    def __init__(self):
        self.events = []

    def __call__(self, e, key=None):
        self.events.append((e, key))


class APIBaseTestCase(TestCase):
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
        self.app = create_app(config_name="testing")
        self.client = self.app.test_client

    def get(self, path, status=200, return_response_as_json=True, extra_headers={}):
        return self._response_check(
            self.client().get(path, headers={**self._get_valid_auth_header(), **extra_headers}),
            status,
            return_response_as_json,
        )

    def post(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(self.client().post, path, data, status, return_response_as_json)

    def patch(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(self.client().patch, path, data, status, return_response_as_json)

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

    def _make_http_call(self, http_method, path, data, status, return_response_as_json=True):
        json_data = json.dumps(data)
        headers = self._get_valid_auth_header()
        headers["content-type"] = "application/json"
        return self._response_check(
            http_method(path, data=json_data, headers=headers), status, return_response_as_json
        )

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(response.status_code, status)
        if return_response_as_json:
            return json.loads(response.data)
        else:
            return response


class DBAPITestCase(APIBaseTestCase):
    @classmethod
    def setUpClass(cls):
        """
        Temporarily rename the host table while the tests run.  This is done
        to make dropping the table at the end of the tests a bit safer.
        """
        rename_host_table_and_indexes()

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
        self.assertEqual(response["data"][host_index]["status"], expected_status)

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


class CreateHostsTestCase(DBAPITestCase):
    def test_create_and_update(self):
        facts = None

        host_data = HostWrapper(test_data(facts=facts))

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        self._validate_host(created_host, host_data, expected_id=original_id)

        created_time = dateutil.parser.parse(created_host["created"])
        current_timestamp = now()
        self.assertGreater(current_timestamp, created_time)
        self.assertLess(current_timestamp - timedelta(minutes=15), created_time)

        host_data.facts = copy.deepcopy(FACTS)

        # Replace facts under the first namespace
        host_data.facts[0]["facts"] = {"newkey1": "newvalue1"}

        # Add a new set of facts under a new namespace
        host_data.facts.append({"namespace": "ns2", "facts": {"key2": "value2"}})

        # Add a new canonical fact
        host_data.rhel_machine_id = generate_uuid()
        host_data.ip_addresses = ["10.10.0.1", "10.0.0.2", "fe80::d46b:2807:f258:c319"]
        host_data.mac_addresses = ["c2:00:d0:c8:61:01"]
        host_data.external_id = "i-05d2313e6b9a42b16"
        host_data.insights_id = generate_uuid()

        # Update the host with the new data
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 200)

        updated_host = self._pluck_host_from_response(response, 0)

        # Make sure the id from the update post matches the id from the create
        self.assertEqual(updated_host["id"], original_id)

        # Verify the timestamp has been modified
        self.assertIsNotNone(updated_host["updated"])
        modified_time = dateutil.parser.parse(updated_host["updated"])
        self.assertGreater(modified_time, created_time)

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        # sanity check
        # host_lookup_results["results"][0]["facts"][0]["facts"]["key2"] = "blah"
        # host_lookup_results["results"][0]["insights_id"] = "1.2.3.4"
        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_with_branch_id(self):
        facts = None

        host_data = HostWrapper(test_data(facts=facts))

        post_url = HOST_URL + "?" + "branch_id=1234"

        # Create the host
        response = self.post(post_url, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

    def test_create_host_update_with_same_insights_id_and_different_canonical_facts(self):
        original_insights_id = generate_uuid()

        host_data = HostWrapper(test_data(facts=None))
        host_data.insights_id = original_insights_id
        host_data.rhel_machine_id = generate_uuid()
        host_data.subscription_manager_id = generate_uuid()
        host_data.satellite_id = generate_uuid()
        host_data.bios_uuid = generate_uuid()
        host_data.fqdn = "original_fqdn"
        host_data.mac_addresses = ["aa:bb:cc:dd:ee:ff"]
        host_data.external_id = "abcdef"

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        self._validate_host(created_host, host_data, expected_id=original_id)

        # Change the canonical facts except for the insights_id
        host_data.rhel_machine_id = generate_uuid()
        host_data.ip_addresses = ["192.168.1.44", "10.0.0.2"]
        host_data.subscription_manager_id = generate_uuid()
        host_data.satellite_id = generate_uuid()
        host_data.bios_uuid = generate_uuid()
        host_data.fqdn = "expected_fqdn"
        host_data.mac_addresses = ["ff:ee:dd:cc:bb:aa"]
        host_data.external_id = "fedcba"
        host_data.facts = [{"namespace": "ns1", "facts": {"newkey": "newvalue"}}]

        # Update the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 200)

        updated_host = self._pluck_host_from_response(response, 0)

        # Verify that the id did not change on the update
        self.assertEqual(updated_host["id"], original_id)

        # Retrieve the host using the id that we first received
        data = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(data["results"][0], host_data, expected_id=original_id)

    @patch("lib.host_repository.canonical_fact_host_query", wraps=canonical_fact_host_query)
    @patch("lib.host_repository.canonical_facts_host_query", wraps=canonical_facts_host_query)
    def test_match_host_by_elevated_id_performance(self, canonical_facts_host_query, canonical_fact_host_query):
        subscription_manager_id = generate_uuid()
        host_data = HostWrapper(test_data(subscription_manager_id=subscription_manager_id))
        create_response = self.post(HOST_URL, [host_data.data()], 207)
        self._verify_host_status(create_response, 0, 201)

        # Create a host with Subscription Manager ID
        insights_id = generate_uuid()
        host_data = HostWrapper(test_data(insights_id=insights_id, subscription_manager_id=subscription_manager_id))

        canonical_fact_host_query.reset_mock()
        canonical_facts_host_query.reset_mock()

        # Update a host with Insights ID and Subscription Manager ID
        update_response = self.post(HOST_URL, [host_data.data()], 207)
        self._verify_host_status(update_response, 0, 200)

        expected_calls = (
            call(ACCOUNT, "insights_id", insights_id),
            call(ACCOUNT, "subscription_manager_id", subscription_manager_id),
        )
        canonical_fact_host_query.assert_has_calls(expected_calls)
        self.assertEqual(canonical_fact_host_query.call_count, len(expected_calls))
        canonical_facts_host_query.assert_not_called()

    def test_create_host_with_empty_facts_display_name_then_update(self):
        # Create a host with empty facts, and display_name
        # then update those fields
        host_data = HostWrapper(test_data(facts=None))
        del host_data.display_name
        del host_data.facts

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        self.assertIsNotNone(created_host["id"])

        original_id = created_host["id"]

        # Update the facts and display name
        host_data.facts = copy.deepcopy(FACTS)
        host_data.display_name = "expected_display_name"

        # Update the hosts
        self.post(HOST_URL, [host_data.data()], 207)

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_and_update_multiple_hosts_with_account_mismatch(self):
        """
        Attempt to create multiple hosts, one host has the wrong account number.
        Verify this causes an error response to be returned.
        """
        facts = None

        host1 = HostWrapper(test_data(display_name="host1", facts=facts))
        host1.ip_addresses = ["10.0.0.1"]
        host1.rhel_machine_id = generate_uuid()

        host2 = HostWrapper(test_data(display_name="host2", facts=facts))
        # Set the account number to the wrong account for this request
        host2.account = "222222"
        host2.ip_addresses = ["10.0.0.2"]
        host2.rhel_machine_id = generate_uuid()

        host_list = [host1.data(), host2.data()]

        # Create the host
        created_host = self.post(HOST_URL, host_list, 207)

        self.assertEqual(len(host_list), len(created_host["data"]))

        self.assertEqual(created_host["errors"], 1)

        self.assertEqual(created_host["data"][0]["status"], 201)
        self.assertEqual(created_host["data"][1]["status"], 400)

    def test_create_host_without_canonical_facts(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.insights_id
        del host_data.rhel_machine_id
        del host_data.subscription_manager_id
        del host_data.satellite_id
        del host_data.bios_uuid
        del host_data.ip_addresses
        del host_data.fqdn
        del host_data.mac_addresses
        del host_data.external_id

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        self.verify_error_response(response_data, expected_title="Invalid request", expected_status=400)

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account

        response_data = self.post(HOST_URL, [host_data.data()], 400)

        self.verify_error_response(
            response_data, expected_title="Bad Request", expected_detail="'account' is a required property - '0'"
        )

    def test_create_host_with_invalid_account(self):
        accounts = ("", "someaccount")
        for account in accounts:
            with self.subTest(account=account):
                host_data = HostWrapper(test_data(account=account, facts=None))

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                self._verify_host_status(response_data, 0, 400)

                response_data = response_data["data"][0]

                self.verify_error_response(
                    response_data,
                    expected_title="Bad Request",
                    expected_detail="{'account': ['Length must be between 1 and 10.']}",
                )

    def test_create_host_with_mismatched_account_numbers(self):
        host_data = HostWrapper(test_data(facts=None))
        host_data.account = ACCOUNT[::-1]

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        self.verify_error_response(
            response_data,
            expected_title="Invalid request",
            expected_detail="The account number associated with the user does not match the account number associated "
            "with the host",
        )

    def test_create_host_with_invalid_facts(self):
        facts_with_no_namespace = copy.deepcopy(FACTS)
        del facts_with_no_namespace[0]["namespace"]

        facts_with_no_facts = copy.deepcopy(FACTS)
        del facts_with_no_facts[0]["facts"]

        facts_with_empty_str_namespace = copy.deepcopy(FACTS)
        facts_with_empty_str_namespace[0]["namespace"] = ""

        invalid_facts = [facts_with_no_namespace, facts_with_no_facts, facts_with_empty_str_namespace]

        for invalid_fact in invalid_facts:
            with self.subTest(invalid_fact=invalid_fact):
                host_data = HostWrapper(test_data(facts=invalid_fact))

                response_data = self.post(HOST_URL, [host_data.data()], 400)

                self.verify_error_response(response_data, expected_title="Bad Request")

    def test_create_host_with_invalid_uuid_field_values(self):
        uuid_field_names = ("insights_id", "rhel_machine_id", "subscription_manager_id", "satellite_id", "bios_uuid")

        for field_name in uuid_field_names:
            with self.subTest(uuid_field=field_name):
                host_data = copy.deepcopy(test_data(facts=None))

                host_data[field_name] = "notauuid"

                response_data = self.post(HOST_URL, [host_data], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_non_nullable_fields_as_none(self):
        non_nullable_field_names = (
            "display_name",
            "account",
            "insights_id",
            "rhel_machine_id",
            "subscription_manager_id",
            "satellite_id",
            "fqdn",
            "bios_uuid",
            "ip_addresses",
            "mac_addresses",
            "external_id",
            "ansible_host",
            "stale_timestamp",
            "reporter",
        )

        host_data = HostWrapper(test_data(facts=None))

        # Have at least one good canonical fact set
        host_data.insights_id = generate_uuid()
        host_data.rhel_machine_id = generate_uuid()

        host_dict = host_data.data()

        for field_name in non_nullable_field_names:
            with self.subTest(field_as_None=field_name):
                invalid_host_dict = copy.deepcopy(host_dict)

                invalid_host_dict[field_name] = None

                response_data = self.post(HOST_URL, [invalid_host_dict], 400)

                self.verify_error_response(response_data, expected_title="Bad Request")

    def test_create_host_without_required_fields(self):
        fields = ("account", "stale_timestamp", "reporter")
        for field in fields:
            with self.subTest(fields=fields):
                data = test_data()
                del data[field]

                host_data = HostWrapper(data)
                response_data = self.post(HOST_URL, [host_data.data()], 400)
                self.verify_error_response(response_data, expected_title="Bad Request")

    def test_create_host_with_valid_ip_address(self):
        valid_ip_arrays = [["blah"], ["1.1.1.1", "sigh"]]

        for ip_array in valid_ip_arrays:
            with self.subTest(ip_array=ip_array):
                host_data = HostWrapper(test_data(facts=None))
                host_data.insights_id = generate_uuid()
                host_data.ip_addresses = ip_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 201)

    def test_create_host_with_invalid_ip_address(self):
        invalid_ip_arrays = [[], [""], ["a" * 256]]

        for ip_array in invalid_ip_arrays:
            with self.subTest(ip_array=ip_array):
                host_data = HostWrapper(test_data(facts=None))
                host_data.insights_id = generate_uuid()
                host_data.ip_addresses = ip_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_valid_mac_address(self):
        valid_mac_arrays = [["blah"], ["11:22:33:44:55:66", "blah"]]

        for mac_array in valid_mac_arrays:
            with self.subTest(mac_array=mac_array):
                host_data = HostWrapper(test_data(facts=None))
                host_data.insights_id = generate_uuid()
                host_data.mac_addresses = mac_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 201)

    def test_create_host_with_invalid_mac_address(self):
        invalid_mac_arrays = [[], [""], ["11:22:33:44:55:66", "a" * 256]]

        for mac_array in invalid_mac_arrays:
            with self.subTest(mac_array=mac_array):
                host_data = HostWrapper(test_data(facts=None))
                host_data.insights_id = generate_uuid()
                host_data.mac_addresses = mac_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_invalid_display_name(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_display_names = ["", "a" * 201]

        for display_name in invalid_display_names:
            with self.subTest(display_name=display_name):
                host_data.display_name = display_name

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_invalid_fqdn(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_fqdns = ["", "a" * 256]

        for fqdn in invalid_fqdns:
            with self.subTest(fqdn=fqdn):
                host_data.fqdn = fqdn

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_invalid_external_id(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_external_ids = ["", "a" * 501]

        for external_id in invalid_external_ids:
            with self.subTest(external_id=external_id):
                host_data.external_id = external_id

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_ansible_host(self):
        # Create a host with ansible_host field
        host_data = HostWrapper(test_data(facts=None))
        host_data.ansible_host = "ansible_host_" + generate_uuid()

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_host_without_ansible_host_then_update(self):
        # Create a host without ansible_host field
        # then update those fields
        host_data = HostWrapper(test_data(facts=None))
        del host_data.ansible_host

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        ansible_hosts = ["ima_ansible_host_" + generate_uuid(), ""]

        # Update the ansible_host
        for ansible_host in ansible_hosts:
            with self.subTest(ansible_host=ansible_host):
                host_data.ansible_host = ansible_host

                # Update the hosts
                self.post(HOST_URL, [host_data.data()], 207)

                host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

                self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_host_with_invalid_ansible_host(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_ansible_host = ["a" * 256]

        for ansible_host in invalid_ansible_host:
            with self.subTest(ansible_host=ansible_host):
                host_data.ansible_host = ansible_host

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host, expected_title="Bad Request")

    def test_create_host_with_invalid_tags(self):
        tags = [
            {
                "namespace": """"qwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiop
                    asdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyu
                    iopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklz
                    xcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyu
                    iopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwer
                    tyuiop""",
                "key": "",
                "value": "val",
            },
            {"namespace": "", "key": "", "value": "val"},
            {"namespace": "              ", "key": "", "value": "val"},
            {
                "namespace": "SPECIAL",
                "key": "something",
                "value": """"qwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiop
                    asdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyu
                    iopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklz
                    xcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyu
                    iopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwer
                    tyuiop""",
            },
            {"namespace": "val", "key": "", "value": ""},
            {"namespace": "val", "key": "", "value": "              "},
            {"namespace": "SPECIAL", "key": "", "value": "val"},
            {"namespace": "NS3", "key": "         ", "value": "val3"},
            {
                "namespace": "NS1",
                "key": """"qwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiop
                    asdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyu
                    iopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklz
                    xcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwertyuiopqwertyu
                    iopasdfghjklzxcvbnmqwertyuiopqwertyuiopasdfghjklzxcvbnmqwer
                    tyuiop""",
                "value": "val3",
            },
        ]

        for tag in tags:
            host_data = HostWrapper(test_data(tags=[tag]))

            response = self.post(HOST_URL, [host_data.data()], 207)

            assert "'status': 400" in str(response)

    def test_create_host_with_invalid_string_tag_format(self):
        tag = "string/tag=format"

        host_data = HostWrapper(test_data(tags=[tag]))

        self.post(HOST_URL, [host_data.data()], 400)

    def test_create_host_with_invalid_tag_format(self):
        tag = {"namespace": "spam", "key": {"foo": "bar"}, "value": "eggs"}

        host_data = HostWrapper(test_data(tags=[tag]))

        self.post(HOST_URL, [host_data.data()], 400)

    def test_create_host_with_tags(self):
        host_data = HostWrapper(
            test_data(
                tags=[
                    {"namespace": "NS3", "key": "key2", "value": "val2"},
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": "Sat", "key": "prod", "value": None},
                ]
            )
        )

        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

        host_tags = self.get(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]

        expected_tags = [
            {"namespace": "NS1", "key": "key3", "value": "val3"},
            {"namespace": "NS3", "key": "key2", "value": "val2"},
            {"namespace": "Sat", "key": "prod", "value": None},
        ]

        for tag, expected_tag in zip(host_tags, expected_tags):
            self.assertEqual(tag, expected_tag)

    def test_create_host_with_tags_special_characters(self):
        host_data = HostWrapper(
            test_data(tags=[{"namespace": "NS1", "key": "ŠtěpánΔ12!@#$%^&*()_+-=", "value": "ŠtěpánΔ:;'|,./?~`"}])
        )

        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

        host_tags = self.get(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]

        expected_tags = [{"namespace": "NS1", "key": "ŠtěpánΔ12!@#$%^&*()_+-=", "value": "ŠtěpánΔ:;'|,./?~`"}]

        for tag, expected_tag in zip(host_tags, expected_tags):
            self.assertEqual(tag, expected_tag)

    def test_create_host_with_tag_without_namespace(self):
        tags = [
            {"namespace": None, "key": "key3", "value": "val3"},
            {"key": "key2", "value": "val2"},
            {"namespace": "Sat", "key": "prod", "value": None},
        ]

        host_data = HostWrapper(test_data(tags=tags))

        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

        host_tags = self.get(f"{HOST_URL}/{original_id}/tags", 200)["results"][original_id]

        expected_tags = [
            {"namespace": "Sat", "key": "prod", "value": None},
            {"namespace": None, "key": "key2", "value": "val2"},
            {"namespace": None, "key": "key3", "value": "val3"},
        ]

        for tag, expected_tag in zip(host_tags, expected_tags):
            self.assertEqual(tag, expected_tag)

    def test_create_host_with_20_byte_MAC_address(self):
        system_profile = {
            "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33"}]
        }

        host_data = HostWrapper(test_data(system_profile=system_profile))

        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_host_with_too_long_MAC_address(self):
        system_profile = {
            "network_interfaces": [{"mac_address": "00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44"}]
        }

        host_data = HostWrapper(test_data(system_profile=system_profile))

        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 400)

    def test_create_host_with_empty_json_key_in_system_profile(self):
        samples = (
            {"disk_devices": [{"options": {"": "invalid"}}]},
            {"disk_devices": [{"options": {"ro": True, "uuid": "0", "": "invalid"}}]},
            {"disk_devices": [{"options": {"nested": {"uuid": "0", "": "invalid"}}}]},
            {"disk_devices": [{"options": {"ro": True}}, {"options": {"": "invalid"}}]},
        )

        for sample in samples:
            with self.subTest(system_profile=sample):
                host_data = HostWrapper(test_data(system_profile=sample))
                response = self.post(HOST_URL, [host_data.data()], 207)
                self._verify_host_status(response, 0, 400)

    def test_create_host_with_empty_json_key_in_facts(self):
        samples = (
            [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
            [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
            [{"facts": {"foo": "bar", "": "invalid"}, "namespace": "rhsm"}],
            [{"facts": {"foo": "bar"}, "namespace": "valid"}, {"facts": {"": "invalid"}, "namespace": "rhsm"}],
        )

        for facts in samples:
            with self.subTest(facts=facts):
                host_data = HostWrapper(test_data(facts=facts))
                response = self.post(HOST_URL, [host_data.data()], 207)
                self._verify_host_status(response, 0, 400)


class CreateHostsWithStaleTimestampTestCase(DBAPITestCase):
    def _add_host(self, expected_status, **values):
        host_data = HostWrapper(test_data(fqdn="match this host", **values))
        response = self.post(HOST_URL, [host_data.data()], 207)
        self._verify_host_status(response, 0, expected_status)
        created_host = self._pluck_host_from_response(response, 0)
        return created_host.get("id")

    def _retrieve_host(self, host_id):
        with self.app.app_context():
            return Host.query.filter(Host.id == host_id).first()

    def test_create_host_without_culling_fields(self):
        fields_to_delete = (("stale_timestamp", "reporter"), ("stale_timestamp",), ("reporter",))
        for fields in fields_to_delete:
            with self.subTest(fields=fields):
                host_data = test_data(fqdn="match this host")
                for field in fields:
                    del host_data[field]
                self.post(HOST_URL, [host_data], 400)

    def test_create_host_with_null_culling_fields(self):
        culling_fields = (("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter"))
        for fields in culling_fields:
            host_data = test_data(fqdn="match this host", **{field: None for field in fields})
            self.post(HOST_URL, [host_data], 400)

    def test_create_host_with_empty_culling_fields(self):
        culling_fields = (("stale_timestamp",), ("reporter",), ("stale_timestamp", "reporter"))
        for fields in culling_fields:
            with self.subTest(fields=fields):
                self._add_host(400, **{field: "" for field in fields})

    def test_create_host_with_invalid_stale_timestamp(self):
        self._add_host(400, stale_timestamp="not a timestamp")

    def test_create_host_with_stale_timestamp_and_reporter(self):
        stale_timestamp = now()
        reporter = "some reporter"
        created_host_id = self._add_host(201, stale_timestamp=stale_timestamp.isoformat(), reporter=reporter)

        retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(stale_timestamp, retrieved_host.stale_timestamp)
        self.assertEqual(reporter, retrieved_host.reporter)

    def test_update_stale_timestamp_from_same_reporter(self):
        current_timestamp = now()

        old_stale_timestamp = current_timestamp + timedelta(days=1)
        reporter = "some reporter"

        created_host_id = self._add_host(201, stale_timestamp=old_stale_timestamp.isoformat(), reporter=reporter)
        old_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)
        self.assertEqual(reporter, old_retrieved_host.reporter)

        new_stale_timestamp = current_timestamp + timedelta(days=2)
        self._add_host(200, stale_timestamp=new_stale_timestamp.isoformat(), reporter=reporter)

        new_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(new_stale_timestamp, new_retrieved_host.stale_timestamp)
        self.assertEqual(reporter, new_retrieved_host.reporter)

    def test_dont_update_stale_timestamp_from_same_reporter(self):
        current_timestamp = now()

        old_stale_timestamp = current_timestamp + timedelta(days=2)
        reporter = "some reporter"

        created_host_id = self._add_host(201, stale_timestamp=old_stale_timestamp.isoformat(), reporter=reporter)
        old_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)

        new_stale_timestamp = current_timestamp + timedelta(days=1)
        self._add_host(200, stale_timestamp=new_stale_timestamp.isoformat(), reporter=reporter)

        new_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, new_retrieved_host.stale_timestamp)

    def test_update_stale_timestamp_from_different_reporter(self):
        current_timestamp = now()

        old_stale_timestamp = current_timestamp + timedelta(days=2)
        old_reporter = "old reporter"

        created_host_id = self._add_host(201, stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter)
        old_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)
        self.assertEqual(old_reporter, old_retrieved_host.reporter)

        new_stale_timestamp = current_timestamp + timedelta(days=1)
        new_reporter = "new reporter"
        self._add_host(200, stale_timestamp=new_stale_timestamp.isoformat(), reporter=new_reporter)

        new_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(new_stale_timestamp, new_retrieved_host.stale_timestamp)
        self.assertEqual(new_reporter, new_retrieved_host.reporter)

    def test_update_stale_host_timestamp_from_next_reporter(self):
        current_timestamp = now()

        old_stale_timestamp = current_timestamp - timedelta(days=1)  # stale host
        old_reporter = "old reporter"

        created_host_id = self._add_host(201, stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter)
        old_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)
        self.assertEqual(old_reporter, old_retrieved_host.reporter)

        new_stale_timestamp = current_timestamp + timedelta(days=1)
        new_reporter = "new reporter"
        self._add_host(200, stale_timestamp=new_stale_timestamp.isoformat(), reporter=new_reporter)

        new_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(new_stale_timestamp, new_retrieved_host.stale_timestamp)
        self.assertEqual(new_reporter, new_retrieved_host.reporter)

    def test_dont_update_stale_timestamp_from_different_reporter(self):
        current_timestamp = now()

        old_stale_timestamp = current_timestamp + timedelta(days=1)
        old_reporter = "old reporter"

        created_host_id = self._add_host(201, stale_timestamp=old_stale_timestamp.isoformat(), reporter=old_reporter)

        old_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)
        self.assertEqual(old_reporter, old_retrieved_host.reporter)

        new_stale_timestamp = current_timestamp + timedelta(days=2)
        self._add_host(200, stale_timestamp=new_stale_timestamp.isoformat(), reporter="new_reporter")

        new_retrieved_host = self._retrieve_host(created_host_id)

        self.assertEqual(old_stale_timestamp, new_retrieved_host.stale_timestamp)
        self.assertEqual(old_reporter, new_retrieved_host.reporter)


class DeleteHostsBaseTestCase(DBAPITestCase):
    def _get_hosts(self, host_ids):
        url_part = ",".join(host_ids)
        return self.get(f"{HOST_URL}/{url_part}", 200)

    def _assert_event_is_valid(self, event, key, host, timestamp):
        self.assertIsInstance(event, dict)
        expected_keys = {"timestamp", "type", "id", "account", "insights_id", "request_id"}
        self.assertEqual(set(event.keys()), expected_keys)

        self.assertEqual(timestamp.replace(tzinfo=timezone.utc).isoformat(), event["timestamp"])
        self.assertEqual("delete", event["type"])

        self.assertEqual(host.insights_id, event["insights_id"])

        self.assertEqual(key, host.id)

    def _get_hosts_from_db(self, host_ids):
        with self.app.app_context():
            return tuple(str(host.id) for host in Host.query.filter(Host.id.in_(host_ids)))

    def _check_hosts_are_present(self, host_ids):
        retrieved_ids = self._get_hosts_from_db(host_ids)
        self.assertEqual(retrieved_ids, host_ids)

    def _check_hosts_are_deleted(self, host_ids):
        retrieved_ids = self._get_hosts_from_db(host_ids)
        self.assertEqual(retrieved_ids, ())


class CullingBaseTestCase(APIBaseTestCase):
    def _nullify_culling_fields(self, host_id):
        with self.app.app_context():
            host = db.session.query(Host).get(host_id)
            host.stale_timestamp = None
            host.reporter = None
            db.session.add(host)
            db.session.commit()


@patch("lib.host_delete.emit_event", new_callable=MockEmitEvent)
class HostReaperTestCase(DeleteHostsBaseTestCase, CullingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.now_timestamp = datetime.utcnow()
        self.staleness_timestamps = {
            "fresh": self.now_timestamp + timedelta(hours=1),
            "stale": self.now_timestamp,
            "stale_warning": self.now_timestamp - timedelta(weeks=1),
            "culled": self.now_timestamp - timedelta(weeks=2),
        }

    def _run_host_reaper(self):
        with patch("app.events.datetime", **{"utcnow.return_value": self.now_timestamp}):
            with self.app.app_context():
                config = self.app.config["INVENTORY_CONFIG"]
                host_reaper_run(config, db.session)

    def _add_hosts(self, data):
        post = []
        for d in data:
            host = HostWrapper(test_data(insights_id=generate_uuid(), **d))
            post.append(host.data())

        response = self.post(HOST_URL, post, 207)

        hosts = []
        for i in range(len(data)):
            self._verify_host_status(response, i, 201)
            added_host = self._pluck_host_from_response(response, i)
            hosts.append(HostWrapper(added_host))

        return hosts

    def _get_hosts(self, host_ids):
        url_part = ",".join(host_ids)
        return self.get(f"{HOST_URL}/{url_part}")

    def test_culled_host_is_removed(self, emit_event):
        added_host = self._add_hosts(
            ({"stale_timestamp": self.staleness_timestamps["culled"].isoformat(), "reporter": "some reporter"},)
        )[0]
        self._check_hosts_are_present((added_host.id,))

        self._run_host_reaper()
        self._check_hosts_are_deleted((added_host.id,))

        self.assertEqual(len(emit_event.events), 1)

        event, key = emit_event.events[0]
        self._assert_event_is_valid(json.loads(event), key, added_host, self.now_timestamp)

    def test_non_culled_host_is_not_removed(self, emit_event):
        hosts_to_add = []
        for stale_timestamp in (
            self.staleness_timestamps["stale_warning"],
            self.staleness_timestamps["stale"],
            self.staleness_timestamps["fresh"],
        ):
            hosts_to_add.append({"stale_timestamp": stale_timestamp.isoformat(), "reporter": "some reporter"})

        added_hosts = self._add_hosts(hosts_to_add)
        added_host_ids = tuple(host.id for host in added_hosts)
        self._check_hosts_are_present(added_host_ids)

        self._run_host_reaper()

        self._check_hosts_are_present(added_host_ids)

    def test_unknown_host_is_not_removed(self, emit_event):
        added_hosts = self._add_hosts(({},))
        added_host_id = added_hosts[0].id
        self._check_hosts_are_present((added_host_id,))

        self._nullify_culling_fields(added_host_id)

        self._run_host_reaper()
        self._check_hosts_are_present((added_host_id,))
        self.assertEqual(len(emit_event.events), 0)


class ResolveDisplayNameOnCreationTestCase(DBAPITestCase):
    def test_create_host_without_display_name_and_without_fqdn(self):
        """
        This test should verify that the display_name is set to the id
        when neither the display name or fqdn is set.
        """
        host_data = HostWrapper(test_data(facts=None))
        del host_data.display_name
        del host_data.fqdn

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        # Explicitly set the display_name to the be id...this is expected here
        host_data.display_name = created_host["id"]

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)

    def test_create_host_without_display_name_and_with_fqdn(self):
        """
        This test should verify that the display_name is set to the
        fqdn when a display_name is not passed in but the fqdn is passed in.
        """
        expected_display_name = "fred.flintstone.bedrock.com"

        host_data = HostWrapper(test_data(facts=None))
        del host_data.display_name
        host_data.fqdn = expected_display_name

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}", 200)

        # Explicitly set the display_name ...this is expected here
        host_data.display_name = expected_display_name

        self._validate_host(host_lookup_results["results"][0], host_data, expected_id=original_id)


class BulkCreateHostsTestCase(DBAPITestCase):
    def _get_valid_auth_header(self):
        return build_valid_auth_header()

    def test_create_and_update_multiple_hosts_with_different_accounts(self):
        with set_environment({"INVENTORY_SHARED_SECRET": SHARED_SECRET}):
            facts = None

            host1 = HostWrapper(test_data(display_name="host1", facts=facts))
            host1.account = "111111"
            host1.ip_addresses = ["10.0.0.1"]
            host1.rhel_machine_id = generate_uuid()

            host2 = HostWrapper(test_data(display_name="host2", facts=facts))
            host2.account = "222222"
            host2.ip_addresses = ["10.0.0.2"]
            host2.rhel_machine_id = generate_uuid()

            host_list = [host1.data(), host2.data()]

            # Create the host
            response = self.post(HOST_URL, host_list, 207)

            self.assertEqual(len(host_list), len(response["data"]))
            self.assertEqual(response["total"], len(response["data"]))

            self.assertEqual(response["errors"], 0)

            for host in response["data"]:
                self.assertEqual(host["status"], 201)

            host_list[0]["id"] = response["data"][0]["host"]["id"]
            host_list[0]["bios_uuid"] = generate_uuid()
            host_list[0]["display_name"] = "fred"

            host_list[1]["id"] = response["data"][1]["host"]["id"]
            host_list[1]["bios_uuid"] = generate_uuid()
            host_list[1]["display_name"] = "barney"

            # Update the host
            updated_host = self.post(HOST_URL, host_list, 207)

            self.assertEqual(updated_host["errors"], 0)

            i = 0
            for host in updated_host["data"]:
                self.assertEqual(host["status"], 200)

                expected_host = HostWrapper(host_list[i])

                self._validate_host(host["host"], expected_host, expected_id=expected_host.id)

                i += 1


class PaginationBaseTestCase(APIBaseTestCase):
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


class CreateHostsWithSystemProfileTestCase(DBAPITestCase, PaginationBaseTestCase):
    def test_create_host_with_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()

        host["system_profile"] = valid_system_profile()

        # Create the host
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        # verify system_profile is not included
        self.assertNotIn("system_profile", created_host)

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile", 200)
        actual_host = host_lookup_results["results"][0]

        self.assertEqual(original_id, actual_host["id"])

        self.assertEqual(actual_host["system_profile"], host["system_profile"])

    def test_create_host_with_system_profile_and_query_with_branch_id(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()

        host["system_profile"] = valid_system_profile()

        # Create the host
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        # verify system_profile is not included
        self.assertNotIn("system_profile", created_host)

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile?branch_id=1234", 200)
        actual_host = host_lookup_results["results"][0]

        self.assertEqual(original_id, actual_host["id"])

        self.assertEqual(actual_host["system_profile"], host["system_profile"])

    def test_create_host_without_system_profile_then_update_with_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        # List of tuples (system profile change, expected system profile)
        system_profiles = [({}, {})]

        # Only set the enabled_services to start out with
        enabled_services_only_system_profile = {"enabled_services": ["firewalld"]}
        system_profiles.append((enabled_services_only_system_profile, enabled_services_only_system_profile))

        # Set the entire system profile...overwriting the enabled_service
        # set from before
        full_system_profile = valid_system_profile()
        system_profiles.append((full_system_profile, full_system_profile))

        # Change the enabled_services
        full_system_profile = {**full_system_profile, **enabled_services_only_system_profile}
        system_profiles.append((enabled_services_only_system_profile, full_system_profile))

        # Make sure an empty system profile doesn't overwrite the data
        system_profiles.append(({}, full_system_profile))

        for i, (system_profile, expected_system_profile) in enumerate(system_profiles):
            with self.subTest(system_profile=i):
                mq_message = {"id": original_id, "request_id": None, "system_profile": system_profile}
                with self.app.app_context():
                    msg_handler(mq_message)

                host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile", 200)
                actual_host = host_lookup_results["results"][0]

                self.assertEqual(original_id, actual_host["id"])

                self.assertEqual(actual_host["system_profile"], expected_system_profile)

    def test_create_host_with_null_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()
        host["system_profile"] = None

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 400)

        self.verify_error_response(response, expected_title="Bad Request", expected_status=400)

    def test_create_host_with_system_profile_with_invalid_data(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()

        # List of tuples (system profile change, expected system profile)
        system_profiles = [
            {"infrastructure_type": "i" * 101, "infrastructure_vendor": "i" * 101, "cloud_provider": "i" * 101}
        ]

        for system_profile in system_profiles:
            with self.subTest(system_profile=system_profile):
                host["system_profile"] = system_profile

                # Create the host
                response = self.post(HOST_URL, [host], 207)

                self._verify_host_status(response, 0, 400)

                self.assertEqual(response["errors"], 1)

    def test_create_host_with_system_profile_with_different_yum_urls(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)

        yum_urls = [
            "file:///cdrom/",
            "http://foo.com http://foo.com",
            "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-$releasever-$basearch",
            "https://codecs.fedoraproject.org/openh264/$releasever/$basearch/debug/",
        ]

        for yum_url in yum_urls:
            with self.subTest(yum_url=yum_url):
                host["rhel_machine_id"] = generate_uuid()
                host["system_profile"] = {
                    "yum_repos": [{"name": "repo1", "gpgcheck": True, "enabled": True, "base_url": yum_url}]
                }

                # Create the host
                response = self.post(HOST_URL, [host], 207)

                self._verify_host_status(response, 0, 201)

                created_host = self._pluck_host_from_response(response, 0)
                original_id = created_host["id"]

                # Verify that the system profile data is saved
                host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile", 200)
                actual_host = host_lookup_results["results"][0]

                self.assertEqual(original_id, actual_host["id"])

                self.assertEqual(actual_host["system_profile"], host["system_profile"])

    def test_create_host_with_system_profile_with_different_cloud_providers(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)

        cloud_providers = ["cumulonimbus", "cumulus", "c" * 100]

        for cloud_provider in cloud_providers:
            with self.subTest(cloud_provider=cloud_provider):
                host["rhel_machine_id"] = generate_uuid()
                host["system_profile"] = {"cloud_provider": cloud_provider}

                # Create the host
                response = self.post(HOST_URL, [host], 207)

                self._verify_host_status(response, 0, 201)

                created_host = self._pluck_host_from_response(response, 0)
                original_id = created_host["id"]

                # Verify that the system profile data is saved
                host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile", 200)
                actual_host = host_lookup_results["results"][0]

                self.assertEqual(original_id, actual_host["id"])

                self.assertEqual(actual_host["system_profile"], host["system_profile"])

    def test_get_system_profile_of_host_that_does_not_have_system_profile(self):
        facts = None
        expected_system_profile = {}

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = generate_uuid()

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get(f"{HOST_URL}/{original_id}/system_profile", 200)
        actual_host = host_lookup_results["results"][0]

        self.assertEqual(original_id, actual_host["id"])

        self.assertEqual(actual_host["system_profile"], expected_system_profile)

    def test_get_system_profile_of_multiple_hosts(self):
        facts = None
        host_id_list = []
        expected_system_profiles = []

        for i in range(2):
            host = test_data(display_name="host1", facts=facts)
            host["ip_addresses"] = [f"10.0.0.{i}"]
            host["rhel_machine_id"] = generate_uuid()
            host["system_profile"] = valid_system_profile()
            host["system_profile"]["number_of_cpus"] = i

            response = self.post(HOST_URL, [host], 207)
            self._verify_host_status(response, 0, 201)

            created_host = self._pluck_host_from_response(response, 0)
            original_id = created_host["id"]

            host_id_list.append(original_id)
            expected_system_profiles.append({"id": original_id, "system_profile": host["system_profile"]})

        url_host_id_list = ",".join(host_id_list)
        test_url = f"{HOST_URL}/{url_host_id_list}/system_profile"
        host_lookup_results = self.get(test_url, 200)

        self.assertEqual(len(expected_system_profiles), len(host_lookup_results["results"]))
        for expected_system_profile in expected_system_profiles:
            self.assertIn(expected_system_profile, host_lookup_results["results"])

        self._base_paging_test(test_url, len(expected_system_profiles))
        self._invalid_paging_parameters_test(test_url)

    def test_get_system_profile_of_host_that_does_not_exist(self):
        expected_count = 0
        expected_total = 0
        host_id = generate_uuid()
        results = self.get(f"{HOST_URL}/{host_id}/system_profile", 200)
        self.assertEqual(results["count"], expected_count)
        self.assertEqual(results["total"], expected_total)

    def test_get_system_profile_with_invalid_host_id(self):
        invalid_host_ids = ["notauuid", f"{generate_uuid()},notuuid"]
        for host_id in invalid_host_ids:
            with self.subTest(invalid_host_id=host_id):
                response = self.get(f"{HOST_URL}/{host_id}/system_profile", 400)
                self.verify_error_response(response, expected_title="Bad Request", expected_status=400)


class PreCreatedHostsBaseTestCase(DBAPITestCase, PaginationBaseTestCase):
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
                ],
            ),
        ]
        host_list = []

        for host in hosts_to_create:
            host_wrapper = HostWrapper()
            host_wrapper.id = generate_uuid()
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

            response_data = self.post(HOST_URL, [host_wrapper.data()], 207)
            host_list.append(HostWrapper(response_data["data"][0]["host"]))

        return host_list


@patch("api.host.emit_event")
class PatchHostTestCase(PreCreatedHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.now_timestamp = datetime.utcnow()

    def test_update_fields(self, emit_event):
        original_id = self.added_hosts[0].id

        patch_docs = [
            {"ansible_host": "NEW_ansible_host"},
            {"ansible_host": ""},
            {"display_name": "fred_flintstone"},
            {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"},
        ]

        for patch_doc in patch_docs:
            with self.subTest(valid_patch_doc=patch_doc):
                response_data = self.patch(f"{HOST_URL}/{original_id}", patch_doc, 200)

                response_data = self.get(f"{HOST_URL}/{original_id}", 200)

                host = response_data["results"][0]

                for key in patch_doc:
                    self.assertEqual(host[key], patch_doc[key])

    def test_patch_with_branch_id_parameter(self, emit_event):
        self.added_hosts[0].id

        patch_doc = {"display_name": "branch_id_test"}

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}?branch_id=123"

        self.patch(test_url, patch_doc, 200)

    def test_update_fields_on_multiple_hosts(self, emit_event):
        patch_doc = {"display_name": "fred_flintstone", "ansible_host": "barney_rubble"}

        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)

        test_url = f"{HOST_URL}/{url_host_id_list}"

        self.patch(test_url, patch_doc, 200)

        response_data = self.get(test_url, 200)

        for host in response_data["results"]:
            for key in patch_doc:
                self.assertEqual(host[key], patch_doc[key])

    def test_patch_on_non_existent_host(self, emit_event):
        non_existent_id = generate_uuid()

        patch_doc = {"ansible_host": "NEW_ansible_host"}

        self.patch(f"{HOST_URL}/{non_existent_id}", patch_doc, status=404)

    def test_patch_on_multiple_hosts_with_some_non_existent(self, emit_event):
        non_existent_id = generate_uuid()
        original_id = self.added_hosts[0].id

        patch_doc = {"ansible_host": "NEW_ansible_host"}

        self.patch(f"{HOST_URL}/{non_existent_id},{original_id}", patch_doc)

    def test_invalid_data(self, emit_event):
        original_id = self.added_hosts[0].id

        invalid_data_list = [
            {"ansible_host": "a" * 256},
            {"ansible_host": None},
            {},
            {"display_name": None},
            {"display_name": ""},
        ]

        for patch_doc in invalid_data_list:
            with self.subTest(invalid_patch_doc=patch_doc):
                response = self.patch(f"{HOST_URL}/{original_id}", patch_doc, status=400)

                self.verify_error_response(response, expected_title="Bad Request", expected_status=400)

    def test_invalid_host_id(self, emit_event):
        patch_doc = {"display_name": "branch_id_test"}
        host_id_lists = ["notauuid", f"{self.added_hosts[0].id},notauuid"]
        for host_id_list in host_id_lists:
            with self.subTest(host_id_list=host_id_list):
                self.patch(f"{HOST_URL}/{host_id_list}", patch_doc, 400)

    def test_patch_produces_update_event(self, emit_event):
        with patch("app.queue.egress.datetime", **{"utcnow.return_value": self.now_timestamp}):
            patch_doc = {"display_name": "patch_event_test"}
            host_to_patch = self.added_hosts[0].id
            self.patch(f"{HOST_URL}/{host_to_patch}", patch_doc, 200)
            event_message = json.loads(emit_event.call_args[0][0])
            emit_event.assert_called_once()
            expected_event_message = {
                "type": "updated",
                "host": {
                    "stale_timestamp": self.added_hosts[0].stale_timestamp.replace("T", " "),
                    "display_name": "patch_event_test",
                    "reporter": "test",
                    "id": self.added_hosts[0].id,
                    "account": "000501",
                    "ansible_host": None,
                    "tags": [{}],
                },
                "platform_metadata": {},
                "metadata": {"request_id": "-1"},
                "timestamp": self.now_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            }

            self.assertEqual(event_message, expected_event_message)


class DeleteHostsErrorTestCase(DBAPITestCase):
    def test_delete_non_existent_host(self):
        url = HOST_URL + "/" + generate_uuid()

        self.delete(url, 404)

    def test_delete_with_invalid_host_id(self):
        url = HOST_URL + "/" + "notauuid"

        self.delete(url, 400)


class DeleteHostsEventTestCase(PreCreatedHostsBaseTestCase, DeleteHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.host_to_delete = self.added_hosts[0]
        self.delete_url = HOST_URL + "/" + self.host_to_delete.id
        self.timestamp = datetime.utcnow()

    def _delete(self, url_query="", header=None):
        with patch("lib.host_delete.emit_event", new_callable=MockEmitEvent) as m:
            with patch("app.events.datetime", **{"utcnow.return_value": self.timestamp}):
                url = f"{self.delete_url}{url_query}"
                self.delete(url, 200, header, return_response_as_json=False)
                event, key = m.events[0]
                return json.loads(event), key

    def test_create_then_delete(self):
        self._check_hosts_are_present((self.host_to_delete.id,))
        event, key = self._delete()
        self._assert_event_is_valid(event, key, self.host_to_delete, self.timestamp)
        self._check_hosts_are_deleted((self.host_to_delete.id,))

    def test_create_then_delete_with_branch_id(self):
        self._check_hosts_are_present((self.host_to_delete.id,))
        event, key = self._delete(url_query="?branch_id=1234")
        self._assert_event_is_valid(event, key, self.host_to_delete, self.timestamp)
        self._check_hosts_are_deleted((self.host_to_delete.id,))

    def test_create_then_delete_with_request_id(self):
        request_id = generate_uuid()
        header = {"x-rh-insights-request-id": request_id}
        event, key = self._delete(header=header)
        self._assert_event_is_valid(event, key, self.host_to_delete, self.timestamp)
        self.assertEqual(request_id, event["request_id"])

    def test_create_then_delete_without_request_id(self):
        self._check_hosts_are_present((self.host_to_delete.id,))
        event, key = self._delete(header=None)
        self._assert_event_is_valid(event, key, self.host_to_delete, self.timestamp)
        self.assertEqual("-1", event["request_id"])


@patch("lib.host_delete.emit_event")
class DeleteHostsRaceConditionTestCase(PreCreatedHostsBaseTestCase):
    class DeleteHostsMock:
        @classmethod
        def create_mock(cls, hosts_ids_to_delete):
            def _constructor(select_query):
                return cls(hosts_ids_to_delete, select_query)

            return _constructor

        def __init__(self, host_ids_to_delete, original_query):
            self.host_ids_to_delete = host_ids_to_delete
            self.original_query = delete_hosts(original_query)

        def __getattr__(self, item):
            """
            Forwards all calls to the original query, only intercepting the actual SELECT.
            """
            return self.__iter__ if item == "__iter__" else getattr(self.original_query, item)

        def _delete_hosts(self):
            delete_query = Host.query.filter(Host.id.in_(self.host_ids_to_delete))
            delete_query.delete(synchronize_session=False)
            delete_query.session.commit()

        def __iter__(self, *args, **kwargs):
            """
            Intercepts the actual SELECT by first running the query and then deleting the hosts,
            causing the race condition.
            """
            iterator = self.original_query.__iter__(*args, **kwargs)
            self._delete_hosts()
            return iterator

    def test_delete_when_one_host_is_deleted(self, emit_event):
        host_id = self.added_hosts[0].id
        url = HOST_URL + "/" + host_id
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock([host_id])):
            # One host queried, but deleted by a different process. No event emitted yet returning
            # 200 OK.
            self.delete(url, 200, return_response_as_json=False)
            emit_event.assert_not_called()

    def test_delete_when_all_hosts_are_deleted(self, emit_event):
        host_id_list = [self.added_hosts[0].id, self.added_hosts[1].id]
        url = HOST_URL + "/" + ",".join(host_id_list)
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock(host_id_list)):
            # Two hosts queried, but both deleted by a different process. No event emitted yet
            # returning 200 OK.
            self.delete(url, 200, return_response_as_json=False)
            emit_event.assert_not_called()

    def test_delete_when_some_hosts_is_deleted(self, emit_event):
        host_id_list = [self.added_hosts[0].id, self.added_hosts[1].id]
        url = HOST_URL + "/" + ",".join(host_id_list)
        with patch("api.host.delete_hosts", self.DeleteHostsMock.create_mock(host_id_list[0:1])):
            # Two hosts queried, one of them deleted by a different process. Only one event emitted,
            # returning 200 OK.
            self.delete(url, 200, return_response_as_json=False)
            emit_event.assert_called_once()


class QueryTestCase(PreCreatedHostsBaseTestCase):
    def test_query_all(self):
        response = self.get(HOST_URL, 200)

        host_list = self.added_hosts.copy()
        host_list.reverse()

        expected_host_list = [h.data() for h in host_list]
        self.assertEqual(response["results"], expected_host_list)

        self._base_paging_test(HOST_URL, len(self.added_hosts))
        self._invalid_paging_parameters_test(HOST_URL)

    def test_query_using_display_name(self):
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?display_name=" + host_list[0].display_name)

        self.assertEqual(len(response["results"]), 1)
        self.assertEqual(response["results"][0]["fqdn"], host_list[0].fqdn)
        self.assertEqual(response["results"][0]["insights_id"], host_list[0].insights_id)
        self.assertEqual(response["results"][0]["display_name"], host_list[0].display_name)

    def test_query_using_fqdn_two_results(self):
        expected_host_list = [self.added_hosts[0], self.added_hosts[1]]

        response = self.get(HOST_URL + "?fqdn=" + expected_host_list[0].fqdn)

        self.assertEqual(len(response["results"]), 2)
        for result in response["results"]:
            self.assertEqual(result["fqdn"], expected_host_list[0].fqdn)
            assert any(result["insights_id"] == host.insights_id for host in expected_host_list)
            assert any(result["display_name"] == host.display_name for host in expected_host_list)

    def test_query_using_fqdn_one_result(self):
        expected_host_list = [self.added_hosts[2]]

        response = self.get(HOST_URL + "?fqdn=" + expected_host_list[0].fqdn)

        self.assertEqual(len(response["results"]), 1)
        for result in response["results"]:
            self.assertEqual(result["fqdn"], expected_host_list[0].fqdn)
            assert any(result["insights_id"] == host.insights_id for host in expected_host_list)
            assert any(result["display_name"] == host.display_name for host in expected_host_list)

    def test_query_using_non_existant_fqdn(self):
        response = self.get(HOST_URL + "?fqdn=ROFLSAUCE.com")

        self.assertEqual(len(response["results"]), 0)

    def test_query_using_display_name_substring(self):
        host_list = self.added_hosts.copy()
        host_list.reverse()

        host_name_substr = host_list[0].display_name[:-2]

        test_url = HOST_URL + "?display_name=" + host_name_substr

        response = self.get(test_url)

        expected_host_list = [h.data() for h in host_list]
        self.assertEqual(response["results"], expected_host_list)

        self._base_paging_test(test_url, len(self.added_hosts))
        self._invalid_paging_parameters_test(test_url)


class TagsPreCreatedHostsBaseTestCase(PreCreatedHostsBaseTestCase):
    def setUp(self):
        super().setUp()
        host_wrapper = HostWrapper()
        host_wrapper.account = ACCOUNT
        host_wrapper.display_name = "host4"
        host_wrapper.insights_id = generate_uuid()
        host_wrapper.tags = []
        host_wrapper.stale_timestamp = now().isoformat()
        host_wrapper.reporter = "test"

        response_data = self.post(HOST_URL, [host_wrapper.data()], 207)
        self.added_hosts.append(HostWrapper(response_data["data"][0]["host"]))

    def _assert_host_ids_in_response(self, response, expected_hosts):
        response_ids = [host["id"] for host in response["results"]]
        expected_ids = [host.id for host in expected_hosts]
        self.assertEqual(response_ids, expected_ids)


class QueryByHostIdTestCase(PreCreatedHostsBaseTestCase, PaginationBaseTestCase):
    def _base_query_test(self, host_id_list, expected_host_list):
        url = f"{HOST_URL}/{host_id_list}"
        response = self.get(url)

        self.assertEqual(response["count"], len(expected_host_list))
        self.assertEqual(len(response["results"]), len(expected_host_list))

        host_data = [host.data() for host in expected_host_list]
        for host in host_data:
            self.assertIn(host, response["results"])
        for host in response["results"]:
            self.assertIn(host, host_data)

        self._base_paging_test(url, len(expected_host_list))
        self._invalid_paging_parameters_test(url)

    def test_query_existent_hosts(self):
        host_lists = [self.added_hosts[0:1], self.added_hosts[1:3], self.added_hosts]
        for host_list in host_lists:
            with self.subTest(host_list=host_list):
                host_id_list = self._build_host_id_list_for_url(host_list)
                self._base_query_test(host_id_list, host_list)

    def test_query_single_non_existent_host(self):
        self._base_query_test(generate_uuid(), [])

    def test_query_multiple_hosts_with_some_non_existent(self):
        host_list = self.added_hosts[0:1]
        existent_host_id_list = self._build_host_id_list_for_url(host_list)
        non_existent_host_id = generate_uuid()
        host_id_list = f"{non_existent_host_id},{existent_host_id_list}"
        self._base_query_test(host_id_list, host_list)

    def test_query_invalid_host_id(self):
        bad_id_list = ["notauuid", "1234blahblahinvalid"]
        only_bad_id = bad_id_list.copy()

        # Can’t have empty string as an only ID, that results in 404 Not Found.
        more_bad_id_list = bad_id_list + [""]
        valid_id = self.added_hosts[0].id
        with_bad_id = [f"{valid_id},{bad_id}" for bad_id in more_bad_id_list]

        for host_id_list in chain(only_bad_id, with_bad_id):
            with self.subTest(host_id_list=host_id_list):
                self.get(f"{HOST_URL}/{host_id_list}", 400)

    def test_query_host_id_without_hyphens(self):
        host_lists = [self.added_hosts[0:1], self.added_hosts]
        for original_host_list in host_lists:
            with self.subTest(host_list=original_host_list):
                # deepcopy host.__data to insulate original_host_list from changes.
                host_data = (host.data() for host in original_host_list)
                host_data = (copy.deepcopy(host) for host in host_data)
                query_host_list = [HostWrapper(host) for host in host_data]

                # Remove the hyphens from one of the valid hosts.
                query_host_list[0].id = uuid.UUID(query_host_list[0].id, version=4).hex

                host_id_list = self._build_host_id_list_for_url(query_host_list)
                self._base_query_test(host_id_list, original_host_list)

    def test_query_with_branch_id_parameter(self):
        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)
        # branch_id parameter is accepted, but doesn’t affect results.
        self._base_query_test(f"{url_host_id_list}?branch_id=123", self.added_hosts)

    def test_query_invalid_paging_parameters(self):
        url_host_id_list = self._build_host_id_list_for_url(self.added_hosts)
        base_url = f"{HOST_URL}/{url_host_id_list}"

        paging_parameters = ["per_page", "page"]
        invalid_values = ["-1", "0", "notanumber"]
        for paging_parameter in paging_parameters:
            for invalid_value in invalid_values:
                with self.subTest(paging_parameter=paging_parameter, invalid_value=invalid_value):
                    self.get(f"{base_url}?{paging_parameter}={invalid_value}", 400)


class QueryByHostnameOrIdTestCase(PreCreatedHostsBaseTestCase):
    def _base_query_test(self, query_value, expected_number_of_hosts):
        test_url = HOST_URL + "?hostname_or_id=" + query_value

        response = self.get(test_url)

        self.assertEqual(len(response["results"]), expected_number_of_hosts)

        self._base_paging_test(test_url, expected_number_of_hosts)
        self._invalid_paging_parameters_test(test_url)

    def test_query_using_display_name_as_hostname(self):
        host_list = self.added_hosts

        self._base_query_test(host_list[0].display_name, 2)

    def test_query_using_fqdn_as_hostname(self):
        host_list = self.added_hosts

        self._base_query_test(host_list[2].fqdn, 1)

    def test_query_using_id(self):
        host_list = self.added_hosts

        self._base_query_test(host_list[0].id, 1)

    def test_query_using_non_existent_hostname(self):
        self._base_query_test("NotGonnaFindMe", 0)

    def test_query_using_non_existent_id(self):
        self._base_query_test(generate_uuid(), 0)


class QueryByInsightsIdTestCase(PreCreatedHostsBaseTestCase):
    def _test_url(self, query_value):
        return HOST_URL + "?insights_id=" + query_value

    def _base_query_test(self, query_value, expected_number_of_hosts):
        test_url = self._test_url(query_value)

        response = self.get(test_url)

        self.assertEqual(len(response["results"]), expected_number_of_hosts)

        self._base_paging_test(test_url, expected_number_of_hosts)
        self._invalid_paging_parameters_test(test_url)

    def test_query_with_matching_insights_id(self):
        host_list = self.added_hosts

        self._base_query_test(host_list[0].insights_id, 1)

    def test_query_with_no_matching_insights_id(self):
        uuid_that_does_not_exist_in_db = generate_uuid()
        self._base_query_test(uuid_that_does_not_exist_in_db, 0)

    def test_query_with_invalid_insights_id(self):
        test_url = self._test_url("notauuid")
        self.get(test_url, 400)

    def test_query_with_maching_insights_id_and_branch_id(self):
        valid_insights_id = self.added_hosts[0].insights_id

        test_url = HOST_URL + "?insights_id=" + valid_insights_id + "&branch_id=123"

        self.get(test_url, 200)


@patch("api.host_query_db.canonical_fact_host_query", wraps=canonical_fact_host_query)
@patch("api.host_query_db.canonical_facts_host_query", wraps=canonical_facts_host_query)
class QueryByCanonicalFactPerformanceTestCase(DBAPITestCase):
    def test_query_using_fqdn_not_subset_match(self, canonical_facts_host_query, canonical_fact_host_query):
        fqdn = "some fqdn"
        self.get(f"{HOST_URL}?fqdn={fqdn}")
        canonical_facts_host_query.assert_not_called()
        canonical_fact_host_query.assert_called_once_with(ACCOUNT, "fqdn", fqdn)

    def test_query_using_insights_id_not_subset_match(self, canonical_facts_host_query, canonical_fact_host_query):
        insights_id = "ff13a346-19cb-42ae-9631-44c42927fb92"
        self.get(f"{HOST_URL}?insights_id={insights_id}")
        canonical_facts_host_query.assert_not_called()
        canonical_fact_host_query.assert_called_once_with(ACCOUNT, "insights_id", insights_id)


class QueryByTagTestCase(PreCreatedHostsBaseTestCase, PaginationBaseTestCase):
    def _compare_responses(self, expected_response_list, response_list, test_url):
        self.assertEqual(len(expected_response_list), len(response_list["results"]))
        for host, result in zip(expected_response_list, response_list["results"]):
            self.assertEqual(host.id, result["id"])
        self._base_paging_test(test_url, len(expected_response_list))

    def test_get_host_by_tag(self):
        """
        Get only the one host with the special tag to find on it.
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]  # host with tag SPECIAL/tag=ToFind

        test_url = f"{HOST_URL}?tags=SPECIAL/tag=ToFind"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_multiple_hosts_by_tag(self):
        """
        Get only the one host with the special tag to find on it.
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0], host_list[1]]  # hosts with tag "NS1/key1=val1"

        test_url = f"{HOST_URL}?tags=NS1/key1=val1&order_by=updated&order_how=ASC"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_by_multiple_tags(self):
        """
        Get only the host with all three tags on it and not the other host
        which both have some, but not all of the tags we query for.
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[1]]
        # host with tags ["NS1/key1=val1", "NS2/key2=val2", "NS3/key3=val3"]

        test_url = f"{HOST_URL}?tags=NS1/key1=val1,NS2/key2=val2,NS3/key3=val3"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_by_subset_of_tags(self):
        """
        Get a host using a subset of it's tags
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[1]]
        # host with tags ["NS1/key1=val1", "NS2/key2=val2", "NS3/key3=val3"]

        test_url = f"{HOST_URL}?tags=NS1/key1=val1,NS3/key3=val3"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_with_different_tags_same_namespace(self):
        """
        get a host with two tags in the same namespace with diffent key and same value
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]  # host with tags ["NS1/key1=val1", "NS1/key2=val1"]

        test_url = f"{HOST_URL}?tags=NS1/key1=val1,NS1/key2=val1"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_no_host_with_different_tags_same_namespace(self):
        """
        Don’t get a host with two tags in the same namespace, from which only one match. This is a
        regression test.
        """
        test_url = f"{HOST_URL}?tags=NS1/key1=val2,NS1/key2=val1"
        response_list = self.get(test_url, 200)

        # self.added_hosts[0] would have been matched by NS1/key2=val1, this must not happen.
        self.assertEqual(0, len(response_list["results"]))

    def test_get_host_with_same_tags_different_namespaces(self):
        """
        get a host with two tags in the same namespace with diffent key and same value
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[2]]  # host with tags ["NS3/key3=val3", "NS1/key3=val3"]

        test_url = f"{HOST_URL}?tags=NS3/key3=val3,NS1/key3=val3"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_with_tag_no_value(self):
        """
        Attempt to find host with a tag with no value
        """
        test_url = f"{HOST_URL}?tags=namespace/key"
        self.get(test_url, 200)

    def test_get_host_with_tag_no_namespace(self):
        """
        Attempt to find host with a tag with no namespace.
        """
        test_url = f"{HOST_URL}?tags=key=value"
        self.get(test_url, 400)

    def test_get_host_with_invalid_tag_no_key(self):
        """
        Attempt to find host with an incomplete tag (no key).
        Expects 400 response.
        """
        test_url = f"{HOST_URL}?tags=namespace/=Value"
        self.get(test_url, 400)

    def test_get_host_by_display_name_and_tag(self):
        """
        Attempt to get only the host with the specified key and
        the specified display name
        """

        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]
        # host with tag NS1/key1=val1 and host_name "host1"

        test_url = f"{HOST_URL}?tags=NS1/key1=val1&display_name=host1"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_by_display_name_and_tag_backwards(self):
        """
        Attempt to get only the host with the specified key and
        the specified display name, but the parameters are backwards
        """

        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]
        # host with tag NS1/key1=val1 and host_name "host1"

        test_url = f"{HOST_URL}?display_name=host1&tags=NS1/key1=val1"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_namespace_too_long(self):
        """
        send a request to find hosts with a string tag where the length
        of the namespace excedes the 255 character limit
        """

        test_url = (
            f"{HOST_URL}?tags=JBctjABIKUmEqOmjRnwPDCFskVoTsbbZLyIAdedQU"
            "TTTJOOAGeaKBHDESrvuxwpDsFzDItsOlZPufuKDcaktqldVXWDTandhRCTBgrQXriFPjg"
            "WrlWBoawOdHxkPggFDbqRkmALBBEEeDUnEHYedydlvNWSWuEwIiExkRPzJxnVzlNLgcQq"
            "WfKqmQBhJtKhNMPhmmyTBJaRqWriDMhIPNibsHalYyYbuNJUVUZRhLrhtbOTGAtwLFwUE"
            "GCfxMvnpLNzLHwIXhtSiehQupukwYRQbJRBUMMXkODyCCWCeHvDwoIthoKRYPhCfPhViH"
            "rcRZvwKQJPtjKfCRHWKgneLGfwcENsMARiCUCxGZLs/key=val"
        )

        response = self.get(test_url, 400)

        assert "namespace" in str(response)

    def test_get_host_key_too_long(self):
        """
        send a request to find hosts with a string tag where the length
        of the namespace excedes the 255 character limit
        """

        test_url = (
            f"{HOST_URL}?tags=NS/JBctjABIKUmEqOmjRnwPDCFskVoTsbbZLyIAde"
            "dQUTTTJOOAGeaKBHDESrvuxwpDsFzDItsOlZPufuKDcaktqldVXWDTandhRCTBgrQXriF"
            "PjgWrlWBoawOdHxkPggFDbqRkmALBBEEeDUnEHYedydlvNWSWuEwIiExkRPzJxnVzlNLg"
            "cQqWfKqmQBhJtKhNMPhmmyTBJaRqWriDMhIPNibsHalYyYbuNJUVUZRhLrhtbOTGAtwLF"
            "wUEGCfxMvnpLNzLHwIXhtSiehQupukwYRQbJRBUMMXkODyCCWCeHvDwoIthoKRYPhCfPh"
            "ViHrcRZvwKQJPtjKfCRHWKgneLGfwcENsMARiCUCxGZLs=val"
        )

        response = self.get(test_url, 400)

        assert "key" in str(response)

    def test_get_host_value_too_long(self):
        """
        send a request to find hosts with a string tag where the length
        of the namespace excedes the 255 character limit
        """

        test_url = (
            f"{HOST_URL}?tags=NS/key=JBctjABIKUmEqOmjRnwPDCFskVoTsbbZLy"
            "IAdedQUTTTJOOAGeaKBHDESrvuxwpDsFzDItsOlZPufuKDcaktqldVXWDTandhRCTBgrQ"
            "XriFPjgWrlWBoawOdHxkPggFDbqRkmALBBEEeDUnEHYedydlvNWSWuEwIiExkRPzJxnVz"
            "lNLgcQqWfKqmQBhJtKhNMPhmmyTBJaRqWriDMhIPNibsHalYyYbuNJUVUZRhLrhtbOTGA"
            "twLFwUEGCfxMvnpLNzLHwIXhtSiehQupukwYRQbJRBUMMXkODyCCWCeHvDwoIthoKRYPh"
            "CfPhViHrcRZvwKQJPtjKfCRHWKgneLGfwcENsMARiCUCxGZLs"
        )

        response = self.get(test_url, 400)

        assert "value" in str(response)


class QueryOrderBaseTestCase(PreCreatedHostsBaseTestCase):
    def _queries_subtests_with_added_hosts(self):
        host_id_list = [host.id for host in self.added_hosts]
        url_host_id_list = ",".join(host_id_list)
        urls = (HOST_URL, f"{HOST_URL}/{url_host_id_list}", f"{HOST_URL}/{url_host_id_list}/system_profile")
        for url in urls:
            with self.subTest(url=url):
                yield url

    def _get(self, base_url, order_by=None, order_how=None, status=200):
        kwargs = {}
        if order_by:
            kwargs["order_by"] = order_by
        if order_how:
            kwargs["order_how"] = order_how

        full_url = inject_qs(base_url, **kwargs)
        return self.get(full_url, status)


class QueryOrderWithAdditionalHostsBaseTestCase(QueryOrderBaseTestCase):
    def setUp(self):
        super().setUp()
        host_wrapper = HostWrapper()
        host_wrapper.account = ACCOUNT
        host_wrapper.display_name = "host1"  # Same as self.added_hosts[0]
        host_wrapper.insights_id = generate_uuid()
        host_wrapper.stale_timestamp = now().isoformat()
        host_wrapper.reporter = "test"
        response_data = self.post(HOST_URL, [host_wrapper.data()], 207)
        self.added_hosts.append(HostWrapper(response_data["data"][0]["host"]))

    def _assert_host_ids_in_response(self, response, expected_hosts):
        response_ids = [host["id"] for host in response["results"]]
        expected_ids = [host.id for host in expected_hosts]
        self.assertEqual(response_ids, expected_ids)


class QueryOrderTestCase(QueryOrderWithAdditionalHostsBaseTestCase):
    def _added_hosts_by_updated_desc(self):
        expected_hosts = self.added_hosts.copy()
        expected_hosts.reverse()
        return expected_hosts

    def _added_hosts_by_updated_asc(self):
        return self.added_hosts

    def _added_hosts_by_display_name_asc(self):
        return (
            # Hosts with same display_name are ordered by updated descending
            self.added_hosts[3],
            self.added_hosts[0],
            self.added_hosts[1],
            self.added_hosts[2],
        )

    def _added_hosts_by_display_name_desc(self):
        return (
            self.added_hosts[2],
            self.added_hosts[1],
            # Hosts with same display_name are ordered by updated descending
            self.added_hosts[3],
            self.added_hosts[0],
        )

    def tests_hosts_are_ordered_by_updated_desc_by_default(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url)
                expected_hosts = self._added_hosts_by_updated_desc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_ordered_by_updated_are_descending_by_default(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="updated")
                expected_hosts = self._added_hosts_by_updated_desc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_are_ordered_by_updated_descending(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="updated", order_how="DESC")
                expected_hosts = self._added_hosts_by_updated_desc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_are_ordered_by_updated_ascending(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="updated", order_how="ASC")
                expected_hosts = self._added_hosts_by_updated_asc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_ordered_by_display_name_are_ascending_by_default(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="display_name")
                expected_hosts = self._added_hosts_by_display_name_asc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_are_ordered_by_display_name_ascending(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="display_name", order_how="ASC")
                expected_hosts = self._added_hosts_by_display_name_asc()
                self._assert_host_ids_in_response(response, expected_hosts)

    def tests_hosts_are_ordered_by_display_name_descending(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                response = self._get(url, order_by="display_name", order_how="DESC")
                expected_hosts = self._added_hosts_by_display_name_desc()
                self._assert_host_ids_in_response(response, expected_hosts)


class QueryOrderWithSameModifiedOnTestsCase(QueryOrderWithAdditionalHostsBaseTestCase):
    UUID_1 = "00000000-0000-0000-0000-000000000001"
    UUID_2 = "00000000-0000-0000-0000-000000000002"
    UUID_3 = "00000000-0000-0000-0000-000000000003"

    def setUp(self):
        super().setUp()

    def _update_host(self, added_host_index, new_id, new_modified_on):
        old_id = self.added_hosts[added_host_index].id

        old_host = db.session.query(Host).get(old_id)
        old_host.id = new_id
        old_host.modified_on = new_modified_on
        db.session.add(old_host)

        staleness_offset = Timestamps.from_config(self.app.config["INVENTORY_CONFIG"])
        serialized_old_host = serialize_host(old_host, staleness_offset)
        self.added_hosts[added_host_index] = HostWrapper(serialized_old_host)

    def _update_hosts(self, id_updates):
        # New modified_on value must be set explicitly so it’s saved the same to all
        # records. Otherwise SQLAlchemy would consider it unchanged and update it
        # automatically to its own "now" only for records whose ID changed.
        new_modified_on = now()

        with self.app.app_context():
            for added_host_index, new_id in id_updates:
                self._update_host(added_host_index, new_id, new_modified_on)
            db.session.commit()

    def _added_hosts_by_indexes(self, indexes):
        return tuple(self.added_hosts[added_host_index] for added_host_index in indexes)

    def _test_order_by_id_desc(self, specifications, order_by, order_how):
        """
        Specification format is: Update these hosts (specification[*][0]) with these IDs
        (specification[*][1]). The updated hosts also get the same current timestamp.
        Then expect the query to return hosts in this order (specification[1]). Integers
        at specification[*][0] and specification[1][*] are self.added_hosts indices.
        """
        for updates, expected_added_hosts in specifications:
            # Update hosts to they have a same modified_on timestamp, but different IDs.
            self._update_hosts(updates)

            # Check the order in the response against the expected order. Only indexes
            # are passed, because self.added_hosts values were replaced during the
            # update.
            expected_hosts = self._added_hosts_by_indexes(expected_added_hosts)
            for url in self._queries_subtests_with_added_hosts():
                with self.subTest(url=url, updates=updates):
                    response = self._get(url, order_by=order_by, order_how=order_how)
                    self._assert_host_ids_in_response(response, expected_hosts)

    def test_hosts_ordered_by_updated_are_also_ordered_by_id_desc(self):
        # The first two hosts (0 and 1) with different display_names will have the same
        # modified_on timestamp, but different IDs.
        specifications = (
            (((0, self.UUID_1), (1, self.UUID_2)), (1, 0, 3, 2)),
            (((1, self.UUID_2), (0, self.UUID_3)), (0, 1, 3, 2)),
            # UPDATE order may influence actual result order.
            (((1, self.UUID_2), (0, self.UUID_1)), (1, 0, 3, 2)),
            (((0, self.UUID_3), (1, self.UUID_2)), (0, 1, 3, 2)),
        )
        self._test_order_by_id_desc(specifications, "updated", "DESC")

    def test_hosts_ordered_by_display_name_are_also_ordered_by_id_desc(self):
        # The two hosts with the same display_name (1 and 2) will have the same
        # modified_on timestamp, but different IDs.
        specifications = (
            (((0, self.UUID_1), (3, self.UUID_2)), (3, 0, 1, 2)),
            (((3, self.UUID_2), (0, self.UUID_3)), (0, 3, 1, 2)),
            # UPDATE order may influence actual result order.
            (((3, self.UUID_2), (0, self.UUID_1)), (3, 0, 1, 2)),
            (((0, self.UUID_3), (3, self.UUID_2)), (0, 3, 1, 2)),
        )
        self._test_order_by_id_desc(specifications, "display_name", "ASC")


class QueryOrderBadRequestsTestCase(QueryOrderBaseTestCase):
    def test_invalid_order_by(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                self._get(url, "fqdn", "ASC", 400)

    def test_invalid_order_how(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                self._get(url, "display_name", "asc", 400)

    def test_only_order_how(self):
        for url in self._queries_subtests_with_added_hosts():
            with self.subTest(url=url):
                self._get(url, None, "ASC", 400)


class QueryStaleTimestampTestCase(DBAPITestCase):
    def test_with_stale_timestamp(self):
        def _assert_values(response_host):
            self.assertIn("stale_timestamp", response_host)
            self.assertIn("stale_warning_timestamp", response_host)
            self.assertIn("culled_timestamp", response_host)
            self.assertIn("reporter", response_host)
            self.assertEqual(stale_timestamp_str, response_host["stale_timestamp"])
            self.assertEqual(stale_warning_timestamp_str, response_host["stale_warning_timestamp"])
            self.assertEqual(culled_timestamp_str, response_host["culled_timestamp"])
            self.assertEqual(reporter, response_host["reporter"])

        stale_timestamp = now()
        stale_timestamp_str = stale_timestamp.isoformat()
        stale_warning_timestamp = stale_timestamp + timedelta(weeks=1)
        stale_warning_timestamp_str = stale_warning_timestamp.isoformat()
        culled_timestamp = stale_timestamp + timedelta(weeks=2)
        culled_timestamp_str = culled_timestamp.isoformat()
        reporter = "some reporter"

        host_to_create = HostWrapper(
            {"account": ACCOUNT, "fqdn": "matching fqdn", "stale_timestamp": stale_timestamp_str, "reporter": reporter}
        )

        create_response = self.post(HOST_URL, [host_to_create.data()], 207)
        self._verify_host_status(create_response, 0, 201)
        created_host = self._pluck_host_from_response(create_response, 0)
        _assert_values(created_host)

        update_response = self.post(HOST_URL, [host_to_create.data()], 207)
        self._verify_host_status(update_response, 0, 200)
        updated_host = self._pluck_host_from_response(update_response, 0)
        _assert_values(updated_host)

        get_list_response = self.get(HOST_URL, 200)
        _assert_values(get_list_response["results"][0])

        created_host_id = created_host["id"]
        get_by_id_response = self.get(f"{HOST_URL}/{created_host_id}", 200)
        _assert_values(get_by_id_response["results"][0])


class QueryStalenessBaseTestCase(DBAPITestCase):
    def _create_host(self, stale_timestamp):
        data = {
            "account": ACCOUNT,
            "insights_id": str(generate_uuid()),
            "facts": [{"facts": {"fact1": "value1"}, "namespace": "ns1"}],
        }
        if stale_timestamp:
            data["reporter"] = "some reporter"
            data["stale_timestamp"] = stale_timestamp.isoformat()

        host = HostWrapper(data)
        response = self.post(HOST_URL, [host.data()], 207)
        self._verify_host_status(response, 0, 201)
        return self._pluck_host_from_response(response, 0)

    def _get_hosts_by_id_url(self, host_id_list, endpoint="", query=""):
        host_id_query = ",".join(host_id_list)
        return f"{HOST_URL}/{host_id_query}{endpoint}{query}"

    def _get_hosts_by_id(self, host_id_list, endpoint="", query=""):
        url = self._get_hosts_by_id_url(host_id_list, endpoint, query)
        response = self.get(url, 200)
        return response["results"]


class QueryStalenessGetHostsBaseTestCase(QueryStalenessBaseTestCase, CullingBaseTestCase):
    def setUp(self):
        super().setUp()
        current_timestamp = now()
        self.fresh_host = self._create_host(current_timestamp + timedelta(hours=1))
        self.stale_host = self._create_host(current_timestamp - timedelta(hours=1))
        self.stale_warning_host = self._create_host(current_timestamp - timedelta(weeks=1, hours=1))
        self.culled_host = self._create_host(current_timestamp - timedelta(weeks=2, hours=1))

        self.unknown_host = self._create_host(current_timestamp)
        self._nullify_culling_fields(self.unknown_host["id"])

    def _created_hosts(self):
        return (self.fresh_host["id"], self.stale_host["id"], self.stale_warning_host["id"], self.culled_host["id"])

    def _get_all_hosts_url(self, query):
        return f"{HOST_URL}{query}"

    def _get_all_hosts(self, query):
        url = self._get_all_hosts_url(query)
        response = self.get(url, 200)
        return tuple(host["id"] for host in response["results"])

    def _get_created_hosts_by_id_url(self, query):
        return self._get_hosts_by_id_url(self._created_hosts(), query=query)


class QueryStalenessGetHostsTestCase(QueryStalenessGetHostsBaseTestCase):
    def _get_endpoint_query_results(self, endpoint="", query=""):
        hosts = self._get_hosts_by_id(self._created_hosts(), endpoint, query)
        if endpoint == "/tags" or endpoint == "/tags/count":
            return tuple(hosts.keys())
        else:
            return tuple(host["id"] for host in hosts)

    def test_dont_get_only_culled(self):
        self.get(self._get_all_hosts_url(query="?staleness=culled"), 400)

    def test_get_only_fresh(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=fresh")
        self.assertEqual((self.fresh_host["id"],), retrieved_host_ids)

    def test_get_only_stale(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=stale")
        self.assertEqual((self.stale_host["id"],), retrieved_host_ids)

    def test_get_only_stale_warning(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=stale_warning")
        self.assertEqual((self.stale_warning_host["id"],), retrieved_host_ids)

    def test_get_only_unknown(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=unknown")
        self.assertEqual((self.unknown_host["id"],), retrieved_host_ids)

    def test_get_multiple_states(self):
        retrieved_host_ids = self._get_all_hosts("?staleness=fresh,stale")
        self.assertEqual((self.stale_host["id"], self.fresh_host["id"]), retrieved_host_ids)

    def test_get_hosts_list_default_ignores_culled(self):
        retrieved_host_ids = self._get_all_hosts("")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_get_hosts_by_id_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_tags_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/tags")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_tags_count_default_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/tags/count")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)

    def test_get_system_profile_ignores_culled(self):
        retrieved_host_ids = self._get_endpoint_query_results("/system_profile")
        self.assertNotIn(self.culled_host["id"], retrieved_host_ids)


class QueryStalenessGetHostsIgnoresCulledTestCase(QueryStalenessGetHostsBaseTestCase, DeleteHostsBaseTestCase):
    @patch("api.host.emit_patch_event")
    def test_patch_ignores_culled(self, emit_event):
        url = HOST_URL + "/" + self.culled_host["id"]

        self.patch(url, {"display_name": "patched"}, 404)

    @patch("api.host.emit_patch_event")
    def test_patch_works_on_non_culled(self, emit_patch_event):
        url = HOST_URL + "/" + self.fresh_host["id"]

        self.patch(url, {"display_name": "patched"}, 200)

    @patch("api.host.emit_patch_event")
    def test_patch_facts_ignores_culled(self, emit_patch_event):
        url = HOST_URL + "/" + self.culled_host["id"] + "/facts/ns1"

        self.patch(url, {"ARCHITECTURE": "patched"}, 400)

    @patch("api.host.emit_patch_event")
    def test_patch_facts_works_on_non_culled(self, emit_patch_event):  # broken
        url = HOST_URL + "/" + self.fresh_host["id"] + "/facts/ns1"

        self.patch(url, {"ARCHITECTURE": "patched"}, 200)

    @patch("api.host.emit_patch_event")
    def test_put_facts_ignores_culled(self, emit_patch_event):
        url = HOST_URL + "/" + self.culled_host["id"] + "/facts/ns1"

        self.put(url, {"ARCHITECTURE": "patched"}, 400)

    @patch("api.host.emit_patch_event")
    def test_put_facts_works_on_non_culled(self, emit_patch_event):  # broken
        url = HOST_URL + "/" + self.fresh_host["id"] + "/facts/ns1"
        print(url)
        self.put(url, {"ARCHITECTURE": "patched"}, 200)

    @patch("api.host.emit_patch_event")
    def test_delete_ignores_culled(self, emit_patch_event):
        url = HOST_URL + "/" + self.culled_host["id"]

        self.delete(url, 404)

    @patch("lib.host_delete.emit_event", new_callable=MockEmitEvent)
    def test_delete_works_on_non_culled(self, emit_patch_event):
        url = HOST_URL + "/" + self.fresh_host["id"]
        self.delete(url, 200, return_response_as_json=False)


class QueryStalenessGetHostsIgnoresStalenessParameterTestCase(QueryStalenessGetHostsTestCase):
    def _check_query_fails(self, endpoint="", query=""):
        url = self._get_hosts_by_id_url(self._created_hosts(), endpoint, query)
        self.get(url, 400)

    def test_get_host_by_id_doesnt_use_staleness_parameter(self):
        self._check_query_fails(query="?staleness=fresh")

    def test_tags_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/tags", "?staleness=fresh")

    def test_tags_count_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/tags/count", "?staleness=fresh")

    def test_sytem_profile_doesnt_use_staleness_parameter(self):
        self._check_query_fails("/system_profile", "?staleness=fresh")


class QueryStalenessConfigTimestampsTestCase(QueryStalenessBaseTestCase):
    def _create_and_get_host(self, stale_timestamp):
        host_to_create = self._create_host(stale_timestamp)
        retrieved_host = self._get_hosts_by_id((host_to_create["id"],))[0]
        self.assertEqual(stale_timestamp.isoformat(), retrieved_host["stale_timestamp"])
        return retrieved_host

    def test_stale_warning_timestamp(self):
        for culling_stale_warning_offset_days in (1, 7, 12):
            with self.subTest(culling_stale_warning_offset_days=culling_stale_warning_offset_days):
                config = self.app.config["INVENTORY_CONFIG"]
                config.culling_stale_warning_offset_days = culling_stale_warning_offset_days

                stale_timestamp = datetime.now(timezone.utc) + timedelta(hours=1)
                host = self._create_and_get_host(stale_timestamp)

                stale_warning_timestamp = stale_timestamp + timedelta(days=culling_stale_warning_offset_days)
                self.assertEqual(stale_warning_timestamp.isoformat(), host["stale_warning_timestamp"])

    def test_culled_timestamp(self):
        for culling_culled_offset_days in (8, 14, 20):
            with self.subTest(culling_culled_offset_days=culling_culled_offset_days):
                config = self.app.config["INVENTORY_CONFIG"]
                config.culling_culled_offset_days = culling_culled_offset_days

                stale_timestamp = datetime.now(timezone.utc) + timedelta(hours=1)
                host = self._create_and_get_host(stale_timestamp)

                culled_timestamp = stale_timestamp + timedelta(days=culling_culled_offset_days)
                self.assertEqual(culled_timestamp.isoformat(), host["culled_timestamp"])


class FactsTestCase(PreCreatedHostsBaseTestCase):
    def _valid_fact_doc(self):
        return {"newfact1": "newvalue1", "newfact2": "newvalue2"}

    def _build_facts_url(self, host_list, namespace):
        if type(host_list) == list:
            url_host_id_list = self._build_host_id_list_for_url(host_list)
        else:
            url_host_id_list = str(host_list)
        return HOST_URL + "/" + url_host_id_list + "/facts/" + namespace

    def _basic_fact_test(self, input_facts, expected_facts, replace_facts):

        host_list = self.added_hosts

        # This test assumes the set of facts are the same across
        # the hosts in the host_list

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        patch_url = self._build_facts_url(host_list, target_namespace)

        if replace_facts:
            response = self.put(patch_url, input_facts, 200)
        else:
            response = self.patch(patch_url, input_facts, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertEqual(host_to_verify.facts[0]["facts"], expected_facts)

            self.assertEqual(host_to_verify.facts[0]["namespace"], target_namespace)

    def test_add_facts_without_fact_dict(self):
        patch_url = self._build_facts_url(1, "ns1")
        response = self.patch(patch_url, None, 400)
        self.assertEqual(response["detail"], "Request body is not valid JSON")

    def test_add_facts_to_multiple_hosts(self):
        facts_to_add = self._valid_fact_doc()

        host_list = self.added_hosts

        # This test assumes the set of facts are the same across
        # the hosts in the host_list

        expected_facts = {**host_list[0].facts[0]["facts"], **facts_to_add}

        self._basic_fact_test(facts_to_add, expected_facts, False)

    def test_replace_and_add_facts_to_multiple_hosts_with_branch_id(self):
        facts_to_add = self._valid_fact_doc()

        host_list = self.added_hosts

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        patch_url = HOST_URL + "/" + url_host_id_list + "/facts/" + target_namespace + "?" + "branch_id=1234"

        # Add facts
        self.patch(patch_url, facts_to_add, 200)

        # Replace facts
        self.put(patch_url, facts_to_add, 200)

    def test_replace_and_add_facts_to_multiple_hosts_including_nonexistent_host(self):
        facts_to_add = self._valid_fact_doc()

        host_list = self.added_hosts

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        # Add a couple of host ids that should not exist in the database
        url_host_id_list = url_host_id_list + "," + generate_uuid() + "," + generate_uuid()

        patch_url = HOST_URL + "/" + url_host_id_list + "/facts/" + target_namespace

        # Add facts
        self.patch(patch_url, facts_to_add, 400)

        # Replace facts
        self.put(patch_url, facts_to_add, 400)

    def test_add_facts_to_multiple_hosts_overwrite_empty_key_value_pair(self):
        new_facts = {}
        expected_facts = new_facts

        # Set the value in the namespace to an empty fact set
        self._basic_fact_test(new_facts, expected_facts, True)

        new_facts = self._valid_fact_doc()
        expected_facts = new_facts

        # Overwrite the empty fact set
        self._basic_fact_test(new_facts, expected_facts, False)

    def test_add_facts_to_multiple_hosts_add_empty_fact_set(self):
        new_facts = {}
        target_namespace = self.added_hosts[0].facts[0]["namespace"]
        valid_host_id = self.added_hosts[0].id

        test_url = self._build_facts_url(valid_host_id, target_namespace)

        # Test merging empty facts set
        self.patch(test_url, new_facts, 400)

    def test_replace_and_add_facts_to_namespace_that_does_not_exist(self):
        valid_host_id = self.added_hosts[0].id
        facts_to_add = self._valid_fact_doc()
        test_url = self._build_facts_url(valid_host_id, "imanonexistentnamespace")

        # Test replace
        self.put(test_url, facts_to_add, 400)

        # Test add/merge
        self.patch(test_url, facts_to_add, 400)

    def test_replace_facts_without_fact_dict(self):
        put_url = self._build_facts_url(1, "ns1")
        response = self.put(put_url, None, 400)
        self.assertEqual(response["detail"], "Request body is not valid JSON")

    def test_replace_facts_on_multiple_hosts(self):
        new_facts = self._valid_fact_doc()
        expected_facts = new_facts

        self._basic_fact_test(new_facts, expected_facts, True)

    def test_replace_facts_on_multiple_hosts_with_empty_fact_set(self):
        new_facts = {}
        expected_facts = new_facts

        self._basic_fact_test(new_facts, expected_facts, True)

    def test_replace_empty_facts_on_multiple_hosts(self):
        new_facts = {}
        expected_facts = new_facts

        self._basic_fact_test(new_facts, expected_facts, True)

        new_facts = self._valid_fact_doc()
        expected_facts = new_facts

        self._basic_fact_test(new_facts, expected_facts, True)

    def test_invalid_host_id(self):
        bad_id_list = ["notauuid", "1234blahblahinvalid"]
        only_bad_id = bad_id_list.copy()

        # Can’t have empty string as an only ID, that results in 404 Not Found.
        more_bad_id_list = bad_id_list + [""]
        valid_id = self.added_hosts[0].id
        with_bad_id = [f"{valid_id},{bad_id}" for bad_id in more_bad_id_list]

        operations = (self.patch, self.put)
        fact_doc = self._valid_fact_doc()
        for operation in operations:
            for host_id_list in chain(only_bad_id, with_bad_id):
                url = self._build_facts_url(host_id_list, "ns1")
                with self.subTest(operation=operation, host_id_list=host_id_list):
                    operation(url, fact_doc, 400)


class FactsCullingTestCase(FactsTestCase, QueryStalenessGetHostsBaseTestCase):
    def test_replace_and_merge_ignore_culled_hosts(self):
        # Try to replace the facts on a host that has been marked as culled
        print(self.culled_host["facts"])
        target_namespace = self.culled_host["facts"][0]["namespace"]

        facts_to_add = self._valid_fact_doc()
        test_url = self._build_facts_url(self.culled_host["id"], target_namespace)
        # Test replace
        self.put(test_url, facts_to_add, 400)

        # Test add/merge
        self.patch(test_url, facts_to_add, 400)


class HeaderAuthTestCase(DBAPITestCase):
    @staticmethod
    def _valid_identity():
        """
        Provides a valid Identity object.
        """
        return Identity(account_number="some account number")

    @staticmethod
    def _valid_payload():
        """
        Builds a valid HTTP header payload – Base64 encoded JSON string with valid data.
        """
        identity = __class__._valid_identity()
        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)
        return b64encode(json.encode())

    def _get_hosts(self, headers):
        """
        Issues a GET request to the /hosts URL, providing given headers.
        """
        return self.client().get(HOST_URL, headers=headers)

    def test_validate_missing_identity(self):
        """
        Identity header is not present.
        """
        response = self._get_hosts({})
        self.assertEqual(401, response.status_code)

    def test_validate_invalid_identity(self):
        """
        Identity header is not valid – empty in this case
        """
        response = self._get_hosts({"x-rh-identity": ""})
        self.assertEqual(401, response.status_code)

    def test_validate_valid_identity(self):
        """
        Identity header is valid – non-empty in this case
        """
        payload = self._valid_payload()
        response = self._get_hosts({"x-rh-identity": payload})
        self.assertEqual(200, response.status_code)  # OK


class TokenAuthTestCase(DBAPITestCase):
    """
    A couple of sanity checks to make sure the service is denying access
    """

    def test_validate_invalid_token_on_GET(self):
        auth_header = build_auth_header("NotTheSuperSecretValue")
        response = self.client().get(HOST_URL, headers=auth_header)
        self.assertEqual(401, response.status_code)

    def test_validate_invalid_token_on_POST(self):
        auth_header = build_auth_header("NotTheSuperSecretValue")
        response = self.client().post(HOST_URL, headers=auth_header)
        self.assertEqual(401, response.status_code)

    def test_validate_token_on_POST_shared_secret_not_set(self):
        with set_environment({}):
            auth_header = build_valid_auth_header()
            response = self.client().post(HOST_URL, headers=auth_header)
            self.assertEqual(401, response.status_code)


class HealthTestCase(APIBaseTestCase):
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


class TagTestCase(TagsPreCreatedHostsBaseTestCase, PaginationBaseTestCase):
    """
    Tests the tag endpoints
    """

    tags_list = [
        [Tag("no", "key"), Tag("NS1", "key1", "val1"), Tag("NS1", "key2", "val1"), Tag("SPECIAL", "tag", "ToFind")],
        [Tag("NS1", "key1", "val1"), Tag("NS2", "key2", "val2"), Tag("NS3", "key3", "val3")],
        [Tag("NS1", "key3", "val3"), Tag("NS2", "key2", "val2"), Tag("NS3", "key3", "val3")],
        [],
    ]

    def _compare_responses(self, expected_response, response, test_url):
        self.assertEqual(len(expected_response), len(response["results"]))
        self.assertEqual(expected_response, response["results"])

        self._base_paging_test(test_url, len(expected_response))
        self._invalid_paging_parameters_test(test_url)

    def test_get_tags_of_multiple_hosts(self):
        """
        Send a request for the tag count of 1 host and check
        that it is the correct number
        """
        host_list = self.added_hosts

        expected_response = {}

        for host, tags in zip(host_list, self.tags_list):
            expected_response[str(host.id)] = [tag.data() for tag in tags]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        test_url = f"{HOST_URL}/{url_host_id_list}/tags?order_by=updated&order_how=ASC"
        response = self.get(test_url, 200)

        self._compare_responses(expected_response, response, test_url)

    def test_get_tag_count_of_multiple_hosts(self):
        host_list = self.added_hosts

        expected_response = {}

        for host, tags in zip(host_list, self.tags_list):
            expected_response[str(host.id)] = len(tags)

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        test_url = f"{HOST_URL}/{url_host_id_list}/tags/count?order_by=updated&order_how=ASC"
        response = self.get(test_url, 200)

        self._compare_responses(expected_response, response, test_url)

    def test_get_tags_of_hosts_that_doesnt_exist(self):
        """
        send a request for some hosts that don't exist
        """
        url_host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
        test_url = f"{HOST_URL}/{url_host_id}/tags"
        host_tag_results = self.get(test_url, 200)

        expected_response = {}

        self.assertEqual(expected_response, host_tag_results["results"])

    def _testing_apparatus_for_filtering(self, expected_filtered_results, given_results):
        self.assertEqual(len(expected_filtered_results), len(given_results))

        expectedValues = list(expected_filtered_results.values())
        givenValues = list(given_results.values())

        for i in range(len(givenValues)):
            self.assertEqual(expectedValues[i], givenValues[i])

    def test_get_filtered_by_search_tags_of_multiple_hosts(self):
        """
        send a request for tags to one host with some searchTerm
        """
        host_list = self.added_hosts

        """
        unfiltered_result = [
            {
                '5c322406-9ab2-467c-b968-1730e9b56cc3': [],
        'a2aea312-d6c0-4bae-a820-fc46f7abd123': [
                {'namespace': 'NS1', 'key': 'key3', 'value': 'val3'},
                {'namespace': 'NS2', 'key': 'key2', 'value': 'val2'},
                {'namespace': 'NS3', 'key': 'key3', 'value': 'val3'}
            ],
        '6582fdc7-4059-4a53-909b-f0691daff19b': [
                {'namespace': 'NS1', 'key': 'key1', 'value': 'val1'},
                {'namespace': 'NS2', 'key': 'key2', 'value': 'val2'},
                {'namespace': 'NS3', 'key': 'key3', 'value': 'val3'}
            ],
        '53327c6a-dcbd-45c8-b63a-a1f66bea10cf': [
                {'namespace': 'no', 'key': 'key', 'value': None},
                {'namespace': 'NS1', 'key': 'key1', 'value': 'val1'},
                {'namespace': 'NS1', 'key': 'key2', 'value': 'val1'},
                {'namespace': 'SPECIAL', 'key': 'tag', 'value': 'ToFind'}
                ]
            }
        ]
        """

        expected_filtered_results = [
            {
                "d3118a7a-f256-4cdd-a262-3c1d41507119": [],
                "d60da678-083a-4325-b79a-7b6c9c020ec6": [
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                "34798f51-421c-47b2-99c3-b1a646c8fa32": [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                "82c67d19-5fb0-4898-a6bb-56e2c64760c5": [
                    {"namespace": "no", "key": "key", "value": None},
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                    {"namespace": "SPECIAL", "key": "tag", "value": "ToFind"},
                ],
            },
            {
                "ef4b2967-ad89-4d70-9ea8-31d529644ef4": [],
                "3ebe7bbd-f24a-4177-bb15-f7e8d118eedf": [],
                "e2161dc9-a8d5-4df4-92e8-f55f993424a5": [],
                "a85f87f7-6067-4319-869f-15153b6a1432": [{"namespace": "SPECIAL", "key": "tag", "value": "ToFind"}],
            },
            {
                "ac065b69-8f78-4f2d-b0e3-4a6191774c87": [],
                "75264a41-7054-4a0e-84bf-5fcb68274977": [{"namespace": "NS1", "key": "key3", "value": "val3"}],
                "10f04142-c628-43ef-b52d-8e0bfb1a6dde": [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                "11f9a1e5-6cfa-4d5c-a275-035fbf1c0f83": [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                ],
            },
            {
                "1980a8b2-a9a9-4bf9-9e61-956307dad1ba": [],
                "87afe4e6-9321-4d1e-b5ad-25d6797c29ce": [],
                "83373e4f-36ae-48a0-b8f6-48a33db6e054": [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                "959d8732-500c-4a03-8384-29723cb5f4c3": [{"namespace": "NS1", "key": "key1", "value": "val1"}],
            },
            {
                "9c9a6c05-eb72-443e-9bca-90b32c32e865": [],
                "1c22b9a5-256f-4ca4-9079-3bb8d596e6e0": [],
                "a10c9158-cf64-443d-8df3-ef90492ec119": [{"namespace": "NS1", "key": "key1", "value": "val1"}],
                "368cbd5d-6843-4fcf-91bf-d73e5b5a81b6": [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                ],
            },
            {
                "a23a6609-3a77-4ba8-ae1c-1786e6f8f888": [],
                "fb1c5073-f323-4969-b019-d3ba306262b7": [
                    {"namespace": "NS1", "key": "key3", "value": "val3"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                "90e3235e-cc81-4c55-b28a-4720826b9d44": [
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS2", "key": "key2", "value": "val2"},
                    {"namespace": "NS3", "key": "key3", "value": "val3"},
                ],
                "5cdd679f-ae70-4699-a593-f01eafaa0202": [
                    {"namespace": "no", "key": "key", "value": None},
                    {"namespace": "NS1", "key": "key1", "value": "val1"},
                    {"namespace": "NS1", "key": "key2", "value": "val1"},
                ],
            },
            {
                "2bf91606-3430-4e12-8d50-0c11ab0f5aa4": [],
                "29761ca4-f483-4325-8a6e-6088ad7a50bb": [],
                "282dbf62-ea82-4a54-82c3-2e42a752d200": [],
                "721e9ee9-931f-4833-8f75-7f30f217dc96": [],
            },
        ]

        searchTerms = ["", "To", "NS1", "key1", "val1", "e", " "]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        for i in range(len(searchTerms)):
            test_url = f"{HOST_URL}/{url_host_id_list}/tags?search={searchTerms[i]}"
            response = self.get(test_url, 200)

            self._testing_apparatus_for_filtering(expected_filtered_results[i], response["results"])

    def test_get_tags_count_of_hosts_that_doesnt_exist(self):
        """
        send a request for some hosts that don't exist
        """
        url_host_id = "fa28ec9b-5555-4b96-9b72-96129e0c3336"
        test_url = f"{HOST_URL}/{url_host_id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        expected_response = {}

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_from_host_with_no_tags(self):
        """
        send a request for a host with no tags
        """
        host_with_no_tags = self.added_hosts[3]
        expected_response = {host_with_no_tags.id: []}

        test_url = f"{HOST_URL}/{host_with_no_tags.id}/tags"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_count_from_host_with_no_tags(self):
        """
        send a request for a host with no tags
        """
        host_with_no_tags = self.added_hosts[3]
        expected_response = {host_with_no_tags.id: 0}

        test_url = f"{HOST_URL}/{host_with_no_tags.id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def test_get_tags_count_from_host_with_tag_with_no_value(self):
        # host 0 has 4 tags, one of which has no value
        host_with_valueless_tag = self.added_hosts[0]
        expected_response = {host_with_valueless_tag.id: 4}

        test_url = f"{HOST_URL}/{host_with_valueless_tag.id}/tags/count"
        host_tag_results = self.get(test_url, 200)

        self.assertEqual(expected_response, host_tag_results["results"])

    def _per_page_test(self, per_page, total, range_end, test_url, expected_responses):
        for i in range(1, range_end):
            test_url = inject_qs(test_url, page=str(i), per_page=str(per_page))
            response = self.get(test_url, 200)
            with self.subTest(pagination_test_1_per_page=i):
                self.assertEqual(response["results"], expected_responses[i - 1])
                self.assertEqual(len(response["results"]), per_page)
                self.assertEqual(response["count"], per_page)
                self.assertEqual(response["total"], total)

    def test_tags_pagination(self):
        """
        simple test to check pagination works for /tags
        """
        host_list = self.added_hosts
        url_host_id_list = self._build_host_id_list_for_url(host_list)

        expected_responses_1_per_page = []

        for host, tags in zip(host_list, self.tags_list):
            expected_responses_1_per_page.append({str(host.id): [tag.data() for tag in tags]})

        test_url = f"{HOST_URL}/{url_host_id_list}/tags?order_by=updated&order_how=ASC"

        # 1 per page test
        self._per_page_test(1, len(host_list), len(host_list), test_url, expected_responses_1_per_page)

        expected_responses_2_per_page = [
            {
                str(host_list[0].id): [tag.data() for tag in self.tags_list[0]],
                str(host_list[1].id): [tag.data() for tag in self.tags_list[1]],
            },
            {
                str(host_list[2].id): [tag.data() for tag in self.tags_list[2]],
                str(host_list[3].id): [tag.data() for tag in self.tags_list[3]],
            },
        ]

        # 2 per page test
        self._per_page_test(2, len(host_list), int((len(host_list) + 1) / 2), test_url, expected_responses_2_per_page)

    def test_tags_count_pagination(self):
        """
        simple test to check pagination works for /tags
        """
        host_list = self.added_hosts
        url_host_id_list = self._build_host_id_list_for_url(host_list)

        expected_responses_1_per_page = []

        for host, tags in zip(host_list, self.tags_list):
            expected_responses_1_per_page.append({str(host.id): len(tags)})

        test_url = f"{HOST_URL}/{url_host_id_list}/tags/count?order_by=updated&order_how=ASC"

        # 1 per page test
        self._per_page_test(1, len(host_list), len(host_list), test_url, expected_responses_1_per_page)

        expected_responses_2_per_page = [
            {str(host_list[0].id): len(self.tags_list[0]), str(host_list[1].id): len(self.tags_list[1])},
            {str(host_list[2].id): len(self.tags_list[2]), str(host_list[3].id): len(self.tags_list[3])},
        ]

        # 2 per page test
        self._per_page_test(2, len(host_list), int((len(host_list) + 1) / 2), test_url, expected_responses_2_per_page)


class XjoinRequestBaseTestCase(APIBaseTestCase):
    @contextmanager
    def _patch_xjoin_post(self, response, status=200):
        with patch(
            "app.xjoin.post",
            **{
                "return_value.text": json.dumps(response),
                "return_value.json.return_value": response,
                "return_value.status_code": status,
            },
        ) as post:
            yield post

    def _get_with_request_id(self, url, request_id, status=200):
        return self.get(url, status, extra_headers={"x-rh-insights-request-id": request_id, "foo": "bar"})

    def _assert_called_with_headers(self, post, request_id):
        identity = self._get_valid_auth_header()["x-rh-identity"].decode()
        post.assert_called_once_with(
            ANY, json=ANY, headers={"x-rh-identity": identity, "x-rh-insights-request-id": request_id}
        )


class HostsXjoinBaseTestCase(APIBaseTestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "xjoin"}):
            super().setUp()


class HostsXjoinRequestBaseTestCase(XjoinRequestBaseTestCase, HostsXjoinBaseTestCase):
    EMPTY_RESPONSE = {"hosts": {"meta": {"total": 0}, "data": []}}
    patch_graphql_query_empty_response = partial(
        patch, "api.host_query_xjoin.graphql_query", return_value=EMPTY_RESPONSE
    )


class HostsXjoinRequestHeadersTestCase(HostsXjoinRequestBaseTestCase):
    def test_headers_forwarded(self):
        with self._patch_xjoin_post({"data": self.EMPTY_RESPONSE}) as post:
            request_id = generate_uuid()
            self._get_with_request_id(HOST_URL, request_id)
            self._assert_called_with_headers(post, request_id)


class XjoinSearchResponseCheckingTestCase(XjoinRequestBaseTestCase, HostsXjoinBaseTestCase):
    EMPTY_RESPONSE = {"hosts": {"meta": {"total": 0}, "data": []}}

    def base_xjoin_response_status_test(self, xjoin_res_status, expected_HBI_res_status):
        with self._patch_xjoin_post({"data": self.EMPTY_RESPONSE}, xjoin_res_status):
            request_id = generate_uuid()
            self._get_with_request_id(HOST_URL, request_id, expected_HBI_res_status)

    def test_host_request_xjoin_status_403(self):
        self.base_xjoin_response_status_test(403, 500)

    def test_host_request_xjoin_status_200(self):
        self.base_xjoin_response_status_test(200, 200)


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterSearchTestCase(HostsXjoinRequestBaseTestCase):
    STALENESS_ANY = ANY

    def test_query_variables_fqdn(self, graphql_query):
        fqdn = "host.domain.com"
        self.get(f"{HOST_URL}?fqdn={quote(fqdn)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"fqdn": fqdn}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_display_name(self, graphql_query):
        display_name = "my awesome host uwu"
        self.get(f"{HOST_URL}?display_name={quote(display_name)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"display_name": f"*{display_name}*"}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_hostname_or_id_non_uuid(self, graphql_query):
        hostname_or_id = "host.domain.com"
        self.get(f"{HOST_URL}?hostname_or_id={quote(hostname_or_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": (
                    {"OR": ({"display_name": f"*{hostname_or_id}*"}, {"fqdn": f"*{hostname_or_id}*"})},
                    self.STALENESS_ANY,
                ),
            },
        )

    def test_query_variables_hostname_or_id_uuid(self, graphql_query):
        hostname_or_id = generate_uuid()
        self.get(f"{HOST_URL}?hostname_or_id={quote(hostname_or_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": (
                    {
                        "OR": (
                            {"display_name": f"*{hostname_or_id}*"},
                            {"fqdn": f"*{hostname_or_id}*"},
                            {"id": hostname_or_id},
                        )
                    },
                    self.STALENESS_ANY,
                ),
            },
        )

    def test_query_variables_insights_id(self, graphql_query):
        insights_id = generate_uuid()
        self.get(f"{HOST_URL}?insights_id={quote(insights_id)}", 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "filter": ({"insights_id": insights_id}, self.STALENESS_ANY),
            },
        )

    def test_query_variables_none(self, graphql_query):
        self.get(HOST_URL, 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {"order_by": ANY, "order_how": ANY, "limit": ANY, "offset": ANY, "filter": (self.STALENESS_ANY,)},
        )

    def test_query_variables_priority(self, graphql_query):
        param = quote(generate_uuid())
        for filter_, query in (
            ("fqdn", f"fqdn={param}&display_name={param}"),
            ("fqdn", f"fqdn={param}&hostname_or_id={param}"),
            ("fqdn", f"fqdn={param}&insights_id={param}"),
            ("display_name", f"display_name={param}&hostname_or_id={param}"),
            ("display_name", f"display_name={param}&insights_id={param}"),
            ("OR", f"hostname_or_id={param}&insights_id={param}"),
        ):
            with self.subTest(filter=filter_, query=query):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?{query}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": ({filter_: ANY}, self.STALENESS_ANY),
                    },
                )


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterTagsTestCase(HostsXjoinRequestBaseTestCase):
    STALENESS_ANY = ANY

    def test_query_variables_tags(self, graphql_query):
        for tags, query_param in (
            (({"namespace": "a", "key": "b", "value": "c"},), "a/b=c"),
            (({"namespace": "a", "key": "b", "value": None},), "a/b"),
            (
                ({"namespace": "a", "key": "b", "value": "c"}, {"namespace": "d", "key": "e", "value": "f"}),
                "a/b=c,d/e=f",
            ),
            (
                ({"namespace": "a/a=a", "key": "b/b=b", "value": "c/c=c"},),
                quote("a/a=a") + "/" + quote("b/b=b") + "=" + quote("c/c=c"),
            ),
            (({"namespace": "ɑ", "key": "β", "value": "ɣ"},), "ɑ/β=ɣ"),
        ):
            with self.subTest(tags=tags, query_param=query_param):
                graphql_query.reset_mock()

                self.get(f"{HOST_URL}?tags={quote(query_param)}")

                tag_filters = tuple({"tag": item} for item in tags)
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": tag_filters + (self.STALENESS_ANY,),
                    },
                )

    def test_query_variables_tags_with_search(self, graphql_query):
        for field in ("fqdn", "display_name", "hostname_or_id", "insights_id"):
            with self.subTest(field=field):
                graphql_query.reset_mock()

                value = quote(generate_uuid())
                self.get(f"{HOST_URL}?{field}={value}&tags=a/b=c")

                search_any = ANY
                tag_filter = {"tag": {"namespace": "a", "key": "b", "value": "c"}}
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": (search_any, tag_filter, self.STALENESS_ANY),
                    },
                )


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestOrderingTestCase(HostsXjoinRequestBaseTestCase):
    def test_query_variables_ordering_dir(self, graphql_query):
        for direction in ("ASC", "DESC"):
            with self.subTest(direction=direction):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?order_by=updated&order_how={quote(direction)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY, {"limit": ANY, "offset": ANY, "order_by": ANY, "order_how": direction, "filter": ANY}
                )

    def test_query_variables_ordering_by(self, graphql_query):
        for params_order_by, xjoin_order_by, default_xjoin_order_how in (
            ("updated", "modified_on", "DESC"),
            ("display_name", "display_name", "ASC"),
        ):
            with self.subTest(ordering=params_order_by):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?order_by={quote(params_order_by)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "limit": ANY,
                        "offset": ANY,
                        "order_by": xjoin_order_by,
                        "order_how": default_xjoin_order_how,
                        "filter": ANY,
                    },
                )

    def test_query_variables_ordering_by_invalid(self, graphql_query):
        self.get(f"{HOST_URL}?order_by=fqdn", 400)
        graphql_query.assert_not_called()

    def test_query_variables_ordering_dir_invalid(self, graphql_query):
        self.get(f"{HOST_URL}?order_by=updated&order_how=REVERSE", 400)
        graphql_query.assert_not_called()

    def test_query_variables_ordering_dir_without_by(self, graphql_query):
        self.get(f"{HOST_URL}?order_how=ASC", 400)
        graphql_query.assert_not_called()


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestPaginationTestCase(HostsXjoinRequestBaseTestCase):
    def test_response_pagination(self, graphql_query):
        for page, limit, offset in ((1, 2, 0), (2, 2, 2), (4, 50, 150)):
            with self.subTest(page=page, limit=limit, offset=offset):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?per_page={quote(limit)}&page={quote(page)}", 200)
                graphql_query.assert_called_once_with(
                    HOST_QUERY, {"order_by": ANY, "order_how": ANY, "limit": limit, "offset": offset, "filter": ANY}
                )

    def test_response_invalid_pagination(self, graphql_query):
        for page, per_page in ((0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)):
            with self.subTest(page=page):
                self.get(f"{HOST_URL}?per_page={quote(per_page)}&page={quote(page)}", 400)
                graphql_query.assert_not_called()


@HostsXjoinRequestBaseTestCase.patch_graphql_query_empty_response()
class HostsXjoinRequestFilterStalenessTestCase(HostsXjoinRequestBaseTestCase):
    def _assert_graph_query_single_call_with_staleness(self, graphql_query, staleness_conditions):
        conditions = tuple({"stale_timestamp": staleness_condition} for staleness_condition in staleness_conditions)
        graphql_query.assert_called_once_with(
            HOST_QUERY,
            {"order_by": ANY, "order_how": ANY, "limit": ANY, "offset": ANY, "filter": ({"OR": conditions},)},
        )

    def test_query_variables_default_except_staleness(self, graphql_query):
        self.get(HOST_URL, 200)
        graphql_query.assert_called_once_with(
            HOST_QUERY, {"order_by": "modified_on", "order_how": "DESC", "limit": 50, "offset": 0, "filter": ANY}
        )

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_variables_default_staleness(self, datetime_mock, graphql_query):
        self.get(HOST_URL, 200)
        self._assert_graph_query_single_call_with_staleness(
            graphql_query,
            (
                {"gte": "2019-12-16T10:10:06.754201+00:00"},  # fresh
                {"gte": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"},  # stale
            ),
        )

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_variables_staleness(self, datetime_mock, graphql_query):
        for staleness, expected in (
            ("fresh", {"gte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale", {"gte": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale_warning", {"gte": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ):
            with self.subTest(staleness=staleness):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?staleness={staleness}", 200)
                self._assert_graph_query_single_call_with_staleness(graphql_query, (expected,))

    @patch(
        "app.culling.datetime", **{"now.return_value": datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)}
    )
    def test_query_multiple_staleness(self, datetime_mock, graphql_query):
        staleness = "fresh,stale_warning"
        graphql_query.reset_mock()
        self.get(f"{HOST_URL}?staleness={staleness}", 200)
        self._assert_graph_query_single_call_with_staleness(
            graphql_query,
            (
                {"gte": "2019-12-16T10:10:06.754201+00:00"},  # fresh
                {
                    "gte": "2019-12-02T10:10:06.754201+00:00",
                    "lte": "2019-12-09T10:10:06.754201+00:00",
                },  # stale warning
            ),
        )

    def test_query_variables_staleness_with_search(self, graphql_query):
        for field, value in (
            ("fqdn", generate_uuid()),
            ("display_name", "some display name"),
            ("hostname_or_id", "some hostname"),
            ("insights_id", generate_uuid()),
            ("tags", "some/tag"),
        ):
            with self.subTest(field=field):
                graphql_query.reset_mock()
                self.get(f"{HOST_URL}?{field}={quote(value)}")

                SEARCH_ANY = ANY
                STALENESS_ANY = ANY
                graphql_query.assert_called_once_with(
                    HOST_QUERY,
                    {
                        "order_by": ANY,
                        "order_how": ANY,
                        "limit": ANY,
                        "offset": ANY,
                        "filter": (SEARCH_ANY, STALENESS_ANY),
                    },
                )


class HostsXjoinResponseTestCase(HostsXjoinBaseTestCase):
    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_response_processed_properly(self, graphql_query):
        result = self.get(HOST_URL, 200)
        graphql_query.assert_called_once()

        self.assertEqual(
            result,
            {
                "total": 2,
                "count": 2,
                "page": 1,
                "per_page": 50,
                "results": [
                    {
                        "id": "6e7b6317-0a2d-4552-a2f2-b7da0aece49d",
                        "account": "test",
                        "display_name": "test01.rhel7.jharting.local",
                        "ansible_host": "test01.rhel7.jharting.local",
                        "created": "2019-02-10T08:07:03.354307+00:00",
                        "updated": "2019-02-10T08:07:03.354312+00:00",
                        "fqdn": "fqdn.test01.rhel7.jharting.local",
                        "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                        "insights_id": "a58c53e0-8000-4384-b902-c70b69faacc5",
                        "stale_timestamp": "2020-02-10T08:07:03.354307+00:00",
                        "reporter": "puptoo",
                        "rhel_machine_id": None,
                        "subscription_manager_id": None,
                        "bios_uuid": None,
                        "ip_addresses": None,
                        "mac_addresses": None,
                        "external_id": None,
                        "stale_warning_timestamp": "2020-02-17T08:07:03.354307+00:00",
                        "culled_timestamp": "2020-02-24T08:07:03.354307+00:00",
                        "facts": [],
                    },
                    {
                        "id": "22cd8e39-13bb-4d02-8316-84b850dc5136",
                        "account": "test",
                        "display_name": "test02.rhel7.jharting.local",
                        "ansible_host": "test02.rhel7.jharting.local",
                        "created": "2019-01-10T08:07:03.354307+00:00",
                        "updated": "2019-01-10T08:07:03.354312+00:00",
                        "fqdn": "fqdn.test02.rhel7.jharting.local",
                        "satellite_id": "ce87bfac-a6cb-43a0-80ce-95d9669db71f",
                        "insights_id": "17c52679-f0b9-4e9b-9bac-a3c7fae5070c",
                        "stale_timestamp": "2020-01-10T08:07:03.354307+00:00",
                        "reporter": "puptoo",
                        "rhel_machine_id": None,
                        "subscription_manager_id": None,
                        "bios_uuid": None,
                        "ip_addresses": None,
                        "mac_addresses": None,
                        "external_id": None,
                        "stale_warning_timestamp": "2020-01-17T08:07:03.354307+00:00",
                        "culled_timestamp": "2020-01-24T08:07:03.354307+00:00",
                        "facts": [
                            {"namespace": "os", "facts": {"os.release": "Red Hat Enterprise Linux Server"}},
                            {
                                "namespace": "bios",
                                "facts": {
                                    "bios.vendor": "SeaBIOS",
                                    "bios.release_date": "2014-04-01",
                                    "bios.version": "1.11.0-2.el7",
                                },
                            },
                        ],
                    },
                ],
            },
        )

    @patch_with_response()
    def test_response_pagination_index_error(self, graphql_query):
        self.get(f"{HOST_URL}?per_page=2&page=3", 404)
        graphql_query.assert_called_once()


class HostsXjoinTimestampsTestCase(HostsXjoinBaseTestCase):
    @staticmethod
    def _xjoin_host_response(timestamp):
        return {
            "hosts": {
                **MOCK_XJOIN_HOST_RESPONSE["hosts"],
                "meta": {"total": 1},
                "data": [
                    {
                        **MOCK_XJOIN_HOST_RESPONSE["hosts"]["data"][0],
                        "created_on": timestamp,
                        "modified_on": timestamp,
                        "stale_timestamp": timestamp,
                    }
                ],
            }
        }

    def test_valid_without_decimal_part(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03Z")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            get_host_list_response = self.get(HOST_URL, 200)
            retrieved_host = get_host_list_response["results"][0]
            self.assertEqual(retrieved_host["stale_timestamp"], "2020-02-10T08:07:03+00:00")

    def test_valid_with_offset_timezone(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03.354307+01:00")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            get_host_list_response = self.get(HOST_URL, 200)
            retrieved_host = get_host_list_response["results"][0]
            self.assertEqual(retrieved_host["stale_timestamp"], "2020-02-10T07:07:03.354307+00:00")

    def test_invalid_without_timezone(self):
        xjoin_host_response = self._xjoin_host_response("2020-02-10T08:07:03.354307")
        with patch("api.host_query_xjoin.graphql_query", return_value=xjoin_host_response):
            self.get(HOST_URL, 500)


@patch("api.tag.xjoin_enabled", return_value=True)
class TagsRequestTestCase(XjoinRequestBaseTestCase):
    patch_with_empty_response = partial(
        patch, "api.tag.graphql_query", return_value={"hostTags": {"meta": {"count": 0, "total": 0}, "data": []}}
    )

    def test_headers_forwarded(self, xjoin_enabled):
        value = {"data": {"hostTags": {"meta": {"count": 0, "total": 0}, "data": []}}}
        with self._patch_xjoin_post(value) as resp:
            req_id = "353b230b-5607-4454-90a1-589fbd61fde9"
            self._get_with_request_id(TAGS_URL, req_id)
            self._assert_called_with_headers(resp, req_id)

    @patch_with_empty_response()
    def test_query_variables_default_except_staleness(self, graphql_query, xjoin_enabled):
        self.get(TAGS_URL, 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": ANY}}
        )

    @patch_with_empty_response()
    @patch("app.culling.datetime")
    def test_query_variables_default_staleness(self, datetime_mock, graphql_query, xjoin_enabled):
        datetime_mock.now.return_value = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)

        self.get(TAGS_URL, 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": ANY,
                "order_how": ANY,
                "limit": ANY,
                "offset": ANY,
                "hostFilter": {
                    "OR": [
                        {"stale_timestamp": {"gte": "2019-12-16T10:10:06.754201+00:00"}},
                        {
                            "stale_timestamp": {
                                "gte": "2019-12-09T10:10:06.754201+00:00",
                                "lte": "2019-12-16T10:10:06.754201+00:00",
                            }
                        },
                    ]
                },
            },
        )

    @patch("app.culling.datetime")
    def test_query_variables_staleness(self, datetime_mock, xjoin_enabled):
        now = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
        datetime_mock.now = mock.Mock(return_value=now)

        for staleness, expected in (
            ("fresh", {"gte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale", {"gte": "2019-12-09T10:10:06.754201+00:00", "lte": "2019-12-16T10:10:06.754201+00:00"}),
            ("stale_warning", {"gte": "2019-12-02T10:10:06.754201+00:00", "lte": "2019-12-09T10:10:06.754201+00:00"}),
        ):
            with self.subTest(staleness=staleness):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?staleness={staleness}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": "ASC",
                            "limit": 50,
                            "offset": 0,
                            "hostFilter": {"OR": [{"stale_timestamp": expected}]},
                        },
                    )

    @patch("app.culling.datetime")
    def test_multiple_query_variables_staleness(self, datetime_mock, xjoin_enabled):
        now = datetime(2019, 12, 16, 10, 10, 6, 754201, tzinfo=timezone.utc)
        datetime_mock.now = mock.Mock(return_value=now)

        staleness = "fresh,stale_warning"
        with self.patch_with_empty_response() as graphql_query:
            self.get(f"{TAGS_URL}?staleness={staleness}", 200)

            graphql_query.assert_called_once_with(
                TAGS_QUERY,
                {
                    "order_by": "tag",
                    "order_how": "ASC",
                    "limit": 50,
                    "offset": 0,
                    "hostFilter": {
                        "OR": [
                            {"stale_timestamp": {"gte": "2019-12-16T10:10:06.754201+00:00"}},
                            {
                                "stale_timestamp": {
                                    "gte": "2019-12-02T10:10:06.754201+00:00",
                                    "lte": "2019-12-09T10:10:06.754201+00:00",
                                }
                            },
                        ]
                    },
                },
            )

    @patch_with_empty_response()
    def test_query_variables_tags_simple(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?tags=insights-client/os=fedora", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": [{"tag": {"namespace": "insights-client", "key": "os", "value": "fedora"}}],
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_tags_complex(self, graphql_query, xjoin_enabled):
        tag1 = Tag("Sat", "env", "prod")
        tag2 = Tag("insights-client", "special/keyΔwithčhars", "special/valueΔwithčhars!")

        self.get(f"{TAGS_URL}?tags={quote(tag1.to_string())}&tags={quote(tag2.to_string())}", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "hostFilter": {
                    "AND": [
                        {"tag": {"namespace": "Sat", "key": "env", "value": "prod"}},
                        {
                            "tag": {
                                "namespace": "insights-client",
                                "key": "special/keyΔwithčhars",
                                "value": "special/valueΔwithčhars!",
                            }
                        },
                    ],
                    "OR": ANY,
                },
            },
        )

    @patch_with_empty_response()
    def test_query_variables_search(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?search={quote('Δwithčhar!/~|+ ')}", 200)

        graphql_query.assert_called_once_with(
            TAGS_QUERY,
            {
                "order_by": "tag",
                "order_how": "ASC",
                "limit": 50,
                "offset": 0,
                "filter": {"name": ".*\\%CE\\%94with\\%C4\\%8Dhar\\%21\\%2F\\%7E\\%7C\\%2B\\+.*"},
                "hostFilter": {"OR": ANY},
            },
        )

    def test_query_variables_ordering_dir(self, xjoin_enabled):
        for direction in ["ASC", "DESC"]:
            with self.subTest(direction=direction):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?order_how={direction}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": direction,
                            "limit": 50,
                            "offset": 0,
                            "hostFilter": {"OR": ANY},
                        },
                    )

    def test_query_variables_ordering_by(self, xjoin_enabled):
        for ordering in ["tag", "count"]:
            with self.patch_with_empty_response() as graphql_query:
                self.get(f"{TAGS_URL}?order_by={ordering}", 200)

                graphql_query.assert_called_once_with(
                    TAGS_QUERY,
                    {"order_by": ordering, "order_how": "ASC", "limit": 50, "offset": 0, "hostFilter": {"OR": ANY}},
                )

    def test_response_pagination(self, xjoin_enabled):
        for page, limit, offset in [(1, 2, 0), (2, 2, 2), (4, 50, 150)]:
            with self.subTest(page=page):
                with self.patch_with_empty_response() as graphql_query:
                    self.get(f"{TAGS_URL}?per_page={limit}&page={page}", 200)

                    graphql_query.assert_called_once_with(
                        TAGS_QUERY,
                        {
                            "order_by": "tag",
                            "order_how": "ASC",
                            "limit": limit,
                            "offset": offset,
                            "hostFilter": {"OR": ANY},
                        },
                    )

    def test_response_invalid_pagination(self, xjoin_enabled):
        for page, per_page in [(0, 10), (-1, 10), (1, 0), (1, -5), (1, 101)]:
            with self.subTest(page=page):
                with self.patch_with_empty_response():
                    self.get(f"{TAGS_URL}?per_page={per_page}&page={page}", 400)


@patch("api.tag.xjoin_enabled", return_value=True)
class TagsResponseTestCase(APIBaseTestCase):
    RESPONSE = {
        "hostTags": {
            "meta": {"count": 3, "total": 3},
            "data": [
                {"tag": {"namespace": "Sat", "key": "env", "value": "prod"}, "count": 3},
                {"tag": {"namespace": "insights-client", "key": "database", "value": None}, "count": 2},
                {"tag": {"namespace": "insights-client", "key": "os", "value": "fedora"}, "count": 2},
            ],
        }
    }

    patch_with_tags = partial(patch, "api.tag.graphql_query", return_value=RESPONSE)

    @patch_with_tags()
    def test_response_processed_properly(self, graphql_query, xjoin_enabled):
        expected = self.RESPONSE["hostTags"]
        result = self.get(TAGS_URL, 200)
        graphql_query.assert_called_once()

        self.assertEqual(
            result,
            {
                "total": expected["meta"]["total"],
                "count": expected["meta"]["count"],
                "page": 1,
                "per_page": 50,
                "results": expected["data"],
            },
        )

    @patch_with_tags()
    def test_response_pagination_index_error(self, graphql_query, xjoin_enabled):
        self.get(f"{TAGS_URL}?per_page=2&page=3", 404)

        graphql_query.assert_called_once_with(
            TAGS_QUERY, {"order_by": "tag", "order_how": "ASC", "limit": 2, "offset": 4, "hostFilter": {"OR": ANY}}
        )


class xjoinBulkSourceSwitchTestCaseEnvXjoin(DBAPITestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "xjoin", "BULK_QUERY_SOURCE_BETA": "db"}):
            super().setUp()

    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_bulk_source_header_set_to_db(self, graphql_query):  # FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
        graphql_query.assert_not_called()

    @patch_with_response()
    def test_bulk_source_header_set_to_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use db FAILING
    def test_referer_header_set_to_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"})
        graphql_query.assert_not_called()

    @patch_with_response()  # should use xjoin
    def test_referer_not_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/something"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use xjoin
    def test_no_header_env_var_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200)
        graphql_query.assert_called_once()


class xjoinBulkSourceSwitchTestCaseEnvDB(DBAPITestCase):
    def setUp(self):
        with set_environment({"BULK_QUERY_SOURCE": "db", "BULK_QUERY_SOURCE_BETA": "xjoin"}):
            super().setUp()

    patch_with_response = partial(patch, "api.host_query_xjoin.graphql_query", return_value=MOCK_XJOIN_HOST_RESPONSE)

    @patch_with_response()
    def test_bulk_source_header_set_to_db(self, graphql_query):  # FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "db"})
        graphql_query.assert_not_called()

    @patch_with_response()
    def test_bulk_source_header_set_to_xjoin(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"x-rh-cloud-bulk-query-source": "xjoin"})
        graphql_query.assert_called_once()

    @patch_with_response()
    def test_referer_not_beta(self, graphql_query):  # should use db FAILING
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/something"})
        graphql_query.assert_not_called()

    @patch_with_response()  # should use xjoin
    def test_referer_header_set_to_beta(self, graphql_query):
        self.get(f"{HOST_URL}", 200, extra_headers={"referer": "http://www.cloud.redhat.com/beta/something"})
        graphql_query.assert_called_once()

    @patch_with_response()  # should use db FAILING
    def test_no_header_env_var_db(self, graphql_query):
        self.get(f"{HOST_URL}", 200)
        graphql_query.assert_not_called()


if __name__ == "__main__":
    main()
