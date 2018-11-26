#!/usr/bin/env python

import os

import test_unit
from api import api_operation
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
from json import dumps
from unittest import main, TestCase
import pytest
from unittest.mock import call, Mock, patch
from werkzeug.exceptions import Forbidden


class Abort(Exception):
    pass


class ApiOperationTestCase(TestCase):
    """
    Test the API operation decorator that increments the request counter with every
    call.
    """
    @patch("api.api_request_count.inc")
    def test_counter_is_incremented(self, inc):
        @api_operation
        def func():
            pass

        func()
        inc.assert_called_once_with()

    def test_arguments_are_passed(self):
        old_func = Mock()
        new_func = api_operation(old_func)

        args = (Mock(),)
        kwargs = {"some_arg": Mock()}

        new_func(*args, **kwargs)
        old_func.assert_called_once_with(*args, **kwargs)

    def test_return_value_is_passed(self):
        old_func = Mock()
        new_func = api_operation(old_func)
        self.assertEqual(old_func.return_value, new_func())


class CreateAppTestCase(TestCase):
    """
    Tests the Flask application initialization.
    """

    config_name = "production"

    @patch("app.db")
    @patch("app.RestyResolver")
    @patch("app.connexion.App")
    @patch("app.auth_init_api")
    @patch("app.Api")
    @patch("app.yaml.safe_load")
    @patch("app.open")
    def test_init_api(
        self, open_mock, safe_load, api, auth_init_api, app, resty_resolver, db
    ):
        create_app(self.config_name)
        api.assert_called_once_with(safe_load.return_value)
        auth_init_api.assert_called_once_with(api.return_value)


