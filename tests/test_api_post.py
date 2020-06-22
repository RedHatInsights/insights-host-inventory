#!/usr/bin/env python
import copy
import json
from datetime import timedelta
from itertools import product
from unittest import main
from unittest.mock import call
from unittest.mock import patch

import dateutil.parser

from app.models import Host
from app.queue.ingress import handle_message
from app.utils import HostWrapper
from lib.host_repository import canonical_fact_host_query
from lib.host_repository import canonical_facts_host_query
from tests.test_api_utils import ACCOUNT
from tests.test_api_utils import build_valid_auth_header
from tests.test_api_utils import DBAPITestCase
from tests.test_api_utils import FACTS
from tests.test_api_utils import generate_uuid
from tests.test_api_utils import HOST_URL
from tests.test_api_utils import now
from tests.test_api_utils import PaginationBaseTestCase
from tests.test_api_utils import SHARED_SECRET
from tests.test_api_utils import test_data
from tests.test_utils import MockEventProducer
from tests.test_utils import set_environment
from tests.test_utils import valid_system_profile


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

    def test_ignore_culled_host_on_update_by_canonical_facts(self):
        # Culled host
        host_data = test_data(
            fqdn="my awesome fqdn", facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat()
        )

        # Create the host
        response = self.post(HOST_URL, [host_data], 207)

        self._verify_host_status(response, 0, 201)

        created_host = self._pluck_host_from_response(response, 0)

        # Update the host
        new_response = self.post(HOST_URL, [host_data], 207)

        self._verify_host_status(new_response, 0, 201)

        updated_host = self._pluck_host_from_response(new_response, 0)

        self.assertNotEqual(created_host["id"], updated_host["id"])

    def test_ignore_culled_host_on_update_by_elevated_id(self):
        # Culled host
        host_to_create_data = test_data(
            insights_id=generate_uuid(), facts=None, stale_timestamp=(now() - timedelta(weeks=3)).isoformat()
        )

        # Create the host
        response = self.post(HOST_URL, [host_to_create_data], 207)
        self._verify_host_status(response, 0, 201)
        created_host = self._pluck_host_from_response(response, 0)

        # Update the host
        host_to_update_data = {**host_to_create_data, "ip_addresses": ["10.10.0.2"]}
        new_response = self.post(HOST_URL, [host_to_update_data], 207)
        self._verify_host_status(new_response, 0, 201)
        updated_host = self._pluck_host_from_response(new_response, 0)
        self.assertNotEqual(created_host["id"], updated_host["id"])

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

    def test_create_host_ignores_tags(self):
        host_data = HostWrapper(test_data(tags=[{"namespace": "ns", "key": "some_key", "value": "val"}]))
        create_response = self.post(HOST_URL, [host_data.data()], 207)
        self._verify_host_status(create_response, 0, 201)
        host = self._pluck_host_from_response(create_response, 0)
        host_id = host["id"]
        tags_response = self.get(f"{HOST_URL}/{host_id}/tags")

        self.assertEqual(tags_response["results"][host_id], [])

    def test_update_host_with_tags_doesnt_change_tags(self):
        create_host_data = HostWrapper(
            test_data(tags=[{"namespace": "ns", "key": "some_key", "value": "val"}], fqdn="fqdn")
        )

        message = {"operation": "add_host", "data": create_host_data.data()}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)

        event = json.loads(mock_event_producer.event)
        host_id = event["host"]["id"]

        # attempt to update
        update_host_data = HostWrapper(
            test_data(tags=[{"namespace": "other_ns", "key": "other_key", "value": "other_val"}], fqdn="fqdn")
        )
        update_response = self.post(HOST_URL, [update_host_data.data()], 207)
        self._verify_host_status(update_response, 0, 200)

        tags_response = self.get(f"{HOST_URL}/{host_id}/tags")

        # check the tags haven't updated
        self.assertEqual(create_host_data.tags, tags_response["results"][host_id])

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

    def test_always_update_stale_timestamp_from_next_reporter(self):
        old_stale_timestamp = now() + timedelta(days=2)
        old_reporter = "old reporter"

        timestamps = (old_stale_timestamp + timedelta(days=1), old_stale_timestamp - timedelta(days=1))
        reporters = (old_reporter, "new reporter")
        for new_stale_timestamp, new_reporter in product(timestamps, reporters):
            with self.subTest(stale_timestamp=new_stale_timestamp, reporter=new_reporter):
                print("DISTEST", new_stale_timestamp, new_reporter)
                insights_id = generate_uuid()
                created_host = self._add_host(
                    201,
                    insights_id=insights_id,
                    stale_timestamp=old_stale_timestamp.isoformat(),
                    reporter=old_reporter,
                )
                old_retrieved_host = self._retrieve_host(created_host)

                self.assertEqual(old_stale_timestamp, old_retrieved_host.stale_timestamp)
                self.assertEqual(old_reporter, old_retrieved_host.reporter)

                self._add_host(
                    200,
                    insights_id=insights_id,
                    stale_timestamp=new_stale_timestamp.isoformat(),
                    reporter=new_reporter,
                )

                new_retrieved_host = self._retrieve_host(created_host)

                self.assertEqual(new_stale_timestamp, new_retrieved_host.stale_timestamp)
                self.assertEqual(new_reporter, new_retrieved_host.reporter)


if __name__ == "__main__":
    main()
