#!/usr/bin/env python

import unittest
import json
import dateutil.parser
import test.support
import uuid
import copy
from app import create_app, db
from app.auth.identity import Identity
from app.utils import HostWrapper
from base64 import b64encode
from json import dumps
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode, parse_qs, urlunsplit

HOST_URL = "/r/insights/platform/inventory/api/v1/hosts"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]
ACCOUNT = "000501"
SHARED_SECRET = "SuperSecretStuff"


def test_data(display_name="hi", tags=None, facts=None):
    return {
        "account": ACCOUNT,
        "display_name": display_name,
        # "insights_id": "1234-56-789",
        # "rhel_machine_id": "1234-56-789",
        # "ip_addresses": ["10.10.0.1", "10.0.0.2"],
        "ip_addresses": ["10.10.0.1"],
        # "mac_addresses": ["c2:00:d0:c8:61:01"],
        "tags": tags if tags else [],
        "facts": facts if facts else FACTS,
    }


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


class BaseAPITestCase(unittest.TestCase):
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

    def get(self, path, status=200, return_response_as_json=True):
        return self._response_check(
            self.client().get(path, headers=self._get_valid_auth_header()),
            status,
            return_response_as_json,
        )

    def post(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().post, path, data, status, return_response_as_json
        )

    def patch(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().patch, path, data, status, return_response_as_json
        )

    def put(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
            self.client().put, path, data, status, return_response_as_json
        )

    def _make_http_call(
        self, http_method, path, data, status, return_response_as_json=True
    ):
        json_data = json.dumps(data)
        headers = self._get_valid_auth_header()
        headers["content-type"] = "application/json"
        return self._response_check(
            http_method(path, data=json_data, headers=headers),
            status,
            return_response_as_json,
        )

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(response.status_code, status)
        if return_response_as_json:
            return json.loads(response.data)

        else:
            return response


class DBAPITestCase(BaseAPITestCase):

    @classmethod
    def setUpClass(cls):
        """
        Temporarily rename the host table while the tests run.  This is done
        to make dropping the table at the end of the tests a bit safer.
        """
        from app.models import Host
        temp_table_name_suffix = "__unit_tests__"
        if temp_table_name_suffix not in Host.__table__.name:
            Host.__table__.name = Host.__table__.name + temp_table_name_suffix
        if temp_table_name_suffix not in Host.__table__.fullname:
            Host.__table__.fullname = Host.__table__.fullname + temp_table_name_suffix

    def setUp(self):
        """
        Initializes the database by creating all tables.
        """
        super(DBAPITestCase, self).setUp()

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


