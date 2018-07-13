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
        "facts": facts if facts else {},
    }


class HttpTestCase(TestCase):

    def setUp(self):
        self.client = MyClient()

    def get(self, path, status=200):
        return self._response_check(self.client.get(path), status)

    def post(self, path, json, status=200):
        return self._response_check(self.client.post(path, json=json), status)

    def _response_check(self, response, status):
        self.assertEquals(response.status_code, status)
        return response.json()


class RequestsTest(HttpTestCase):

    def test_create(self):
        self.post("/assets/", test_data(), 201)
        data = self.get(f"/assets/{NS}/{ID}")

        self.assertEquals(data["account"], test_data()["account"])
        self.assertEquals(data["display_name"], test_data()["display_name"])

    def test_append(self):
        # initial create
        self.post("/assets/", test_data(), 201)

        post_data = test_data()
        post_data["facts"]["test2"] = "foo"
        post_data["ids"]["test2"] = "test2id"

        # update initial asset
        data = self.post("/assets/", post_data)

        self.assertEquals(data["facts"]["test2"], "foo")
        self.assertEquals(data["ids"]["test2"], "test2id")

        # fetch same asset and validate merged data
        for ns, id_ in [(NS, ID), ("test2", "test2id")]:
            data = self.get(f"/assets/{ns}/{id_}")

            self.assertEquals(data["facts"]["test2"], "foo")
            self.assertEquals(data["ids"]["test2"], "test2id")

    def test_appends_single_alias_to_multiple_ids(self):
        self.post("/assets/", test_data(ids={NS: ID, "foo": "bar"}), 201)
        self.post("/assets/", test_data(facts={"test": "test"}))

    def test_keeps_facts_namespaced(self):
        self.post("/assets/", test_data(facts={"test": "test"}), 201)
        data = self.post("/assets/", test_data(facts={"test2": "test"}))
        self.assertEquals(data["facts"], {"test": "test", "test2": "test"})

    def test_fetch_with_two_ids(self):
        self.post("/assets/", test_data(ids={NS: ID, "foo": "bar"}), 201)
        first = self.get(f"/assets/{NS}/{ID}")
        second = self.get("/assets/foo/bar")

        self.assertEquals(first, second)

    def test_namespace_in_post(self):
        """Cannot post to endpoint with namespace in path"""
        self.post(f"/assets/{NS}", test_data(), 400)

    def test_missing_post_data(self):
        """Validate missing "ids" or "account" in post data fails the request"""
        for key in ("ids", "account"):
            post_data = test_data()
            del post_data[key]

            self.post("/assets/", post_data, 400)


class TagTest(HttpTestCase):
    tag_in = {"namespace": "ns", "name": "test", "value": "testv"}
    tag_out = {"ns": {"test": "testv"}}

    def test_saves_tags(self):
        self.post("/assets/", test_data(tags=[self.tag_in]), 201)
        data = self.get(f"/assets/{NS}/{ID}")
        self.assertEquals(data["tags"], self.tag_out)

    def test_appends_tags(self):
        self.post("/assets/", test_data(tags=[self.tag_in]), 201)
        self.post(
            "/assets/",
            test_data(tags=[{"namespace": "ns", "name": "test2", "value": "test2v"}]),
        )

        data = self.get(f"/assets/{NS}/{ID}")
        self.assertEquals(data["tags"], {"ns": {"test": "testv", "test2": "test2v"}})

    def test_does_not_dupe_tags(self):
        self.post("/assets/", test_data(tags=[self.tag_in]), 201)
        self.post("/assets/", test_data(tags=[self.tag_in]))

        data = self.get(f"/assets/{NS}/{ID}")
        self.assertEquals(data["tags"], self.tag_out)
