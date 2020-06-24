#!/usr/bin/env python
import copy
import json
import uuid
from itertools import chain
from unittest import main
from unittest.mock import patch
from urllib.parse import quote_plus as url_quote

from .test_api_utils import ACCOUNT
from .test_api_utils import DBAPITestCase
from .test_api_utils import generate_uuid
from .test_api_utils import HOST_URL
from .test_api_utils import inject_qs
from .test_api_utils import now
from .test_api_utils import PaginationBaseTestCase
from .test_api_utils import PreCreatedHostsBaseTestCase
from .test_api_utils import quote_everything
from app import db
from app.culling import Timestamps
from app.models import Host
from app.queue.queue import handle_message
from app.serialization import serialize_host
from app.utils import HostWrapper
from lib.host_repository import canonical_fact_host_query
from tests.test_utils import MockEventProducer


class QueryTestCase(PreCreatedHostsBaseTestCase):
    def _expected_host_list(self):
        # Remove fields that are not returned by the REST endpoint
        return [
            {key: value for key, value in host.data().items() if key not in ("tags", "system_profile")}
            for host in self.added_hosts[::-1]
        ]

    def test_query_all(self):
        response = self.get(HOST_URL, 200)

        host_list = self.added_hosts.copy()
        host_list.reverse()

        expected_host_list = self._expected_host_list()

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

        expected_host_list = self._expected_host_list()

        self.assertEqual(response["results"], expected_host_list)

        self._base_paging_test(test_url, len(self.added_hosts))
        self._invalid_paging_parameters_test(test_url)


