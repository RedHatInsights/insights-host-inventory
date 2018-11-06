#!/usr/bin/env python

import unittest
import json
from app import create_app, db
from app.utils import HostWrapper

HOST_URL = "/api/hosts"

NS = "testns"
ID = "whoabuddy"

ACCOUNT = "000031"
FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]


def test_data(display_name="hi", tags=None, facts=None):
    return {
        "account": ACCOUNT,
        "display_name": display_name,
        #"insights-id": "1234-56-789",
        # "rhel-machine-id": "1234-56-789",
        #"ip-addresses": ["10.10.0.1", "10.0.0.2"],
        "ip-addresses": ["10.10.0.1"],
        #"mac-addresses": ["c2:00:d0:c8:61:01"],
        "tags": tags if tags else [],
        "facts": facts if facts else FACTS,
    }


class BaseAPITestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app(config_name="testing")
        self.client = self.app.test_client

        # binds the app to the current context
        with self.app.app_context():
            # create all tables
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            # drop all tables
            db.session.remove()
            db.drop_all()

    def get(self, path, status=200, return_response_as_json=True):
        return self._response_check(
            self.client().get(path), status, return_response_as_json
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
        return self._response_check(
            http_method(
                path, data=json_data, headers={'content-type': 'application/json'}
            ),
            status,
            return_response_as_json,
        )

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(response.status_code, status)
        if return_response_as_json:
            return json.loads(response.data)

        else:
            return response

    def _build_host_id_list_for_url(self, host_list):
        host_id_list = [str(h.id) for h in host_list]

        return ",".join(host_id_list)


class CreateHostsTestCase(BaseAPITestCase):

    def test_create_and_update(self):
        facts = None
        tags = ["/merge_me_1:value1"]

        host_data = HostWrapper(
            test_data(facts=facts, tags=tags)
        )

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)
        print("results:", results)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        post_data = host_data
        post_data.facts = FACTS

        # Replace facts under the first namespace
        post_data.facts[0]["facts"] = {"newkey1": "newvalue1"}

        # Add a new set of facts under a new namespace
        post_data.facts.append({"namespace": "ns2", "facts":
                               {"key2": "value2"}})

        # Add a new canonical fact
        post_data.rhel_machine_id = "1234-56-789"
        post_data.ip_addresses = ["10.10.0.1", "10.0.0.2"]
        post_data.mac_addresses = ["c2:00:d0:c8:61:01"]

        # Add a new tag
        post_data.tags = ["aws/new_tag_1:new_value_1"]

        expected_tags = tags
        expected_tags.extend(post_data.tags)

        # update initial entity
        results = self.post(HOST_URL, post_data.data(), 200)

        # make sure the id from the update post matches the id from the create
        self.assertEqual(results["id"], original_id)

        data = self.get("%s/%s" % (HOST_URL, original_id), 200)
        print("data:", data)
        results = HostWrapper(data["results"][0])

        # sanity check
        # post_data.facts[0]["facts"]["key2"] = "blah"
        self.assertListEqual(results.facts, post_data.facts)

        # make sure the canonical facts are merged
        self.assertEqual(results.rhel_machine_id, post_data.rhel_machine_id)
        self.assertListEqual(results.ip_addresses, post_data.ip_addresses)
        self.assertListEqual(results.mac_addresses, post_data.mac_addresses)

        # make sure the tags are merged
        self.assertListEqual(results.tags, expected_tags)

    def test_create_host_with_empty_tags_facts_display_name_then_update(self):
        # Create a host with empty tags, facts, and display_name
        # then update those fields
        host_data = HostWrapper(test_data(facts=None))
        del host_data.tags
        del host_data.display_name
        del host_data.facts

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        host_data.tags = ["aws/new_tag_1:new_value_1", "aws/k:v"]
        host_data.facts = FACTS
        host_data.display_name = "expected_display_name"

        self.post(HOST_URL, host_data.data(), 200)

        data = self.get("%s/%s" % (HOST_URL, original_id), 200)
        results = HostWrapper(data["results"][0])

        self.assertListEqual(results.tags, host_data.tags)

        self.assertListEqual(results.facts, host_data.facts)

        self.assertEqual(results.display_name, host_data.display_name)

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
        print("host_data.data():", host_data.data())

        # FIXME: Verify response?
        response_data = self.post(HOST_URL, host_data.data(), 400)

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account

        # FIXME: Verify response?
        response_data = self.post(HOST_URL, host_data.data(), 400)


class PreCreatedHostsBaseTestCase(BaseAPITestCase):

    def setUp(self):
        super(PreCreatedHostsBaseTestCase, self).setUp()
        self.added_hosts = self.create_hosts()

    def create_hosts(self):
        hosts_to_create = [("host1", "12345"),
                           ("host2", "54321")]
        host_list = []

        for host in hosts_to_create:
            host_wrapper = HostWrapper()
            host_wrapper.account = ACCOUNT
            host_wrapper.tags = TAGS
            host_wrapper.display_name = host[0]
            host_wrapper.insights_id = host[1]
            host_wrapper.facts = [{"namespace": "ns1",
                                   "facts": {"key1": "value1"}}]

            response_data = self.post(HOST_URL, host_wrapper.data(), 201)
            host_list.append(HostWrapper(response_data))

        return host_list