class CreateHostsTestCase(DBAPITestCase):

    def _verify_host_status(self, response, host_index, expected_status):
        self.assertEqual(response["data"][host_index]["status"],
                         expected_status)

    def _pluck_host_from_response(self, response, host_index):
        return response["data"][host_index]["host"]

    def test_create_and_update(self):
        facts = None
        tags = []

        host_data = HostWrapper(test_data(facts=facts, tags=tags))

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        self._validate_host(created_host, host_data, expected_id=original_id)
        created_time = dateutil.parser.parse(created_host["created"])
        self.assertGreater(datetime.now(timezone.utc), created_time)

        host_data.facts = copy.deepcopy(FACTS)

        # Replace facts under the first namespace
        host_data.facts[0]["facts"] = {"newkey1": "newvalue1"}

        # Add a new set of facts under a new namespace
        host_data.facts.append({"namespace": "ns2", "facts": {"key2": "value2"}})

        # Add a new canonical fact
        host_data.rhel_machine_id = "1234-56-789"
        host_data.ip_addresses = ["10.10.0.1", "10.0.0.2"]
        host_data.mac_addresses = ["c2:00:d0:c8:61:01"]
        host_data.insights_id = "0987-65-4321"

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

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        # sanity check
        # host_lookup_results["results"][0]["facts"][0]["facts"]["key2"] = "blah"
        # host_lookup_results["results"][0]["insights_id"] = "1.2.3.4"
        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id)

    def test_create_host_update_with_same_insights_id_and_different_canonical_facts(self):
        original_insights_id = str(uuid.uuid4())

        host_data = HostWrapper(test_data(facts=None, tags=None))
        host_data.insights_id = original_insights_id
        host_data.rhel_machine_id = str(uuid.uuid4())
        host_data.subscription_manager_id = "123456"
        host_data.satellite_id = "123456"
        host_data.bios_uuid = "123456"
        host_data.fqdn = "original_fqdn"
        host_data.mac_addresses = ["aa:bb:cc:dd:ee:ff"]

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        self._validate_host(created_host, host_data, expected_id=original_id)

        # Change the canonical facts except for the insights_id
        host_data.rhel_machine_id = str(uuid.uuid4())
        host_data.ip_addresses = ["192.168.1.44", "10.0.0.2", ]
        host_data.subscription_manager_id = "654321"
        host_data.satellite_id = "654321"
        host_data.bios_uuid = "654321"
        host_data.fqdn = "expected_fqdn"
        host_data.mac_addresses = ["ff:ee:dd:cc:bb:aa"]
        host_data.facts = [{"namespace": "ns1",
                            "facts": {"newkey": "newvalue"}}]

        # Update the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 200)

        updated_host = self._pluck_host_from_response(response, 0)

        # Verify that the id did not change on the update
        self.assertEqual(updated_host["id"], original_id)

        # Retrieve the host using the id that we first received
        data = self.get("%s/%s" % (HOST_URL, original_id), 200)

        self._validate_host(data["results"][0],
                            host_data,
                            expected_id=original_id)

    def test_create_host_with_empty_tags_facts_display_name_then_update(self):
        # Create a host with empty tags, facts, and display_name
        # then update those fields
        host_data = HostWrapper(test_data(facts=None))
        del host_data.tags
        del host_data.display_name
        del host_data.facts

        # Tags are currently ignored on create and update
        expected_tags = []

        # Create the host
        response = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        self.assertIsNotNone(created_host["id"])

        original_id = created_host["id"]

        # Update the tags, facts and display name
        host_data.tags = ["aws/new_tag_1:new_value_1", "aws/k:v"]
        host_data.facts = copy.deepcopy(FACTS)
        host_data.display_name = "expected_display_name"

        # Update the hosts
        self.post(HOST_URL, [host_data.data()], 207)

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id,
                            verify_tags=False)

        # Tagging is not supported at the moment.  Verity the tag was ignored
        results = HostWrapper(host_lookup_results["results"][0])
        self.assertListEqual(results.tags, expected_tags)

    def test_create_and_update_multiple_hosts_with_account_mismatch(self):
        """
        Attempt to create multiple hosts, one host has the wrong account number.
        Verify this causes an error response to be returned.
        """
        tags = []
        facts = None

        host1 = HostWrapper(test_data(display_name="host1", facts=facts, tags=tags))
        host1.ip_addresses = ["10.0.0.1"]
        host1.rhel_machine_id = str(uuid.uuid4())

        host2 = HostWrapper(test_data(display_name="host2", facts=facts, tags=tags))
        # Set the account number to the wrong account for this request
        host2.account = "222222"
        host2.ip_addresses = ["10.0.0.2"]
        host2.rhel_machine_id = str(uuid.uuid4())

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

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        assert "Invalid request" in response_data["title"]
        assert "status" in response_data
        assert "detail" in response_data
        assert "type" in response_data

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account

        response_data = self.post(HOST_URL, [host_data.data()], 400)

        assert "Bad Request" in response_data["title"]
        assert "status" in response_data
        assert "detail" in response_data
        assert "type" in response_data

    def test_create_host_with_mismatched_account_numbers(self):
        host_data = HostWrapper(test_data(facts=None))
        host_data.account = ACCOUNT[::-1]

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        assert "Invalid request" in response_data["title"]
        assert "status" in response_data
        assert "detail" in response_data
        assert "type" in response_data

    def test_create_host_with_invalid_facts_no_namespace(self):
        facts = copy.deepcopy(FACTS)
        del facts[0]["namespace"]
        host_data = HostWrapper(test_data(facts=facts))

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        assert response_data["title"] == "Invalid request"
        assert "status" in response_data
        assert "detail" in response_data
        assert "type" in response_data

    def test_create_host_with_invalid_facts_no_facts(self):
        facts = copy.deepcopy(FACTS)
        del facts[0]["facts"]
        host_data = HostWrapper(test_data(facts=facts))

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        assert response_data["title"] == "Invalid request"
        assert "status" in response_data
        assert "detail" in response_data
        assert "type" in response_data

    def _validate_host(self, received_host, expected_host,
                       expected_id=id, verify_tags=True):
        self.assertIsNotNone(received_host["id"])
        self.assertEqual(received_host["id"], expected_id)
        self.assertEqual(received_host["account"], expected_host.account)
        self.assertEqual(received_host["insights_id"],
                         expected_host.insights_id)
        self.assertEqual(received_host["rhel_machine_id"],
                         expected_host.rhel_machine_id)
        self.assertEqual(received_host["subscription_manager_id"],
                         expected_host.subscription_manager_id)
        self.assertEqual(received_host["satellite_id"],
                         expected_host.satellite_id)
        self.assertEqual(received_host["bios_uuid"], expected_host.bios_uuid)
        self.assertEqual(received_host["fqdn"], expected_host.fqdn)
        self.assertEqual(received_host["mac_addresses"],
                         expected_host.mac_addresses)
        self.assertEqual(received_host["ip_addresses"],
                         expected_host.ip_addresses)
        self.assertEqual(received_host["display_name"],
                         expected_host.display_name)
        self.assertEqual(received_host["facts"], expected_host.facts)

        if verify_tags:
            self.assertEqual(received_host["tags"], expected_host.tags)
        else:
            self.assertIsNotNone(received_host["tags"])

        self.assertIsNotNone(received_host["created"])
        self.assertIsNotNone(received_host["updated"])


