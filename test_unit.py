#!/usr/bin/env python

import api.host
import os

import test_unit
from app import create_app
from app.auth import init_api, _validate, _pick_identity
from app.auth.connexion import (
    _is_requires_identity_param,
    _methods,
    get_authenticated_views,
    _requires_identity
)
from app.config import Config
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from app.utils import decorate
from base64 import b64encode
from collections import namedtuple
from functools import wraps
from json import dumps
from unittest import main, TestCase
import pytest
from werkzeug.exceptions import Forbidden


class Abort(Exception):
    pass


MockApi = namedtuple("MockApi", ("specification",))


class AuthRequiresIdentityTests:
    """
    Mixin for the TestCases that test the auth.requires_identity decorator. It patches
    the view functions in-place. This makes the tests not interfere with each other.
    """

    @staticmethod
    def _defined_in_auth(view_func):
        """
        The function is defined in the app.auth module’s __init__ file. That is enough
        to assume the requires_identity decorator has been applied.
        """
        path = os.path.relpath(view_func.__code__.co_filename)
        return hasattr(view_func, "__wrapped__") and "app/auth/__init__.py" == path

    @staticmethod
    def _view_funcs():
        """
        Lists all API requests view functions.
        """
        return (
            api.host.addHost,
            api.host.getHostList,
            api.host.mergeFacts,
            api.host.replaceFacts
        )

    def setUp(self):
        """
        Backs up the api.host functions that are replaced in-place in some tests.
        """
        self._view_funcs_backup = self._view_funcs()

    def tearDown(self):
        """
        Restores the backed up api.host functions that are replaced in-place in some
        tests. This makes the tests not order dependent.
        """
        for view_func in self._view_funcs_backup:
            setattr(api.host, view_func.__name__, view_func)


class CreateAppTestCase(AuthRequiresIdentityTests, TestCase):
    """
    Tests the Flask application initialization.
    """

    config_name = "testing"

    def test_init_api_decorates_functions(self):
        """
        After calling create_app, all API request handlers are decorated.
        """
        create_app(self.config_name)

        # The functions are replaced in the module, so it’s necessary to access them
        # from inside the module instead of assigning them to local variables.
        for view_func in self._view_funcs():
            with self.subTest(view_func=view_func):
                # It’s not possible to find the exact decorator. That it’s from the auth
                # module must suffice.
                self.assertTrue(self._defined_in_auth(view_func))

    def test_functions_not_decorated(self):
        """
        Before calling create_app, no API request handlers are decorated.
        """
        for view_func in self._view_funcs():
            with self.subTest(view_func=view_func):
                # It’s not possible to find the exact decorator. That it isn’t from the
                # auth module must suffice.
                self.assertFalse(self._defined_in_auth(view_func))


class AuthInitApiTestCase(AuthRequiresIdentityTests, TestCase):
    """
    Tests getting the specification from the API and decoration each operation that
    requires the identity header.
    """

    def test_decorate(self):
        """
        The specification is taken from the API and parsed. The view functions that
        belong to operations with authenticated path are decorated
        """
        specification = {
            "paths": {
                "/auth": {
                    "parameters": [
                        {"in": "header", "name": "x-rh-identity", "required": True}
                    ],
                    "GET": {"operationId": "api.host.getHostList"}
                },
                "/noauth": {
                    "GET": {"operationId": "api.host.getHostById"}
                }
            }
        }
        init_api(MockApi(specification))
        self.assertTrue(self._defined_in_auth(api.host.getHostList))
        self.assertFalse(self._defined_in_auth(api.host.getHostById))