class QueryTestCase(PreCreatedHostsBaseTestCase):

    def test_query_all(self):
        response = self.get(HOST_URL, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), len(self.added_hosts))

    def test_query_using_host_id_list(self):
        host_list = self.added_hosts

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        response = self.get(HOST_URL + "/" + url_host_id_list, 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_single_tag(self):
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?tag=" + TAGS[0], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_multiple_tags(self):
        response = self.get(HOST_URL + "?tag=" + TAGS[0] + "&tag=" + TAGS[1], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_display_name(self):
        host_list = self.added_hosts

        response = self.get(HOST_URL + "?display_name=" + host_list[0].display_name)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 1)

    def test_query_using_display_name_substring(self):
        host_list = self.added_hosts

        host_name_substr = host_list[0].display_name[:-2]

        response = self.get(HOST_URL + "?display_name=" + host_name_substr)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)


class FactsTestCase(PreCreatedHostsBaseTestCase):

    def _build_facts_url(self, host_list, namespace):
        if type(host_list) == list:
            url_host_id_list = self._build_host_id_list_for_url(host_list)
        else:
            url_host_id_list = str(host_list)
        return HOST_URL + "/" + url_host_id_list + "/facts/" + namespace

    def test_add_facts_without_fact_dict(self):
        patch_url = self._build_facts_url(1, "ns1")
        response = self.patch(patch_url, None, 400)
        self.assertEqual(response['detail'], "Request body is not valid JSON")

    def test_add_facts_to_multiple_hosts(self):
        facts_to_add = {"newfact1": "newvalue1", "newfact2": "newvalue2"}

        host_list = self.added_hosts

        # This test assumes the set of facts are the same across
        # the hosts in the host_list

        expected_facts = {**host_list[0].facts[0]["facts"], **facts_to_add}

        target_namespace = host_list[0].facts[0]["namespace"]

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        patch_url = self._build_facts_url(host_list, target_namespace)

        response = self.patch(patch_url, facts_to_add, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertEqual(host_to_verify.facts[0]["facts"],
                             expected_facts)

            self.assertEqual(host_to_verify.facts[0]["namespace"],
                             target_namespace)

    @unittest.skip
    def test_add_facts_to_multiple_hosts_overwrite_empty_key_value_pair(self):
        pass

    @unittest.skip
    def test_add_facts_to_multiple_hosts_overwrite_existing_key_value_pair(self):
        pass

    @unittest.skip
    def test_add_facts_to_multiple_hosts_one_host_does_not_exist(self):
        pass

    @unittest.skip
    def test_add_facts_to_namespace_that_does_not_exist(self):
        pass

    def test_replace_facts_without_fact_dict(self):
        put_url = self._build_facts_url(1, "ns1")
        response = self.put(put_url, None, 400)
        self.assertEqual(response['detail'], "Request body is not valid JSON")

    @unittest.skip
    def test_replace_facts_on_multiple_hosts(self):
        pass

    @unittest.skip
    def test_replace_facts_on_multiple_hosts_one_host_does_not_exist(self):
        pass

    @unittest.skip
    def test_replace_facts_on_namespace_that_does_not_exist(self):
        pass


class TagsTestCase(PreCreatedHostsBaseTestCase):

    def _build_tag_op_doc(self, operation, tag):
        return {"operation": operation,
                "tag": tag}

    def test_add_tag_to_host(self):
        tag_to_add = "aws/unique:value"

        tag_op_doc = self._build_tag_op_doc("apply", tag_to_add)

        host_list = self.added_hosts

        expected_tags = host_list[0].tags
        expected_tags.append(tag_to_add)

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        self.post(f"{HOST_URL}/{url_host_id_list}/tags", tag_op_doc, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertListEqual(host_to_verify.tags, expected_tags)

    @unittest.skip
    def test_add_invalid_tag_to_host(self):
        pass

    @unittest.skip
    def test_add_duplicate_tags_to_host(self):
        pass

    def test_remove_tag_from_host(self):
        tag_to_remove = "aws/k:v"

        tag_op_doc = self._build_tag_op_doc("remove", tag_to_remove)

        host_list = self.added_hosts

        expected_tags = host_list[0].tags
        expected_tags.remove(tag_to_remove)

        url_host_id_list = self._build_host_id_list_for_url(host_list)

        self.post(f"{HOST_URL}/{url_host_id_list}/tags", tag_op_doc, 200)

        response = self.get(f"{HOST_URL}/{url_host_id_list}", 200)

        self.assertEqual(len(response["results"]), len(host_list))

        for response_host in response["results"]:
            host_to_verify = HostWrapper(response_host)

            self.assertListEqual(host_to_verify.tags, expected_tags)


if __name__ == "__main__":
    unittest.main()