class ResolveDisplayNameOnCreationTestCase(CreateHostsTestCase):

    def _build_test_host_list(self):
        host_with_display_name_as_none = HostWrapper(test_data(facts=None))
        host_with_display_name_as_none.insights_id = str(uuid.uuid4())
        # Explicitly set the display name to None
        host_with_display_name_as_none.display_name = None

        host_without_display_name = HostWrapper(test_data(facts=None))
        host_without_display_name.insights_id = str(uuid.uuid4())
        # Remove the display name
        del host_without_display_name.display_name

        host_display_name_empty_str = HostWrapper(test_data(facts=None))
        host_display_name_empty_str.insights_id = str(uuid.uuid4())
        # Explicitly set the display name to an empty string
        host_display_name_empty_str.display_name = ""

        test_host_list = {"no display_name": host_without_display_name,
                          "display_name is None": host_with_display_name_as_none,
                          "display_name is empty string": host_display_name_empty_str}

        return test_host_list

    def test_create_host_without_display_name_and_no_fqdn(self):
        """
        This test should verify that the display_name is set to the id
        when neither the display name or fqdn is set.
        """
        test_host_list = self._build_test_host_list()

        host_fqdn_is_empty_str = HostWrapper(test_data(facts=None))
        host_fqdn_is_empty_str.insights_id = str(uuid.uuid4())
        host_fqdn_is_empty_str.display_name = ""
        host_fqdn_is_empty_str.fqdn = ""

        test_host_list["fqdn and display_name are empty strings"] = host_fqdn_is_empty_str

        for test_name, host_data in test_host_list.items():
            with self.subTest(test_name=test_name):

                # Create the host
                response = self.post(HOST_URL, [host_data.data()], 207)

                self._verify_host_status(response, 0, 201)

                created_host = self._pluck_host_from_response(response, 0)

                original_id = created_host["id"]

                host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

                # Explicitly set the display_name to the be id...this is expected here
                host_data.display_name = created_host["id"]

                self._validate_host(host_lookup_results["results"][0],
                                    host_data,
                                    expected_id=original_id,
                                    verify_tags=False)

    def test_create_host_without_display_name_and_with_fqdn(self):
        """
        This test should verify that the display_name is set to the
        fqdn when a display_name is not passed in but the fqdn is passed in.
        """
        expected_display_name = "fred.flintstone.bedrock.com"

        test_host_list = self._build_test_host_list()

        for test_name, host_data in test_host_list.items():

            host_data.fqdn = expected_display_name

            with self.subTest(test_name=test_name):

                # Create the host
                response = self.post(HOST_URL, [host_data.data()], 207)

                self._verify_host_status(response, 0, 201)

                created_host = self._pluck_host_from_response(response, 0)

                original_id = created_host["id"]

                host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

                # Explicitly set the display_name ...this is expected here
                host_data.display_name = expected_display_name

                self._validate_host(host_lookup_results["results"][0],
                                    host_data,
                                    expected_id=original_id,
                                    verify_tags=False)

