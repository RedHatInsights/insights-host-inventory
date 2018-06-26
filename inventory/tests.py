from rest_framework.test import RequestsClient
from django.test import TransactionTestCase
from inventory.populate import populate


def test_data(display_name="hi", ids=None):
    return {
        "account": "test",
        "display_name": display_name,
        "ids": ids if ids else {}
    }


BASE_URL = "http://localhost"


class RequestsTest(TransactionTestCase):

    def setUp(self):
        self.client = RequestsClient()

    def test_create(self):
        ns = "testns"
        id_ = "whoabuddy"
        ids = {ns: id_}
        post_data = test_data(ids=ids)
        response = self.client.post(BASE_URL + "/entities", json=post_data)
        assert response.status_code == 201, response.status_code
        response = self.client.get(BASE_URL + "/entities/%s/%s" % (ns, id_))
        assert response.status_code == 200, response.status_code
        data = response.json()["entity"]
        assert data["account_number"] == post_data["account_number"]
        assert data["display_name"] == post_data["display_name"]

    # def test_fetch(self):
    #     count = 100
    #     populate(count)
    #     response = self.client.get(BASE_URL + "/entities")
    #     data = response.json()
    #     assert response.status_code == 200, response.status_code
    #     assert len(data["entities"]) == count, len(data["entities"])
