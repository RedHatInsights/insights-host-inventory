# import json
from base64 import b64encode
from rest_framework.test import APIClient
from django.test import SimpleTestCase, TestCase
from inventory.auth.identity import from_dict,\
                                    from_http_header,\
                                    from_json,\
                                    Identity,\
                                    validate
from json import dumps


NS = "testns"
ID = "whoabuddy"


def bypass_auth(old_method):
    """
    A decorator preventing usage of header_auth_middleware in a test.
    """
    def new_method(self_):
        with self_.modify_settings(
            MIDDLEWARE={"remove": "inventory.auth.header_auth_middleware"}
        ):
            old_method(self_)
    return new_method


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

    def get(self, path, status=200, **extra):
        return self._response_check(self.client.get(path, **extra), status)

    def post(self, path, json, status=200):
        return self._response_check(self.client.post(path, json, format="json"), status)

    def _response_check(self, response, status):
        self.assertEqual(response.status_code, status, response.content.decode("utf-8"))
        return response.json()


class RequestsTest(HttpTestCase):

    @bypass_auth
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


class AuthRequestsTest(HttpTestCase):
    def test_unauthorized(self):
        self.get("/api/", 403)

    def test_authorized(self):
        self.get("/api/", 200, HTTP_X_RH_IDENTITY="something")


class AuthIdentityTest(SimpleTestCase):
    identity = Identity(account_number="some number", org_id="some org id")

    def test_from_dict(self):
        """
        Initialize the Identity object with a dictionary.
        """
        dict_ = {"account_number": self.identity.account_number,
                 "org_id": self.identity.org_id}
        identity = from_dict(dict_)
        self.assertEqual(identity, self.identity)

    def test_from_json(self):
        """
        Initialize the Identity object with a JSON string.
        """
        dict_ = self.identity._asdict()
        json = dumps(dict_)
        identity = from_json(json)
        self.assertEqual(identity, self.identity)

    def test_from_http_header(self):
        """
        Initialize the Identity object with a raw HTTP header value –
        a base64-encoded JSON.
        """
        dict_ = self.identity._asdict()
        json = dumps(dict_)
        base64 = b64encode(json.encode())
        identity = from_http_header(base64)
        self.assertEqual(identity, self.identity)

    def test_validate_valid(self):
        try:
            validate(self.identity)
        except ValueError:
            self.fail()

    def test_validate_invalid(self):
        identities = [
            Identity(account_number=None, org_id=None),
            Identity(account_number=None, org_id="some org_id"),
            Identity(account_number="some account_number", org_id=None)
        ]
        for identity in identities:
            with self.subTest(auth_data=identity):
                with self.assertRaises(ValueError):
                    validate(identity)
