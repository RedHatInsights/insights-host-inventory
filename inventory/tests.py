# import json
from rest_framework.test import APIClient
from django.http import JsonResponse, HttpResponseForbidden
from django.test import SimpleTestCase, TestCase
from inventory.auth import header_auth_middleware
from unittest.mock import Mock, patch


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


class AuthMiddlewareTest(SimpleTestCase):
    _auth_data = "some auth data"

    def _mocks(self):
        """
        Mocks the response handler and request objects for the
        middleware.
        """
        return Mock(), Mock(**{"META.get.return_value": self._auth_data})

    @staticmethod
    def _run(get_response, request):
        """
        Runs the middleware with the given response handler and request.
        Expected to be run with mocks.
        """
        middleware = header_auth_middleware(get_response)
        return middleware(request)

    @patch("inventory.auth.validate")
    @patch("inventory.auth.from_http_header")
    def test_no_error(self, from_http_header, validate):
        """
        A request with a valid identity header goes through
        successfully.
        """
        get_response, request = self._mocks()
        response = self._run(get_response, request)

        self.assertEqual(response, get_response.return_value)
        from_http_header.assert_called_once_with(self._auth_data)
        validate.assert_called_once_with(from_http_header.return_value)
        get_response.assert_called_once_with(request)

    @patch("inventory.auth.validate")
    def test_init_error(self, validate):
        """
        Identity header in an invalid format causes the middleware to
        return a Forbidden JSON response.
        """
        errors = [TypeError, ValueError]
        for error in errors:
            with self.subTest(error=error):
                get_response, request = self._mocks()

                with patch("inventory.auth.from_http_header",
                           side_effect=error) as from_http_header:
                    response = self._run(get_response, request)

                self.assertIsInstance(response, JsonResponse)
                self.assertEquals(response.status_code,
                                  HttpResponseForbidden.status_code)
                from_http_header.assert_called_once_with(self._auth_data)
                validate.assert_not_called()
                get_response.assert_not_called()

    @patch("inventory.auth.validate", side_effect=ValueError)
    @patch("inventory.auth.from_http_header")
    def test_validate_error(self, from_http_header, validate):
        """
        Identity header with invalid values causes the middleware to
        return a Forbidden JSON response.
        """
        get_response, request = self._mocks()

        response = self._run(get_response, request)

        self.assertIsInstance(response, JsonResponse)
        self.assertEquals(response.status_code,
                          HttpResponseForbidden.status_code)
        from_http_header.assert_called_once_with(self._auth_data)
        validate.assert_called_once_with(from_http_header.return_value)
        get_response.assert_not_called()

    @patch("inventory.auth.validate")
    @patch("inventory.auth.from_http_header", side_effect=RuntimeError)
    def test_other_error(self, from_http_header, validate):
        """
        An unexpected error in the middleware or validation is not
        caught.
        """
        get_response, request = self._mocks()

        with self.assertRaises(RuntimeError):
            self._run(get_response, request)

        from_http_header.assert_called_once_with(self._auth_data)
        validate.assert_not_called()
        get_response.assert_not_called()
