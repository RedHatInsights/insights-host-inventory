import json
from django.test import TransactionTestCase, Client


def test_data(display_name="hi", ids=None):
    return {
        "account": "test",
        "display_name": display_name,
        "ids": ids if ids else {},
        "tags": [],
        "facts": {}
    }


class RequestsTest(TransactionTestCase):

    def setUp(self):
        self.client = Client()

    def test_create(self):
        ns = "testns"
        id_ = "whoabuddy"
        ids = {ns: id_}
        post_data = test_data(ids=ids)

        response = self.client.post("/entities/", content_type="appliction/json", data=json.dumps(post_data))
        assert response.status_code == 201, response.status_code

        response = self.client.get("/entities/%s/%s" % (ns, id_))
        assert response.status_code == 200, response.status_code

        data = json.loads(response.content)

        assert data["account"] == post_data["account"]
        assert data["display_name"] == post_data["display_name"]
