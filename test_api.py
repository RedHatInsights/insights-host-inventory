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

HOST_URL = "/api/inventory/v1/hosts"
HEALTH_URL = "/health"
METRICS_URL = "/metrics"
VERSION_URL = "/version"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]
ACCOUNT = "000501"
SHARED_SECRET = "SuperSecretStuff"


def generate_uuid():
    return str(uuid.uuid4())


def test_data(display_name="hi", facts=None):
    return {
        "account": ACCOUNT,
        "display_name": display_name,
        # "insights_id": "1234-56-789",
        # "rhel_machine_id": "1234-56-789",
        # "ip_addresses": ["10.10.0.1", "10.0.0.2"],
        "ip_addresses": ["10.10.0.1"],
        # "mac_addresses": ["c2:00:d0:c8:61:01"],
        # "external_id": "i-05d2313e6b9a42b16"
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

    def verify_error_response(self, response, expected_title=None,
                              expected_status=None, expected_detail=None,
                              expected_type=None):

        def _verify_value(field_name, expected_value):
            assert field_name in response
            if expected_value is not None:
                self.assertEqual(response[field_name], expected_value)

        _verify_value("title", expected_title)
        _verify_value("status", expected_status)
        _verify_value("detail", expected_detail)
        _verify_value("type", expected_type)

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

    def _verify_host_status(self, response, host_index, expected_status):
        self.assertEqual(response["data"][host_index]["status"],
                         expected_status)

    def _pluck_host_from_response(self, response, host_index):
        return response["data"][host_index]["host"]

    def _validate_host(self, received_host, expected_host,
                       expected_id=id):
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
        self.assertGreater(datetime.now(timezone.utc), created_time)

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

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        # sanity check
        # host_lookup_results["results"][0]["facts"][0]["facts"]["key2"] = "blah"
        # host_lookup_results["results"][0]["insights_id"] = "1.2.3.4"
        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id)

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
        host_data.ip_addresses = ["192.168.1.44", "10.0.0.2", ]
        host_data.subscription_manager_id = generate_uuid()
        host_data.satellite_id = generate_uuid()
        host_data.bios_uuid = generate_uuid()
        host_data.fqdn = "expected_fqdn"
        host_data.mac_addresses = ["ff:ee:dd:cc:bb:aa"]
        host_data.external_id = "fedcba"
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

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id)

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

        self.verify_error_response(response_data,
                                   expected_title="Invalid request",
                                   expected_status=400)

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account

        response_data = self.post(HOST_URL, [host_data.data()], 400)

        self.verify_error_response(response_data, expected_title="Bad Request")

    def test_create_host_with_mismatched_account_numbers(self):
        host_data = HostWrapper(test_data(facts=None))
        host_data.account = ACCOUNT[::-1]

        response_data = self.post(HOST_URL, [host_data.data()], 207)

        self._verify_host_status(response_data, 0, 400)

        response_data = response_data["data"][0]

        self.verify_error_response(response_data,
                                   expected_title="Invalid request")

    def test_create_host_with_invalid_facts(self):
        facts_with_no_namespace = copy.deepcopy(FACTS)
        del facts_with_no_namespace[0]["namespace"]

        facts_with_no_facts = copy.deepcopy(FACTS)
        del facts_with_no_facts[0]["facts"]

        facts_with_empty_str_namespace = copy.deepcopy(FACTS)
        facts_with_empty_str_namespace[0]["namespace"] = ""

        invalid_facts = [facts_with_no_namespace,
                         facts_with_no_facts,
                         facts_with_empty_str_namespace,
                         ]

        for invalid_fact in invalid_facts:
            with self.subTest(invalid_fact=invalid_fact):
                host_data = HostWrapper(test_data(facts=invalid_fact))

                response_data = self.post(HOST_URL, [host_data.data()], 400)

                self.verify_error_response(response_data,
                                           expected_title="Bad Request")

    def test_create_host_with_invalid_uuid_field_values(self):
        uuid_field_names = (
                "insights_id",
                "rhel_machine_id",
                "subscription_manager_id",
                "satellite_id",
                "bios_uuid",
                )

        for field_name in uuid_field_names:
            with self.subTest(uuid_field=field_name):
                host_data = copy.deepcopy(test_data(facts=None))

                host_data[field_name] = "notauuid"

                response_data = self.post(HOST_URL, [host_data], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")

    def test_create_host_with_non_nullable_fields_as_None(self):
        non_nullable_field_names = ("display_name",
                                    "account",
                                    "insights_id",
                                    "rhel_machine_id",
                                    "subscription_manager_id",
                                    "satellite_id",
                                    "fqdn",
                                    "bios_uuid",
                                    "ip_addresses",
                                    "mac_addresses",
                                    "external_id",)

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

                self.verify_error_response(response_data,
                                           expected_title="Bad Request")

    def test_create_host_with_invalid_ip_address(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_ip_arrays = [["blah"],
                             ["1.1.1.1", "sigh"],
                             [],
                             ]

        for ip_array in invalid_ip_arrays:
            with self.subTest(ip_array=ip_array):
                host_data.ip_addresses = ip_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")

    def test_create_host_with_invalid_mac_address(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_mac_arrays = [["blah"],
                              ["11:22:33:44:55:66", "blah"],
                              [],
                              ]

        for mac_array in invalid_mac_arrays:
            with self.subTest(mac_array=mac_array):
                host_data.mac_addresses = mac_array

                response_data = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response_data["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")


    def test_create_host_with_invalid_display_name(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_display_names = ["", "a"*201]

        for display_name in invalid_display_names:
            with self.subTest(display_name=display_name):
                host_data.display_name = display_name

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")

    def test_create_host_with_invalid_fqdn(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_fqdns = ["", "a"*256]

        for fqdn in invalid_fqdns:
            with self.subTest(fqdn=fqdn):
                host_data.fqdn = fqdn

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")


    def test_create_host_with_invalid_external_id(self):
        host_data = HostWrapper(test_data(facts=None))

        invalid_external_ids = ["", "a"*501]

        for external_id in invalid_external_ids:
            with self.subTest(external_id=external_id):
                host_data.external_id = external_id

                response = self.post(HOST_URL, [host_data.data()], 207)

                error_host = response["data"][0]

                self.assertEqual(error_host["status"], 400)

                self.verify_error_response(error_host,
                                           expected_title="Bad Request")


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

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        # Explicitly set the display_name to the be id...this is expected here
        host_data.display_name = created_host["id"]

        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id)

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

        host_lookup_results = self.get("%s/%s" % (HOST_URL, original_id), 200)

        # Explicitly set the display_name ...this is expected here
        host_data.display_name = expected_display_name

        self._validate_host(host_lookup_results["results"][0],
                            host_data,
                            expected_id=original_id)

class BulkCreateHostsTestCase(DBAPITestCase):

    def _get_valid_auth_header(self):
        return build_valid_auth_header()

    def test_create_and_update_multiple_hosts_with_different_accounts(self):
        with test.support.EnvironmentVarGuard() as env:
            env.set("INVENTORY_SHARED_SECRET", SHARED_SECRET)

            facts = None

            host1 = HostWrapper(test_data(display_name="host1", facts=facts))
            host1.account = "111111"
            host1.ip_addresses = ["10.0.0.1"]
            host1.rhel_machine_id = str(uuid.uuid4())

            host2 = HostWrapper(test_data(display_name="host2", facts=facts))
            host2.account = "222222"
            host2.ip_addresses = ["10.0.0.2"]
            host2.rhel_machine_id = str(uuid.uuid4())

            host_list = [host1.data(), host2.data()]

            # Create the host
            response = self.post(HOST_URL, host_list, 207)

            self.assertEqual(len(host_list), len(response["data"]))
            self.assertEqual(response["total"], len(response["data"]))

            self.assertEqual(response["errors"], 0)

            for host in response["data"]:
                self.assertEqual(host["status"], 201)

            host_list[0]["id"] = response["data"][0]["host"]["id"]
            host_list[0]["bios_uuid"] = str(uuid.uuid4())
            host_list[0]["display_name"] = "fred"

            host_list[1]["id"] = response["data"][1]["host"]["id"]
            host_list[1]["bios_uuid"] = str(uuid.uuid4())
            host_list[1]["display_name"] = "barney"

            # Update the host
            updated_host = self.post(HOST_URL, host_list, 207)

            self.assertEqual(updated_host["errors"], 0)

            i = 0
            for host in updated_host["data"]:
                self.assertEqual(host["status"], 200)

                expected_host = HostWrapper(host_list[i])

                self._validate_host(host["host"],
                                    expected_host,
                                    expected_id=expected_host.id)

                i += 1


class CreateHostsWithSystemProfileTestCase(DBAPITestCase):

    def _valid_system_profile(self):
        return {"number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 4,
                "system_memory_bytes": 1024,
                "infrastructure_type": "massive cpu",
                "infrastructure_vendor": "dell",
                "network_interfaces": [{"ipv4_addresses": ["10.10.10.1"],
                                        "state": "UP",
                                        "ipv6_addresses": ["2001:0db8:85a3:0000:0000:8a2e:0370:7334",],
                                        "mtu": 1500,
                                        "mac_address": "aa:bb:cc:dd:ee:ff",
                                        "type": "loopback",
                                        "name": "eth0", }],
                "disk_devices": [{"device": "/dev/sdb1",
                                  "label": "home drive",
                                  "options": {"uid": "0",
                                              "ro": True},
                                  "mount_point": "/home",
                                  "type": "ext3"}],
                "bios_vendor": "AMI",
                "bios_version": "1.0.0uhoh",
                "bios_release_date": "10/31/2013",
                "cpu_flags": ["flag1", "flag2"],
                "os_release": "Red Hat EL 7.0.1",
                "os_kernel_version": "Linux 2.0.1",
                "arch": "x86-64",
                "last_boot_time": "12:25 Mar 19, 2019",
                "kernel_modules": ["i915", "e1000e"],
                "running_processes": ["vim", "gcc", "python"],
                "subscription_status": "valid",
                "subscription_auto_attach": "yes",
                "katello_agent_running": False,
                "satellite_managed": False,
                "yum_repos": [{"name": "repo1", "gpgcheck": True,
                               "enabled": True,
                               "base_url": "http://rpms.redhat.com"}],
                "installed_products": [{"name": "eap",
                                        "id": "123",
                                        "status": "UP"},
                                       {"name": "jbws",
                                        "id": "321",
                                        "status": "DOWN"}, ],
                "insights_client_version": "12.0.12",
                "insights_egg_version": "120.0.1",
                "installed_packages": ["rpm1", "rpm2"],
                "installed_services": ["ndb", "krb5"],
                "enabled_services": ["ndb", "krb5"],
                }

    def test_create_host_with_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = str(uuid.uuid4())

        host["system_profile"] = self._valid_system_profile()

        # Create the host
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        # verify system_profile is not included
        self.assertNotIn("system_profile", created_host)

        host_lookup_results = self.get("%s/%s/system_profile" % (HOST_URL, original_id), 200)
        actual_host = host_lookup_results["results"][0]

        self.assertEqual(original_id, actual_host["id"])

        self.assertEqual(actual_host["system_profile"], host["system_profile"])

    def test_create_host_without_system_profile_then_update_with_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = str(uuid.uuid4())

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        # List of tuples (system profile change, expected system profile)
        system_profiles = [({}, {})]

        # Only set the enabled_services to start out with
        enabled_services_only_system_profile = {"enabled_services":
                                                ["firewalld"]}
        system_profiles.append((enabled_services_only_system_profile,
                                enabled_services_only_system_profile))

        # Set the entire system profile...overwriting the enabled_service
        # set from before
        full_system_profile = self._valid_system_profile()
        system_profiles.append((full_system_profile, full_system_profile))

        # Change the enabled_services
        full_system_profile = {**full_system_profile,
                               **enabled_services_only_system_profile}
        system_profiles.append((enabled_services_only_system_profile,
                                full_system_profile))

        # Make sure an empty system profile doesn't overwrite the data
        system_profiles.append(({},
                                full_system_profile))

        for i, (system_profile, expected_system_profile) in enumerate(system_profiles):
            with self.subTest(system_profile=i):

                host["system_profile"] = system_profile

                # Create the host
                response = self.post(HOST_URL, [host], 207)

                self._verify_host_status(response, 0, 200)

                created_host = self._pluck_host_from_response(response, 0)

                original_id = created_host["id"]

                # verify system_profile is not included
                self.assertNotIn("system_profile", created_host)

                host_lookup_results = self.get("%s/%s/system_profile" % (HOST_URL, original_id), 200)
                actual_host = host_lookup_results["results"][0]

                self.assertEqual(original_id, actual_host["id"])

                self.assertEqual(actual_host["system_profile"],
                                 expected_system_profile)

    def test_create_host_with_null_system_profile(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = str(uuid.uuid4())
        host["system_profile"] = None

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 400)

        self.verify_error_response(response,
                                   expected_title="Bad Request",
                                   expected_status=400)

    def test_create_host_with_system_profile_with_invalid_data(self):
        facts = None

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = str(uuid.uuid4())

        # List of tuples (system profile change, expected system profile)
        system_profiles = [{"infrastructure_type": "i"*101,
                            "infrastructure_vendor": "i"*101, }]

        for system_profile in system_profiles:
            with self.subTest(system_profile=system_profile):

                host["system_profile"] = system_profile

                # Create the host
                response = self.post(HOST_URL, [host], 207)

                self._verify_host_status(response, 0, 400)

                self.assertEqual(response["errors"], 1)

    def test_get_system_profile_of_host_that_does_not_have_system_profile(self):
        facts = None
        expected_system_profile = {}

        host = test_data(display_name="host1", facts=facts)
        host["ip_addresses"] = ["10.0.0.1"]
        host["rhel_machine_id"] = str(uuid.uuid4())

        # Create the host without a system profile
        response = self.post(HOST_URL, [host], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        original_id = created_host["id"]

        host_lookup_results = self.get("%s/%s/system_profile" % (HOST_URL, original_id), 200)
        actual_host = host_lookup_results["results"][0]

        self.assertEqual(original_id, actual_host["id"])

        self.assertEqual(actual_host["system_profile"],
                         expected_system_profile)

    @unittest.skip("FIXME")
    def test_get_system_profile_of_multiple_hosts(self):
        # FIXME:
        # Test multiple hosts
        # Test pagination
        # Possibly just combine this with the above test
        pass

    def test_get_system_profile_of_host_that_does_not_exist(self):
        expected_count = 0
        expected_total = 0
        host_id = str(uuid.uuid4())
        results = self.get("%s/%s/system_profile" % (HOST_URL, host_id), 200)
        self.assertEqual(results["count"], expected_count)
        self.assertEqual(results["total"], expected_total)

    def test_get_system_profile_with_invalid_host_id(self):
        invalid_host_ids = ["notauuid", "%s,notuuid" % str(uuid.uuid4())]
        for host_id in invalid_host_ids:
            with self.subTest(invalid_host_id=host_id):
                response = self.get("%s/%s/system_profile" % (HOST_URL, host_id), 400)
                self.verify_error_response(response,
                                           expected_title="Bad Request",
                                           expected_status=400)


class PreCreatedHostsBaseTestCase(DBAPITestCase):
    def setUp(self):
        super(PreCreatedHostsBaseTestCase, self).setUp()
        self.added_hosts = self.create_hosts()

    def create_hosts(self):
        hosts_to_create = [
            ("host1", generate_uuid(), "host1.domain.test"),
            ("host2", generate_uuid(), "host1.domain.test"),  # the same fqdn is intentional
            ("host3", generate_uuid(), "host2.domain.test"),
        ]
        host_list = []

        for host in hosts_to_create:
            host_wrapper = HostWrapper()
            host_wrapper.account = ACCOUNT
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

    def test_query_using_host_id_list_one_host_id_does_not_include_hyphens(self):
        added_host_list = copy.deepcopy(self.added_hosts)
        expected_host_list = [h.data() for h in self.added_hosts]

        original_id = added_host_list[0].id

        # Remove the hyphens from one of the valid hosts
        added_host_list[0].id = uuid.UUID(original_id, version=4).hex

        url_host_id_list = self._build_host_id_list_for_url(added_host_list)

        test_url = HOST_URL + "/" + url_host_id_list

        response = self.get(test_url, 200)

        self.assertEqual(response["results"], expected_host_list)

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

    def test_query_using_host_id_list_include_badly_formatted_host_ids(self):
        host_list = self.added_hosts

        bad_id_list = ["1234blahblahinvalid", "", ]

        valid_url_host_id_list = self._build_host_id_list_for_url(host_list)

        for bad_id in bad_id_list:
            with self.subTest(bad_id=bad_id):
                # Construct the host id list for the url...
                # add in the "bad" id
                url_host_id_list = valid_url_host_id_list + "," + bad_id

                response = self.get(HOST_URL + "/" + url_host_id_list, 400)

                self.verify_error_response(response,
                                           expected_title="Bad Request",
                                           expected_status=400)

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
        uuid_that_does_not_exist_in_db = generate_uuid()
        self._base_query_test(uuid_that_does_not_exist_in_db, 0)


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
