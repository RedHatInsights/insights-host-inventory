import unittest
import os
import json
from app import create_app, db

HOST_URL = "/api/hosts"

NS = "testns"
ID = "whoabuddy"

def test_data(display_name="hi", canonical_facts=None, tags=None, facts=None):
    return {
        "account": "test",
        "display_name": display_name,
        "canonical_facts": canonical_facts if canonical_facts else {NS: ID},
        "tags": tags if tags else [],
        "facts": [{"namespace": "ns1", "facts": {"key1": "value1"}}],
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

    def test_create_and_update(self):
        canonical_facts = {"test_id":"11-22-33", "another_test_id": "44-55-66"}
        facts = {"replace_me_1":"value1", "replace_me_2":"value2"}
        tags = ["/merge_me_1:value1"]

        host_data = test_data(canonical_facts=canonical_facts, facts=facts, tags=tags)
        print(host_data)

        # initial create
        response_data = self.client().post(HOST_URL,
                    data=json.dumps(host_data),
                    headers={'content-type':'application/json'})
        results = json.loads(response_data.data)
        print("results:", results)
        results = results["results"]
        self.assertEqual(response_data.status_code, 201)

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
        data = self.client().post(HOST_URL,
                     data=json.dumps(post_data),
                    headers={'content-type':'application/json'})
        self.assertEqual(data.status_code, 200)
        results = json.loads(data.data)
        print("results:",results)
        results = results["results"]

        self.assertEqual(results["id"], original_id)

        data = self.client().get("%s/%d" % (HOST_URL, original_id))
        self.assertEqual(data.status_code, 200)

        print("data",data)
        results = json.loads(data.data)
        print("results:",results)
        results = results["results"][0]
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


    def test_create_host_with_empty_tags_then_update_tags(self):
        pass

    def test_create_host_with_empty_facts_then_update_facts(self):
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
