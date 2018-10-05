# import json
from rest_framework.test import APIClient
from django.test import TestCase


NS = "testns"
ID = "whoabuddy"


def test_data(display_name="hi", canonical_facts=None, tags=None, facts=None):
    return {
        "account": "test",
        "display_name": display_name,
        "canonical_facts": canonical_facts if canonical_facts else {NS: ID},
        "tags": tags if tags else [],
        "facts": facts if facts else {},
    }


class HttpTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def get(self, path, status=200):
        return self._response_check(self.client.get(path), status)

    def post(self, path, json, status=200):
        return self._response_check(self.client.post(path, json, format="json"), status)

    def _response_check(self, response, status):
        self.assertEqual(response.status_code, status, response.content.decode("utf-8"))
        return response.json()


class RequestsTest(HttpTestCase):
    def test_append(self):
        # initial create
        self.post("/api/hosts/", test_data(), 201)

        post_data = test_data()
        post_data["facts"]["test2"] = "foo"
        post_data["canonical_facts"]["test2"] = "test2id"

        # update initial entity
        data = self.post("/api/hosts/", post_data)

        self.assertEqual(data["facts"]["test2"], "foo")
        self.assertEqual(data["canonical_facts"]["test2"], "test2id")

        # fetch same entity and validate merged data
        # for ns, id_ in [(NS, ID), ("test2", "test2id")]:
        #     data = self.get(f"/entities/{ns}/{id_}")

        #     self.assertEqual(data["facts"]["test2"], "foo")
        #     self.assertEqual(data["canonical_facts"]["test2"], "test2id")