class BulkCreateHostsTestCase(DBAPITestCase):

    def _get_valid_auth_header(self):
        return build_valid_auth_header()

    def test_create_and_update_multiple_hosts_with_different_accounts(self):
        with test.support.EnvironmentVarGuard() as env:
            env.set("INVENTORY_SHARED_SECRET", SHARED_SECRET)

            facts = None
            tags = []

            host1 = HostWrapper(test_data(display_name="host1", facts=facts, tags=tags))
            host1.account = "111111"
            host1.ip_addresses = ["10.0.0.1"]
            host1.rhel_machine_id = str(uuid.uuid4())

            host2 = HostWrapper(test_data(display_name="host2", facts=facts, tags=tags))
            host2.account = "222222"
            host2.ip_addresses = ["10.0.0.2"]
            host2.rhel_machine_id = str(uuid.uuid4())

            host_list = [host1.data(), host2.data()]

            # Create the host
            created_host = self.post(HOST_URL, host_list, 207)
            print("created_host:", created_host)

            self.assertEqual(len(host_list), len(created_host))

            self.assertEqual(created_host["errors"], 0)

            for host in created_host["data"]:
                self.assertEqual(host["status"], 201)

            host1_id = created_host["data"][0]["host"]["id"]
            host2_id = created_host["data"][1]["host"]["id"]

            host_list[0]["bios_uuid"] = str(uuid.uuid4())
            host_list[0]["display_name"] = "fred"

            host_list[1]["bios_uuid"] = str(uuid.uuid4())
            host_list[1]["display_name"] = "barney"

            # Update the host
            updated_host = self.post(HOST_URL, host_list, 207)
            print("updated_host:", updated_host)

            self.assertEqual(updated_host["errors"], 0)

            for host in updated_host["data"]:
                self.assertEqual(host["status"], 200)

            self.assertEqual(host1_id, updated_host["data"][0]["host"]["id"])
            self.assertEqual(host2_id, updated_host["data"][1]["host"]["id"])


class PreCreatedHostsBaseTestCase(DBAPITestCase):
    def setUp(self):
        super(PreCreatedHostsBaseTestCase, self).setUp()
        self.added_hosts = self.create_hosts()

    def create_hosts(self):
        hosts_to_create = [
            ("host1", "12345", "host1.domain.test"),
            ("host2", "54321", "host1.domain.test"),  # the same fqdn is intentional
            ("host3", "56789", "host2.domain.test"),
        ]
        host_list = []

        for host in hosts_to_create:
            host_wrapper = HostWrapper()
            host_wrapper.account = ACCOUNT
            host_wrapper.tags = copy.deepcopy(TAGS)
            host_wrapper.display_name = host[0]
            host_wrapper.insights_id = host[1]
            host_wrapper.fqdn = host[2]
            host_wrapper.facts = [{"namespace": "ns1", "facts": {"key1": "value1"}}]

            response_data = self.post(HOST_URL, [host_wrapper.data()], 207)
            host_list.append(HostWrapper(response_data["data"][0]["host"]))

        return host_list

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