class QueryByHostIdTestCase(PreCreatedHostsBaseTestCase, PaginationBaseTestCase):
    def _expected_host_list(self, hosts):
        # Remove fields that are not returned by the REST endpoint
        return [
            {key: value for key, value in host.data().items() if key not in ("tags", "system_profile")}
            for host in hosts[::-1]
        ]

    def _base_query_test(self, host_id_list, expected_host_list):
        url = f"{HOST_URL}/{host_id_list}"
        response = self.get(url)

        self.assertEqual(response["count"], len(expected_host_list))
        self.assertEqual(len(response["results"]), len(expected_host_list))

        host_data = self._expected_host_list(expected_host_list)
        self.assertCountEqual(host_data, response["results"])

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
class QueryByCanonicalFactPerformanceTestCase(DBAPITestCase):
    def test_query_using_fqdn_not_subset_match(self, canonical_fact_host_query):
        fqdn = "some fqdn"
        self.get(f"{HOST_URL}?fqdn={fqdn}")
        canonical_fact_host_query.assert_called_once_with(ACCOUNT, "fqdn", fqdn)

    def test_query_using_insights_id_not_subset_match(self, canonical_fact_host_query):
        insights_id = "ff13a346-19cb-42ae-9631-44c42927fb92"
        self.get(f"{HOST_URL}?insights_id={insights_id}")
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

    def test_get_host_with_tag_no_value_at_all(self):
        """
        Attempt to find host with a tag with no stored value
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]  # host with tag "no/key"

        test_url = f"{HOST_URL}?tags=no/key"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_with_tag_no_value_in_query(self):
        """
        Attempt to find host with a tag with a stored value by a value-less query
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[0]]  # host with tag "no/key"

        test_url = f"{HOST_URL}?tags=NS1/key2"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_with_tag_no_namespace(self):
        """
        Attempt to find host with a tag with no namespace.
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[2]]  # host with tag "key4=val4"
        test_url = f"{HOST_URL}?tags=key4=val4"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

    def test_get_host_with_tag_only_key(self):
        """
        Attempt to find host with a tag with no namespace.
        """
        host_list = self.added_hosts.copy()

        expected_response_list = [host_list[2]]  # host with tag "key5"
        test_url = f"{HOST_URL}?tags=key5"
        response_list = self.get(test_url, 200)

        self._compare_responses(expected_response_list, response_list, test_url)

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

    def test_get_host_tag_part_too_long(self):
        """
        send a request to find hosts with a string tag where the length
        of the namespace excedes the 255 character limit
        """
        too_long = "a" * 256

        for tags_query, part_name in (
            (f"{too_long}/key=val", "namespace"),
            (f"namespace/{too_long}=val", "key"),
            (f"namespace/key={too_long}", "value"),
        ):
            with self.subTest(part=part_name):
                response = self.get(f"{HOST_URL}?tags={tags_query}", 400)
                assert part_name in str(response)

    def test_get_host_with_unescaped_special_characters(self):
        host_wrapper = HostWrapper(
            {
                "account": ACCOUNT,
                "insights_id": generate_uuid(),
                "stale_timestamp": now().isoformat(),
                "reporter": "test",
                "tags": [
                    {"namespace": ";?:@&+$", "key": "-_.!~*'()'", "value": "#"},
                    {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
                ],
            }
        )
        message = {"operation": "add_host", "data": host_wrapper.data()}

        with self.app.app_context():
            mock_event_producer = MockEventProducer()
            handle_message(json.dumps(message), mock_event_producer)
            response_data = json.loads(mock_event_producer.event)
            created_host = response_data["host"]

        for tags_query in (";?:@&+$/-_.!~*'()'=#", " \t\n\r\f\v/ \t\n\r\f\v= \t\n\r\f\v"):
            with self.subTest(tags_query=tags_query):
                get_response = self.get(f"{HOST_URL}?tags={url_quote(tags_query)}", 200)

                self.assertEqual(get_response["count"], 1)
                self.assertEqual(get_response["results"][0]["id"], created_host["id"])

    def test_get_host_with_escaped_special_characters(self):
        host_wrapper = HostWrapper(
            {
                "account": ACCOUNT,
                "insights_id": generate_uuid(),
                "stale_timestamp": now().isoformat(),
                "reporter": "test",
                "tags": [
                    {"namespace": ";,/?:@&=+$", "key": "-_.!~*'()", "value": "#"},
                    {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
                ],
            }
        )
        message = {"operation": "add_host", "data": host_wrapper.data()}

        with self.app.app_context():
            mock_event_producer = MockEventProducer()
            handle_message(json.dumps(message), mock_event_producer)
            response_data = json.loads(mock_event_producer.event)
            created_host = response_data["host"]

        for namespace, key, value in ((";,/?:@&=+$", "-_.!~*'()", "#"), (" \t\n\r\f\v", " \t\n\r\f\v", " \t\n\r\f\v")):
            with self.subTest(namespace=namespace, key=key, value=value):
                tags_query = url_quote(
                    f"{quote_everything(namespace)}/{quote_everything(key)}={quote_everything(value)}"
                )
                get_response = self.get(f"{HOST_URL}?tags={tags_query}", 200)

                self.assertEqual(get_response["count"], 1)
                self.assertEqual(get_response["results"][0]["id"], created_host["id"])


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


class InsightsFilterTestCase(PreCreatedHostsBaseTestCase):
    # remove the insights ID from some hosts in setUp
    def setUp(self):
        super().setUp()
        # add a host with no insights id
        host_wrapper = HostWrapper()
        host_wrapper.account = ACCOUNT
        host_wrapper.id = generate_uuid()
        host_wrapper.satellite_id = generate_uuid()
        host_wrapper.stale_timestamp = now().isoformat()
        host_wrapper.reporter = "test"
        self.post(HOST_URL, [host_wrapper.data()], 207)

    # get host list, check only ones with insight-id is returned
    def test_get_hosts_only_insights(self):
        result = self.get(HOST_URL + "?registered_with=insights")
        result_ids = [host["id"] for host in result["results"]]
        self.assertEqual(len(result_ids), 3)
        expected_ids = [self.added_hosts[2].id, self.added_hosts[1].id, self.added_hosts[0].id]
        self.assertEqual(result_ids, expected_ids)


if __name__ == "__main__":
    main()
