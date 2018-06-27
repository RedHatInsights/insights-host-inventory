import json
from django.test import Client, TestCase


def test_data(display_name="hi", ids=None):
    return {
        "account": "test",
        "display_name": display_name,
        "ids": ids if ids else {},
        "tags": [],
        "facts": {}
    }


class RequestsTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.ns, self.id_ = "testns", "whoabuddy"
        self.post_data = test_data(ids={self.ns: self.id_})

    def test_create(self):

        response = self.client.post("/entities/",
                                    content_type="appliction/json",
                                    data=json.dumps(self.post_data))

        assert response.status_code == 201, response.status_code

        response = self.client.get("/entities/%s/%s" % (self.ns, self.id_))
        assert response.status_code == 200, response.status_code

        data = json.loads(response.content)

        assert data["account"] == self.post_data["account"]
        assert data["display_name"] == self.post_data["display_name"]

    def test_append(self):
        response = self.client.post("/entities/",
                                    content_type="appliction/json",
                                    data=json.dumps(self.post_data))

        assert response.status_code == 201, response.status_code

        post_data = dict(self.post_data)
        post_data["facts"]["test2"] = "foo"
        response = self.client.post("/entities/",
                                    content_type="appliction/json",
                                    data=json.dumps(post_data))

        assert response.status_code == 200, response.status_code

        data = json.loads(response.content)

        assert data["facts"]["test2"] == "foo", data["facts"]

        response = self.client.get("/entities/%s/%s" % (self.ns, self.id_))
        assert response.status_code == 200, response.status_code

        data = json.loads(response.content)

        assert data["facts"]["test2"] == "foo", data["facts"]

    def test_namespace_in_post(self):
        """Cannot post to endpoint with namespace in path"""
        response = self.client.post("/entities/%s" % self.ns,
                                    content_type="appliction/json",
                                    data=json.dumps(self.post_data))

        assert response.status_code == 400, response.status_code

    def test_missing_post_data(self):
        """Validate missing "ids" or "account" in post data fails the request"""
        for key in ("ids", "account"):
            post_data = dict(self.post_data)
            del post_data[key]

            response = self.client.post("/entities/",
                                        content_type="appliction/json",
                                        data=json.dumps(post_data))

            assert response.status_code == 400, response.status_code