class QueryTestCase(PreCreatedHostsBaseTestCase):
    def test_query_all(self):
        response = self.get(HOST_URL, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(self.added_hosts))

        self._base_paging_test(HOST_URL, len(self.added_hosts))

    def test_query_all_with_invalid_paging_parameters(self):
        invalid_limit_parameters = ["-1", "0", "notanumber"]
        for invalid_parameter in invalid_limit_parameters:
            self.get(HOST_URL + "?per_page=" + invalid_parameter, 400)

            self.get(HOST_URL + "?page=" + invalid_parameter, 400)

    def test_query_using_host_id_list(self):
        host_list = self.added_hosts

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        test_url = HOST_URL + "/" + url_host_id_list

        response = self.get(test_url, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(host_list))

        self._base_paging_test(test_url, len(self.added_hosts))

    def test_query_using_host_id_list_with_invalid_paging_parameters(self):
        host_list = self.added_hosts

        url_host_id_list = self._build_host_id_list_for_url(host_list)
        base_url = HOST_URL + "/" + url_host_id_list

        invalid_limit_parameters = ["-1", "0", "notanumber"]
        for invalid_parameter in invalid_limit_parameters:
            self.get(base_url + "?per_page=" + invalid_parameter, 400)

            self.get(base_url + "?page=" + invalid_parameter, 400)

    def test_query_using_host_id_list_include_nonexistent_host_ids(self):
        host_list = self.added_hosts

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        # Add some host ids to the list that do not exist
        url_host_id_list = (
            url_host_id_list + "," + str(uuid.uuid4()) + "," + str(uuid.uuid4())
        )

        response = self.get(HOST_URL + "/" + url_host_id_list, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(host_list))

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
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?fqdn=ROFLSAUCE.com")

        self.assertEqual(len(response["results"]), 0)

    def test_query_using_display_name_substring(self):
        host_list = self.added_hosts

        host_name_substr = host_list[0].display_name[:-2]

        test_url = HOST_URL + "?display_name=" + host_name_substr

        response = self.get(test_url)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(host_list))

        self._base_paging_test(test_url, len(self.added_hosts))


class QueryByHostnameOrIdTestCase(PreCreatedHostsBaseTestCase):

    def _base_query_test(self, query_value, expected_number_of_hosts):
        test_url = HOST_URL + "?hostname_or_id=" + query_value

        response = self.get(test_url)

        self.assertEqual(len(response["results"]), expected_number_of_hosts)

        self._base_paging_test(test_url, expected_number_of_hosts)

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
        self._base_query_test(str(uuid.uuid4()), 0)


class QueryByInsightsIdTestCase(PreCreatedHostsBaseTestCase):

    def _base_query_test(self, query_value, expected_number_of_hosts):
        test_url = HOST_URL + "?insights_id=" + query_value

        response = self.get(test_url)

        self.assertEqual(len(response["results"]), expected_number_of_hosts)

        self._base_paging_test(test_url, expected_number_of_hosts)

    def test_query_with_matching_insights_id(self):
        host_list = self.added_hosts

        self._base_query_test(host_list[0].insights_id, 1)

    def test_query_with_no_matching_insights_id(self):
        self._base_query_test("NotGonnaFindThisInsightsId", 0)


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

    def test_replace_and_add_facts_to_multiple_hosts_including_nonexistent_host(self):
        facts_to_add = self._valid_fact_doc()

        host_list = self.added_hosts

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        # Add a couple of host ids that should not exist in the database
        url_host_id_list = (
            url_host_id_list + "," + str(uuid.uuid4()) + "," + str(uuid.uuid4())
        )

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
        with test.support.EnvironmentVarGuard() as env:
            env.unset("INVENTORY_SHARED_SECRET")

            auth_header = build_valid_auth_header()
            response = self.client().post(HOST_URL, headers=auth_header)
            self.assertEqual(401, response.status_code)


class HealthTestCase(BaseAPITestCase):
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
        response = self.client().get(METRICS_URL)  # No identity header.
        self.assertEqual(200, response.status_code)

    def test_version(self):
        response = self.get(VERSION_URL, 200)
        assert response['version'] is not None

if __name__ == "__main__":
    unittest.main()
