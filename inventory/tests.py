from rest_framework.test import APIRequestFactory, RequestsClient
from django.test import TransactionTestCase

from inventory.views import EntityViewSet
from inventory.populate import populate

TEST_DATA = {"account_number": "1", "display_name": "hi"}


class RequestsTest(TransactionTestCase):

    BASE_URL = "http://localhost"

    def setUp(self):
        self.client = RequestsClient()
        # self.factory = APIRequestFactory()
        # self.view = EntityViewSet.as_view({"get": "list", "post": "create"})

    def test_create(self):
        response = self.client.post(self.BASE_URL + "/entities", json=TEST_DATA)
        # request = self.factory.post("/entities", TEST_DATA, format="json")
        # response = self.view(request)
        assert response.status_code == 201, response.status_code
        saved_id = response.json()["entity"]["id"]
        response = self.client.get(self.BASE_URL + "/entities/%d" % saved_id)
        data = response.json()["entity"]
        assert response.status_code == 200, response.status_code
        assert data["account_number"] == TEST_DATA["account_number"]
        assert data["display_name"] == TEST_DATA["display_name"]

    def test_fetch(self):
        count = 100
        populate(count)
        response = self.client.get(self.BASE_URL + "/entities")
        # request = self.factory.get("/entities")
        # response = self.view(request)
        data = response.json()
        assert response.status_code == 200, response.status_code
        assert len(data["entities"]) == count, len(data["entities"])
