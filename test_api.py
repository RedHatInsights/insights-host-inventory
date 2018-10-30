#!/usr/bin/env python

import unittest
import os
import json
from app import create_app, db
from app.utils import HostWrapper

HOST_URL = "/api/hosts"

NS = "testns"
ID = "whoabuddy"

FACTS = [{"namespace": "ns1", "facts": {"key1": "value1"}}]

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
        json_data=json.dumps(data)
        return self._response_check(self.client().post(path,
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
        canonical_facts = {"test_id":"11-22-33", "another_test_id": "44-55-66"}
        facts = None
        tags = ["/merge_me_1:value1"]

        host_data = test_data(canonical_facts=canonical_facts, facts=facts, tags=tags)
        print(host_data)

        # initial create
        response_data = self.post(HOST_URL, host_data, 201)
        results = response_data["results"]

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        post_data = host_data
        post_data["facts"].clear()
        post_data["facts"] = [{"namespace": "ns2", "facts": {"key2": "value2"}}]
        post_data["canonical_facts"]["test2"] = "test2id"
        post_data["tags"] = ["aws/new_tag_1:new_value_1"]

        expected_tags = tags
        expected_tags.extend(post_data["tags"])

        print("post_data:", post_data)

        # update initial entity
        data = self.post(HOST_URL, post_data, 200)
        results = data["results"]

        self.assertEqual(results["id"], original_id)

        data = self.get("%s/%d" % (HOST_URL, original_id), 200)
        results = data["results"][0]
        print("results:",results)

        self.assertEqual(len(results["facts"]), 2) 
        # sanity check
        #post_data["facts"][0]["facts"]["key2"] = "blah"
        self.assertEqual(results["facts"][1]["facts"], post_data["facts"][0]["facts"])

        # make sure the canonical facts are merged
        self.assertEqual(len(results["canonical_facts"]), 3)
        self.assertEqual(results["canonical_facts"]["test2"], "test2id")

        # make sure the tags are merged
        self.assertEqual(len(results["tags"]), 2)
        self.assertListEqual(results["tags"], expected_tags)

    def test_post_same_facts(self):
        pass

    def test_create_host_with_empty_tags_then_update_tags(self):
        host_data = HostWrapper(test_data())

        # initial create
        response_data = self.post(HOST_URL, host_data.data(), 201)
        results = response_data["results"]

        self.assertIsNotNone(results["id"])

        original_id = results["id"]

        host_data.tags = ["aws/new_tag_1:new_value_1", "aws/k:v"]

        response_data = self.post(HOST_URL, host_data.data(), 200)

        data = self.get("%s/%d" % (HOST_URL, original_id), 200)
        results = HostWrapper(data["results"][0])

        # make sure the tags were added
        self.assertListEqual(results.tags, host_data.tags)


    def test_create_host_with_empty_facts_then_update_facts(self):
        pass

    def test_update_display_name(self):
        pass

    def test_create_host_without_canonical_facts(self):
        pass

    def test_create_host_without_account(self):
        pass

    def test_query_all(self):
        response = self.client().get('/api/hosts')
        # FIXME: check the results
        self.assertEqual(response.status_code, 200)

    def test_query_single_tag(self):
        response = self.client().get('/api/hosts?tag=aws/prod:v')
        # FIXME: check the results
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