class AuthConnexionIsRequiresIdentityParamTestCase(TestCase):
    """
    Tests the check whether an OpenAPI parameter specification describes a required
    x-rh-identity header.
    """
    def test_is(self):
        """
        The parameter dictionary is correctly recognized as a required identity header.
        """
        params = [
            {"required": True, "in": "header", "name": "x-rh-identity"},
            {
                "in": "header",
                "something": "else",
                "name": "x-rh-identity",
                "required": True
            },
            {
                "in": "header",
                "name": "x-rh-identity",
                "required": True,
                "type": "string",
                "format": "byte"
            }
        ]
        for param in params:
            with self.subTest(params=param):
                self.assertTrue(_is_requires_identity_param(param))

    def test_is_not(self):
        """
        The parameter dictionary is correctly recognized as not a required identity
        header.
        """
        params = [
            {"required": False, "in": "header", "name": "x-rh-identity"},
            {"required": True, "in": "query", "name": "x-rh-identity"},
            {"required": True, "in": "header", "name": "identity"},
            # For header fields, "required" is optional and its default is false.
            {"in": "header", "name": "x-rh-identity"}
        ]
        for param in params:
            with self.subTest(param=param):
                self.assertFalse(_is_requires_identity_param(param))


class AuthConnexionRequiresIdentityTestCase(TestCase):
    """
    Tests the check whether among the items parameter is (at least) one that says that
    the identity header is required.
    """

    def test_present(self):
        """
        If there is a parameter requiring the identity header, the request is recognized
        as authenticated.
        """
        item = {
            "parameters": [
                {"required": True, "in": "header", "name": "x-rh-identity"},
                {"required": True, "in": "header", "name": "x-rh-insights-request-id"}
            ]
        }
        self.assertTrue(_requires_identity(item))

    def test_absent(self):
        """
        If there is not a parameter requiring the identity header, the request is not
        as not authenticated.
        """
        item = {
            "parameters": [
                {"required": True, "in": "header", "name": "x-rh-insights-request-id"}
            ]
        }
        self.assertFalse(_requires_identity(item))

    def test_empty(self):
        """
        If there is an empty parameter list, the request is recognized as not
        authenticated.
        """
        item = {"parameters": []}
        self.assertFalse(_requires_identity(item))

    def test_missing(self):
        """
        If there is no parameter list at all, the request is recognized as not
        authenticated.
        """
        item = {}
        self.assertFalse(_requires_identity(item))


class AuthConnexionMethodsTestCase(TestCase):
    """
    Tests getting the method objects as a generator from a path specification,
    omitting the parameters object and the keys.
    """
    def test_reject_parameters(self):
        tests = [
            (
                {
                    "get": {"some": "thing"},
                    "parameters": {"a": "parameter"}
                },
                [{"some": "thing"}]
            ),
            (
                {
                    "get": {"some": "thing"},
                    "parameters": {},
                    "post": {"other": "stuff"}
                },
                [{"some": "thing"}, {"other": "stuff"}]
            ),
            ({"parameters": {"a": "parameter"}}, [])
        ]
        for original, filtered in tests:
            with self.subTest(path=original):
                self.assertEqual(filtered, list(_methods(original)))


class AuthConnectionGetAuthenticatedViewsTestCase(TestCase):
    """
    Tests parsing the OpenAPI specification, finding all the operations view functions
    with an information on whether it requires authentication.
    """

    def test_no_paths(self):
        """
        If there is no paths object at all, no view functions are found.
        """
        spec = {}
        result = get_authenticated_views(spec)
        self.assertEqual([], list(result))

    def test_empty_paths(self):
        """
        If there are no paths in the list, no view functions are found.
        """
        spec = {"paths": {}}
        result = get_authenticated_views(spec)
        self.assertEqual([], list(result))

    def test_no_operations(self):
        """
        If there are no operations in the authenticated paths, no view functions are
        found.
        """
        spec = {"paths": {
            "/first": {
                "get": {"operationId": "api.host.getHostList"}
            },
            "/second": {
                "parameters": [
                    {"in": "header", "name": "x-rh-identity", "required": True}
                ]
            }
        }}
        result = get_authenticated_views(spec)
        self.assertEqual([], list(result))

    def test_no_authenticated_paths(self):
        """
        If there are no authenticated paths, no view functions are found.
        """
        spec = {"paths": {
            "/first": {
                "get": {"operationId": "api.host.getHostList"}
            },
            "/second": {
                "parameters": [],
                "get": {"operationId": "api.host.getHostList"}
            },
            "/third": {
                "parameters": [
                    {
                        "in": "header",
                        "name": "x-rh-insights-request-id",
                        "required": True
                    }
                ],
                "get": {"operationId": "api.host.getHostList"}
            }
        }}
        result = get_authenticated_views(spec)
        self.assertEqual([], list(result))

    def test_authenticated(self):
        """
        Operations of paths with a required identity header parameter are found. These
        are resolved to view functions.
        """
        spec = {"paths": {
            "/first": {
                "get": {"operationId": "api.host.getHostList"}
            },
            "/second": {
                "parameters": [
                    {"in": "header", "name": "x-rh-identity", "required": True}
                ],
                "get": {"operationId": "api.host.getHostById"}
            },
            "/third": {
                "parameters": [
                    {"in": "header", "name": "x-rh-identity", "required": True}
                ],
                "get": {"operationId": "api.host.addHost"}
            }
        }}
        result = get_authenticated_views(spec)
        self.assertEqual([api.host.getHostById, api.host.addHost], list(result))


