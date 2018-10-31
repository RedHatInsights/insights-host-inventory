#!/usr/bin/env python

import unittest
import json
from app import create_app, db
from app.utils import HostWrapper

HOST_URL = "/api/hosts"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]
TAGS = ["aws/new_tag_1:new_value_1", "aws/k:v"]


def test_data(display_name="hi", canonical_facts=None, tags=None, facts=None):
    return {
        "account": "test",
        "display_name": display_name,
        "canonical_facts": canonical_facts if canonical_facts else {NS: ID},
        "tags": tags if tags else [],
        "facts": facts if facts else FACTS
    }


class HostsTestCase(unittest.TestCase):

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
        return self._response_check(self.client().get(path),
                                    status,
                                    return_response_as_json)

    def post(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
                               self.client().post,
                               path,
                               data,
                               status,
                               return_response_as_json)

    def patch(self, path, data, status=200, return_response_as_json=True):
        return self._make_http_call(
                               self.client().patch,
                               path,
                               data,
                               status,
                               return_response_as_json)

    def _make_http_call(self, http_method, path, data, status, return_response_as_json=True):
        json_data = json.dumps(data)
        return self._response_check(http_method(path,
                                                data=json_data,
                                                headers={'content-type':'application/json'}),
                                    status,
                                    return_response_as_json)

    def _response_check(self, response, status, return_response_as_json):
        self.assertEqual(response.status_code, status)
        if return_response_as_json:
            return json.loads(response.data)
        else:
            return response

    def test_create_and_update(self):
        canonical_facts = {"test_id": "11-22-33", "another_test_id": "44-55-66"}
        facts = None
        tags = ["/merge_me_1:value1"]

        host_data = HostWrapper(test_data(canonical_facts=canonical_facts,
                                          facts=facts,
                                          tags=tags))
        print(host_data)

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        post_data = host_data
        post_data.facts.clear()
        post_data.facts = [{"namespace": "ns2", "facts": {"key2": "value2"}}]
        post_data.canonical_facts["test2"] = "test2id"
        post_data.tags = ["aws/new_tag_1:new_value_1"]

        expected_tags = tags
        expected_tags.extend(post_data.tags)

        print("post_data:", post_data)

        # update initial entity
        results = self.post(HOST_URL, post_data.data(), 200)

        self.assertEqual(results["id"], original_id)

        data = self.get("%s/%d" % (HOST_URL, original_id), 200)
        results = HostWrapper(data["results"][0])

        self.assertEqual(len(results.facts), 2)
        # sanity check
        # post_data["facts"][0]["facts"]["key2"] = "blah"
        self.assertEqual(results.facts[1]["facts"], post_data.facts[0]["facts"])

        # make sure the canonical facts are merged
        self.assertEqual(len(results.canonical_facts), 3)
        self.assertEqual(results.canonical_facts["test2"], "test2id")

        # make sure the tags are merged
        self.assertEqual(len(results.tags), 2)
        self.assertListEqual(results.tags, expected_tags)

    def test_post_same_facts(self):
        pass

    def test_create_host_with_empty_tags_facts_display_name_then_update(self):
        # Create a host with empty tags, facts, and display_name
        # then update those fields

        host_data = HostWrapper(test_data(facts=None))
        del host_data.tags
        del host_data.display_name
        del host_data.facts
        print("DATA:", host_data.data())

        # initial create
        results = self.post(HOST_URL, host_data.data(), 201)

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        host_data.tags = ["aws/new_tag_1:new_value_1", "aws/k:v"]
        host_data.facts = FACTS
        host_data.display_name = "expected_display_name"

        self.post(HOST_URL, host_data.data(), 200)

        data = self.get("%s/%d" % (HOST_URL, original_id), 200)
        print(data["results"][0])
        results = HostWrapper(data["results"][0])

        self.assertListEqual(results.tags, host_data.tags)

        self.assertListEqual(results.facts, host_data.facts)

        self.assertEqual(results.display_name, host_data.display_name)

    def test_create_host_without_canonical_facts(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.canonical_facts
        print("DATA:", host_data.data())

        response_data = self.post(HOST_URL, host_data.data(), 400)

        # FIXME: Verify response?

    def test_create_host_without_account(self):
        host_data = HostWrapper(test_data(facts=None))
        del host_data.account
        print("DATA:", host_data.data())

        response_data = self.post(HOST_URL, host_data.data(), 400)

        # FIXME: Verify response?

    def add_2_hosts(self):
        # FIXME: make this more generic
        host_list = []

        canonical_facts = {'insights_id': '12345'}
        display_name = "host1"
        tags = TAGS
        host_data = HostWrapper(test_data(display_name=display_name,
                                          canonical_facts=canonical_facts,
                                          tags=tags))
        response_data = self.post(HOST_URL, host_data.data(), 201)
        host_list.append(HostWrapper(response_data))

        canonical_facts = {'insights_id': '54321'}
        display_name = "host2"
        tags = TAGS
        host_data = HostWrapper(test_data(display_name=display_name,
                                          canonical_facts=canonical_facts,
                                          tags=tags))
        response_data = self.post(HOST_URL, host_data.data(), 201)
        host_list.append(HostWrapper(response_data))

        return host_list

    def test_query_all(self):

        host_list = self.add_2_hosts()

        response = self.get(HOST_URL, 200)
        print("response:", response)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_host_id_list(self):

        host_list = self.add_2_hosts()
        host_id_list = [str(h.id) for h in host_list]

        response = self.get(HOST_URL + "/" + ",".join(host_id_list), 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_single_tag(self):
        host_list = self.add_2_hosts()

        response = self.get(HOST_URL + "?tag=" + TAGS[0], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_multiple_tags(self):
        host_list = self.add_2_hosts()

        response = self.get(HOST_URL + "?tag=" + TAGS[0] +
                            "&tag=" + TAGS[1], 200)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    def test_query_using_display_name(self):
        host_list = self.add_2_hosts()

        response = self.get(HOST_URL +
                            "?display_name=" +
                            host_list[0].display_name)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 1)

    def test_query_using_display_name_substring(self):
        host_list = self.add_2_hosts()

        host_name_substr = host_list[0].display_name[:-2]

        response = self.get(HOST_URL + "?display_name="+host_name_substr)

        # FIXME: check the results
        self.assertEqual(len(response["results"]), 2)

    #@unittest.skip("Incomplete")
    def test_add_facts_to_multiple_hosts(self):
        host_list = self.add_2_hosts()

        response = self.get(HOST_URL, 200)

        # Currently a hack, but I wanted to play with the searching of the facts
        # Needs more work, validation of results, etc
        url = HOST_URL+"/"+str(host_list[0].id)+"/facts/ns1"
        url = HOST_URL+"/1,2/facts/ns1"
        print("url:", url)
        response = self.patch(url,{"blah": "blah"}, 200)

        # FIXME: check the results

    def test_add_facts_to_multiple_hosts_one_host_does_not_exist(self):
        pass

    def test_replace_facts_on_multiple_hosts(self):
        pass

    def test_replace_facts_on_multiple_hosts_one_host_does_not_exist(self):
        pass


if __name__ == "__main__":
    unittest.main()
