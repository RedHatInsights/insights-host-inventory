import json
from django.test import Client, TestCase


class MyClient(Client):

    def post(self, *args, **kwargs):
        if "json" in kwargs:
            kwargs["content_type"] = "application/json"
            kwargs["data"] = json.dumps(kwargs["json"])
            del kwargs["json"]
        return super().post(*args, **kwargs)


NS = "testns"
ID = "whoabuddy"


def test_data(display_name="hi", ids=None, tags=None, facts=None):
    return {
        "account": "test",
        "display_name": display_name,
        "ids": ids if ids else {NS: ID},
        "tags": tags if tags else [],
        "facts": facts if facts else {}
    }


class RequestsTest(TestCase):

    def setUp(self):
        self.client = MyClient()

    def get(self, path, status=200):
        return self._response_check(self.client.get(path), status)

    def post(self, path, json, status=200):
        return self._response_check(self.client.post(path, json=json), status)

    def _response_check(self, response, status):
        self.assertEquals(response.status_code, status)
        return response.json()

    def test_create(self):

        self.post("/entities/", test_data(), 201)
        data = self.get(f"/entities/{NS}/{ID}")

        self.assertEquals(data["account"], test_data()["account"])
        self.assertEquals(data["display_name"], test_data()["display_name"])

    def test_append(self):
        # initial create
        self.post("/entities/", test_data(), 201)

        post_data = test_data()
        post_data["facts"]["test2"] = "foo"
        post_data["ids"]["test2"] = "test2id"

        # update initial entity
        data = self.post("/entities/", post_data)

        self.assertEquals(data["facts"]["test2"], "foo")
        self.assertEquals(data["ids"]["test2"], "test2id")

        # fetch same entity and validate merged data
        for ns, id_ in [(NS, ID), ("test2", "test2id")]:
            data = self.get(f"/entities/{ns}/{id_}")

            self.assertEquals(data["facts"]["test2"], "foo")
            self.assertEquals(data["ids"]["test2"], "test2id")

    def test_appends_single_alias_to_multiple_ids(self):
        self.post("/entities/", test_data(ids={NS: ID, "foo": "bar"}), 201)
        self.post("/entities/", test_data(facts={"test": "test"}))

    def test_keeps_facts_namespaced(self):
        self.post("/entities/", test_data(facts={"test": "test"}), 201)
        data = self.post("/entities/", test_data(facts={"test2": "test"}))
        self.assertEquals(data["facts"], {"test": "test", "test2": "test"})

    def test_saves_tags(self):
        self.post("/entities/", test_data(tags=[{"namespace": "ns", "name": "test", "value": "testv"}]), 201)
        data = self.get(f"/entities/{NS}/{ID}")
        self.assertEquals(data["tags"], {
            "ns": {
                "test": "testv"
            }
        })

    def test_namespace_in_post(self):
        """Cannot post to endpoint with namespace in path"""
        self.post(f"/entities/{NS}", test_data(), 400)

    def test_missing_post_data(self):
        """Validate missing "ids" or "account" in post data fails the request"""
        for key in ("ids", "account"):
            post_data = test_data()
            del post_data[key]

            self.post("/entities/", post_data, 400)