class AuthIdentityConstructorTestCase(TestCase):
    """
    Tests the Identity module constructors.
    """

    @staticmethod
    def _identity():
        return Identity(account_number="some number")


class AuthIdentityFromDictTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a dictionary.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid dictionary.
        """
        identity = self._identity()

        dict_ = {
            "account_number": identity.account_number,
            "internal": {"org_id": "some org id", "extra_field": "extra value"},
        }

        self.assertEqual(identity, from_dict(dict_))

    def test_invalid(self):
        """
        Initializing the Identity object with a dictionary with missing values or with
        anything else should raise TypeError.
        """
        dicts = [{}, {"org_id": "some org id"}, "some string", ["some", "list"]]
        for dict_ in dicts:
            with self.assertRaises(TypeError):
                from_dict(dict_)


class AuthIdentityFromJsonTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a JSON string.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid JSON string.
        """
        identity = self._identity()

        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)

        try:
            self.assertEqual(identity, from_json(json))
        except (TypeError, ValueError):
            self.fail()

    def test_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be JSON should
        raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_json(["not", "a", "string"])

    def test_invalid_value(self):
        """
        Initializing the Identity object with an invalid JSON string should raise a
        ValueError.
        """
        with self.assertRaises(ValueError):
            from_json("invalid JSON")

    def test_invalid_format(self):
        """
        Initializing the Identity object with a JSON string that is not
        formatted correctly.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)

        with self.assertRaises(KeyError):
            from_json(json)


class AuthIdentityFromEncodedTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    """

    def test_valid(self):
        """
        Initialize the Identity object with an encoded payload – a base64-encoded JSON.
        That would typically be a raw HTTP header content.
        """
        identity = self._identity()

        dict_ = {"identity": identity._asdict()}
        json = dumps(dict_)
        base64 = b64encode(json.encode())

        try:
            self.assertEqual(identity, from_encoded(base64))
        except (TypeError, ValueError):
            self.fail()

    def test_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be a Base64
        encoded payload should raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_encoded(["not", "a", "string"])

    def test_invalid_value(self):
        """
        Initializing the Identity object with an invalid Base6č encoded payload should
        raise a ValueError.
        """
        with self.assertRaises(ValueError):
            from_encoded("invalid Base64")

    def test_invalid_format(self):
        """
        Initializing the Identity object with an valid Base64 encoded payload
        that does not contain the "identity" field.
        """
        identity = self._identity()

        dict_ = identity._asdict()
        json = dumps(dict_)
        base64 = b64encode(json.encode())

        with self.assertRaises(KeyError):
            from_encoded(base64)


class AuthIdentityValidateTestCase(TestCase):
    def test_valid(self):
        try:
            identity = Identity(account_number="some number")
            validate(identity)
            self.assertTrue(True)
        except ValueError:
            self.fail()

    def test_invalid(self):
        identities = [
            Identity(account_number=None),
            Identity(account_number=""),
            Identity(account_number=None),
            Identity(account_number=""),
        ]
        for identity in identities:
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    validate(identity)

    def test__validate_identity(self):
        with self.assertRaises(Forbidden):
            _validate(None)
        with self.assertRaises(Forbidden):
            _validate("")
        with self.assertRaises(Forbidden):
            _validate({})