class AuthInitApiTestCase(TestCase):
    """
    Tests getting the specification from the API and decoration each operation that
    requires the identity header.
    """

    @patch("app.auth.get_authenticated_views")
    def test_specification(self, get_authenticated_views):
        """
        The specification is taken from the API and parsed.
        """
        api = Mock()
        init_api(api)
        get_authenticated_views.assert_called_once_with(api.specification)

    @patch("app.auth.requires_identity")
    @patch("app.auth.decorate")
    def test_decorate(self, decorate, requires_identity):
        """
        The returned view functions are decorated.
        """
        view_funcs = [Mock(), Mock()]
        with patch(
            "app.auth.get_authenticated_views", return_value=view_funcs
        ) as get_authenticated_views:
            init_api(Mock())

            decorate_calls = []
            requires_identity_calls = []
            for view_func in view_funcs:
                decorate_calls.append(call(view_func, requires_identity))
                requires_identity_calls.append(call(view_func))

            self.assertEqual(decorate_calls, decorate.mock_calls)


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

    def _item(self, count):
        """
        Builds an item with a given number of parameters.
        """
        return {"parameters": [{}] * count}

    @patch(
        "app.auth.connexion._is_requires_identity_param",
        side_effect=[False, True, False]
    )
    def test_one(self, is_requires_identity_param):
        """
        If one parameter is recognized as requiring the identity header, the request is
        recognized as authenticated.
        """
        item = self._item(3)
        self.assertTrue(_requires_identity(item))

    @patch(
        "app.auth.connexion._is_requires_identity_param",
        side_effect=[False, True, True]
    )
    def test_more_than_one(self, is_requires_identity_param):
        """
        If more than one parameter is recognized as requiring the identity header, the
        request is recognized as authenticated.
        """
        item = self._item(3)
        self.assertTrue(_requires_identity(item))

    @patch(
        "app.auth.connexion._is_requires_identity_param",
        side_effect=[False, False, False]
    )
    def test_none(self, is_requires_identity_param):
        """
        If no parameter is recognized as requiring the identity header, the request is
        recognized as not authenticated.
        """
        item = self._item(3)
        self.assertFalse(_requires_identity(item))

    def test_empty(self):
        """
        If there is an empty parameter list, the request is recognized as not
        authenticated.
        """
        item = self._item(0)
        self.assertFalse(_requires_identity(item))


    def test_missing(self):
        """
        If there is no parameter list at all, the request is recognized as not
        authenticated.
        """
        self.assertFalse(_requires_identity({}))


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

    @patch("app.auth.connexion.get_function_from_name")
    @patch("app.auth.connexion._methods")
    @patch("app.auth.connexion._requires_identity")
    def test_no_paths(self, requires_identity, methods, get_function_from_name):
        """
        If there is no paths object at all, no view functions are found.
        """
        result = get_authenticated_views({})
        self.assertEqual([], list(result))

        requires_identity.assert_not_called()
        methods.assert_not_called()
        get_function_from_name.assert_not_called()


    @patch("app.auth.connexion.get_function_from_name")
    @patch("app.auth.connexion._methods")
    @patch("app.auth.connexion._requires_identity")
    def test_empty_paths(self, requires_identity, methods, get_function_from_name):
        """
        If there are no paths in the list, no view functions are found.
        """
        result = get_authenticated_views({"paths": {}})
        self.assertEqual([], list(result))

        requires_identity.assert_not_called()
        methods.assert_not_called()
        get_function_from_name.assert_not_called()

    @patch("app.auth.connexion.get_function_from_name")
    @patch("app.auth.connexion._methods")
    @patch("app.auth.connexion._requires_identity")
    def test_requires_identity_path(
        self, requires_identity, methods, get_function_from_name
    ):
        """
        Each path is tested on whether it requires the identity parameter.
        """
        paths = {
            "/hosts": {"parameters": {"some": "parameters"}},
            "/health": {"get": {"operationId": "some operation"}}
        }
        all(get_authenticated_views({"paths": paths}))

        calls = []
        for path in paths.values():
            calls.append(call(path))
        requires_identity.assert_has_calls(calls, True)

    @patch("app.auth.connexion.get_function_from_name")
    @patch("app.auth.connexion._methods")
    def test_methods_iterator(self, methods, get_function_from_name):
        """
        Methods are retrieved for every path that requires the header identity
        parameter.
        """
        def requires_identity(path):
            return path["get"]["operationId"] == "first operation"

        paths = {
            "/hosts": {"get": {"operationId": "first operation"}},
            "/health": {"get": {"operationId": "second operation"}}
        }
        with patch("app.auth.connexion._requires_identity", requires_identity):
            all(get_authenticated_views({"paths": paths}))

        self.assertIn(call(paths["/hosts"]), methods.mock_calls)
        self.assertNotIn(call(paths["/health"]), methods.mock_calls)

    @patch("app.auth.connexion.get_function_from_name")
    @patch("app.auth.connexion._requires_identity")
    def test_get_function_from_name(self, requires_identity, get_function_from_name):
        """
        View function is retrieved for every operation.
        """
        methods_return_values = [
            [{"operationId": "first operation"}, {"operationId": "second operation"}],
            [{"operationId": "third operation"}]
        ]

        with patch(
            "app.auth.connexion._methods", side_effect=methods_return_values
        ) as methods_mock:
            for _ in get_authenticated_views({"paths": {"/hosts": {}, "/health": {}}}):
                pass

            calls = []
            for methods in methods_return_values:
                for method in methods:
                    calls.append(call(method["operationId"]))

            get_function_from_name.assert_has_calls(calls, True)
            self.assertEqual(len(calls), len(get_function_from_name.mock_calls))

    def test_return(self):
        """
        For every method that requires the identity header a view function is yielded.
        """
        def requires_identity(item):
            return item["get"]["operationId"] == "first operation"

        def get_function_from_name(name):
            return view_funcs[name]

        paths = {
            "/hosts": {"get": {"operationId": "first operation"}},
            "/health": {"get": {"operationId": "second operation"}}
        }
        methods_return_values = []
        for path in paths.values():
            methods_return_values.append(path.values())

        view_funcs = {
            "first operation": Mock(),
            "second operation": Mock()
        }

        with patch(
            "app.auth.connexion._requires_identity", wraps=requires_identity
        ) as requires_identity_mock:
            with patch(
                "app.auth.connexion._methods", side_effect=methods_return_values
            ) as methods_mock:
                with patch(
                    "app.auth.connexion.get_function_from_name", get_function_from_name
                ) as get_function_from_name_mock:
                    self.assertEqual(
                        [view_funcs["first operation"]],
                        list(get_authenticated_views({"paths": paths}))
                    )

    def test_whole(self):
        def get_function_from_name(name):
            return view_funcs[name]

        view_funcs = {
            "first operation": Mock(),
            "second operation": Mock(),
            "third operation": Mock(),
            "fourth operation": Mock(),
        }

        spec = {
            "paths": {
                "/first_path": {
                    "parameters": [
                        {"in": "header", "name": "x-rh-identity", "required": True}
                    ],
                    "get": {"operationId": "first operation"}
                },
                "/second_path": {
                    "parameters": [
                        {"in": "header", "name": "x-rh-identity", "required": False}
                    ],
                    "get": {"operationId": "second operation"}
                },
                "/third_path": {
                    "parameters": [{"in": "header", "name": "x-rh-identity"}],
                    "get": {"operationId": "third operation"}
                },
                "/fourth_path": {"get": {"operationId": "fourth operation"}}
            }
        }

        with patch(
            "app.auth.connexion.get_function_from_name", get_function_from_name
        ) as get_function_from_name_mock:
            result = list(get_authenticated_views(spec))
            self.assertEqual([view_funcs["first operation"]], result)


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

    def test_decorate(self):
        """
        The decorator function is passed the original function.
        """
        def decorator(func):
            return func

        decorator_mock = Mock(wraps=decorator)

        decorate(test_unit.Abort, decorator_mock)
        decorator_mock.assert_called_once_with(test_unit.Abort)

    def test_return(self):
        """
        The decorator return value is returned.
        """
        mock = Mock()
        self.assertEqual(mock.return_value, decorate(test_unit.Abort, mock))

    def test_replace(self):
        """
        The original module function is replaced by the decorated one.
        """
        mock = Mock()
        decorate(test_unit.Abort, mock)

        self.assertEqual(mock.return_value.return_value, test_unit.Abort("something"))
        mock.return_value.assert_called_once_with("something")


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