class UtilsDecorateTestCase(TestCase):
    """
    Tests decorating a function by reference.
    """

    def setUp(self):
        """
        Backup the original method that is being replaced.
        """
        self.backup = test_unit.Abort

    def tearDown(self):
        """
        Restore the replaced method from the backup.
        """
        test_unit.Abort = self.backup

    def test_return(self):
        """
        The decorated function is returned.
        """
        def new_func():
            pass

        def decorator(old_func):
            wrapper = wraps(old_func)
            return wrapper(new_func)

        result = decorate(test_unit.Abort, decorator)
        self.assertIs(result, new_func)
        self.assertTrue(hasattr(result, "__wrapped__"))
        self.assertIs(result.__wrapped__, self.backup)

    def test_replace(self):
        """
        The original module function is replaced by the decorated one.
        """
        def new_func():
            pass

        def decorator(old_func):
            wrapper = wraps(old_func)
            return wrapper(new_func)

        decorate(test_unit.Abort, decorator)
        self.assertIs(test_unit.Abort, new_func)
        self.assertTrue(hasattr(test_unit.Abort, "__wrapped__"))
        self.assertIs(test_unit.Abort.__wrapped__, self.backup)


@pytest.mark.usefixtures("monkeypatch")
def test_noauthmode(monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("FLASK_DEBUG", "1")
        m.setenv("NOAUTH", "1")
        assert _pick_identity() == Identity(account_number="0000001")


@pytest.mark.usefixtures("monkeypatch")
def test_config(monkeypatch):
    app_name = "brontocrane"
    path_prefix = "/r/slaterock/platform"
    expected_base_url = f"{path_prefix}/{app_name}"
    expected_api_path = f"{expected_base_url}/api/v1"
    expected_mgmt_url_path_prefix = "/mgmt_testing"

    with monkeypatch.context() as m:
        m.setenv("INVENTORY_DB_USER", "fredflintstone")
        m.setenv("INVENTORY_DB_PASS", "bedrock1234")
        m.setenv("INVENTORY_DB_HOST", "localhost")
        m.setenv("INVENTORY_DB_NAME", "SlateRockAndGravel")
        m.setenv("INVENTORY_DB_POOL_TIMEOUT", "3")
        m.setenv("INVENTORY_DB_POOL_SIZE", "8")
        m.setenv("APP_NAME", app_name)
        m.setenv("PATH_PREFIX", path_prefix)
        m.setenv("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", expected_mgmt_url_path_prefix)

        conf = Config("testing")

        assert conf.db_uri == "postgresql://fredflintstone:bedrock1234@localhost/SlateRockAndGravel"
        assert conf.db_pool_timeout == 3
        assert conf.db_pool_size == 8
        assert conf.api_url_path_prefix == expected_api_path
        assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix


@pytest.mark.usefixtures("monkeypatch")
def test_config_default_settings(monkeypatch):
    expected_base_url = "/r/insights/platform/inventory"
    expected_api_path = f"{expected_base_url}/api/v1"
    expected_mgmt_url_path_prefix = "/"

    with monkeypatch.context() as m:
        # Make sure the environment variables are not set
        for env_var in ("INVENTORY_DB_USER", "INVENTORY_DB_PASS",
                        "INVENTORY_DB_HOST", "INVENTORY_DB_NAME",
                        "INVENTORY_DB_POOL_TIMEOUT", "INVENTORY_DB_POOL_SIZE",
                        "APP_NAME", "PATH_PREFIX"
                        "INVENTORY_MANAGEMENT_URL_PATH_PREFIX",):
            if env_var in os.environ:
                m.delenv(env_var)

        conf = Config("testing")

        assert conf.db_uri == "postgresql://insights:insights@localhost/test_db"
        assert conf.api_url_path_prefix == expected_api_path
        assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix
        assert conf.db_pool_timeout == 5
        assert conf.db_pool_size == 5


@pytest.mark.usefixtures("monkeypatch")
def test_config_development(monkeypatch):
    with monkeypatch.context() as m:
        m.setenv("INVENTORY_DB_POOL_TIMEOUT", "3")

        # Test a different "type" (development) of config settings
        conf = Config("development")

        assert conf.db_pool_timeout == 3


if __name__ == "__main__":
    main()
