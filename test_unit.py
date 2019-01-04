#!/usr/bin/env python

import os

from app import create_app
from app.auth import (
    _IDENTITY_HEADER,
    InvalidIdentityError,
    _login_failed,
    _validate,
    _pick_identity,
    requires_identity,
)
from app.config import Config
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from collections import Counter
from contextlib import contextmanager
from json import dumps
from unittest import main, TestCase
import pytest
from werkzeug.exceptions import Forbidden


def _encode_header(dict_):
    """
    Encode the header payload dictionary.
    """
    json = dumps(dict_)
    return b64encode(json.encode())


def _identity():
    """
    Create a valid Identity object.
    """
    return Identity(account_number="some number")


class AuthIdentityFromDictTest(TestCase):
    """
    Tests creating an Identity from a dictionary.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid dictionary.
        """
        identity = _identity()

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


class AuthIdentityFromJsonTest(TestCase):
    """
    Tests creating an Identity from a JSON string.
    """

    def test_valid(self):
        """
        Initialize the Identity object with a valid JSON string.
        """
        identity = _identity()

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
        identity = _identity()

        dict_ = identity._asdict()
        json = dumps(dict_)

        with self.assertRaises(KeyError):
            from_json(json)


class AuthIdentityFromEncodedTest(TestCase):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    """

    def test_valid(self):
        """
        Initialize the Identity object with an encoded payload – a base64-encoded JSON.
        That would typically be a raw HTTP header content.
        """
        identity = _identity()

        dict_ = {"identity": identity._asdict()}
        base64 = _encode_header(dict_)

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
        Initializing the Identity object with an invalid Base64 encoded payload should
        raise a ValueError.
        """
        with self.assertRaises(ValueError):
            from_encoded("invalid Base64")

    def test_invalid_format(self):
        """
        Initializing the Identity object with a valid Base64 encoded payload that does
        not contain the "identity" field.
        """
        json = dumps({})
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
        ]
        for identity in identities:
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    validate(identity)

    def test__validate_identity(self):
        """
        A specific exception is raised if the identity cannot be decoded.
        """
        with self.assertRaises(InvalidIdentityError):
            _validate(None)
        with self.assertRaises(InvalidIdentityError):
            _validate("")
        with self.assertRaises(InvalidIdentityError):
            _validate({})


class AuthPickIdentityTestCase(TestCase):
    """
    The identity is read and decoded from the header.
    """

    def setUp(self):
        self.app = create_app(config_name="testing")

    @contextmanager
    def _request(self, headers):
        with self.app.test_request_context(headers=headers) as context:
            yield context

    def test_header_missing(self):
        """
        If the identity header is missing, the login attempt is considered failed.
        """
        with self._request({}):
            with self.assertRaises(InvalidIdentityError):
                _pick_identity()

    def test_decode_fail_invalid_payload(self):
        """
        If the identity header decode fails, the login attempt is considered failed.
        """
        payload = "invalid"
        with self._request({_IDENTITY_HEADER: payload}):
            with self.assertRaises(InvalidIdentityError):
                # b64decode raises ValueError.
                _pick_identity()

    def test_decode_fail_missing_identity(self):
        """
        If the identity header doesn’t contain the "identity" key, the login attempt is
        considered failed.
        """
        payload = _encode_header({})
        with self._request({_IDENTITY_HEADER: payload}):
            with self.assertRaises(InvalidIdentityError):
                # dict["_identity"] raises KeyError.
                _pick_identity()

    def test_decode_fail_missing_account_number(self):
        """
        If the identity header doesn’t contain the "identity.account_number" key, the
        login attempt is considered failed.
        """
        payload = _encode_header({"identity": {}})
        with self._request({_IDENTITY_HEADER: payload}):
            with self.assertRaises(InvalidIdentityError):
                # Failed "account_number" in dict check raises TypeError.
                _pick_identity()

    def test_return(self):
        """
        The decoded identity is returned.
        """
        identity = _identity()
        payload = _encode_header({"identity": identity._asdict()})
        with self._request({_IDENTITY_HEADER: payload}):
            result = _pick_identity()
        self.assertEqual(identity, result)


class AuthValidateTestCase(TestCase):
    """
    The retrieved identity is validated and if it’s not valid, the login attempt is
    considered failed – the request is aborted.
    """

    def test_valid(self):
        """
        If the identity is valid, the login attempt is not considered failed.
        """
        identity = Identity(account_number="some account")
        try:
            _validate(identity)
            self.assertTrue(True)
        except InvalidIdentityError:
            self.fail()

    def test_login_failed(self):
        """
        If the identity is invalid, the login attempt is considered failed.
        """
        with self.assertRaises(InvalidIdentityError):
            _validate(Identity(account_number=None))


class AuthRequiresIdentityTestCase(TestCase):
    """
    Tests the requires_identity decorator for that it doesn’t accept a request with an
    invalid identity header.
    """
    def setUp(self):
        self.app = create_app(config_name="testing")

    @contextmanager
    def _request(self, headers):
        with self.app.test_request_context(headers=headers) as context:
            yield context

    def test_pick_identity_fail(self):
        """
        If the identity cannot be picked, the request is aborted as Forbidden before
        assigning anything to the current request context.
        """
        @requires_identity
        def view_func():
            """
            Just a dummy to apply the decorator.
            """
            pass

        headers = {}
        with self._request(headers) as request:
            with self.assertRaises(Forbidden):
                view_func()
            self.assertFalse(hasattr(request, "identity"))

    def test_validate_fail(self):
        """
        If the identity is not valid, the request is aborted as Forbidden before
        assigning anything to the current request context.
        """
        @requires_identity
        def view_func():
            """
            Just a dummy to apply the decorator.
            """
            pass

        identity = {"account_number": None}
        payload = _encode_header({"identity": identity})
        with self._request({_IDENTITY_HEADER: payload}) as request:
            with self.assertRaises(Forbidden):
                view_func()
            self.assertFalse(hasattr(request, "identity"))

    def test_identity_assignment(self):
        """
        If the identity is valid, it is assigned to the current request context.
        """
        @requires_identity
        def view_func():
            """
            Just a dummy to apply the decorator.
            """
            pass

        identity = _identity()
        payload = _encode_header({"identity": identity._asdict()})
        with self._request({_IDENTITY_HEADER: payload}) as request:
            view_func()
            self.assertTrue(hasattr(request, "identity"))
            self.assertEqual(identity, request.identity)

    def test_view_func_call(self):
        """
        If the identity is valid, the original view function is called.
        """
        @requires_identity
        def view_func():
            counter["calls"] += 1

        counter = Counter(calls=0)

        identity = _identity()
        payload = _encode_header({"identity": identity._asdict()})
        with self._request({_IDENTITY_HEADER: payload}):
            view_func()

        self.assertEqual(1, counter["calls"])

    def test_view_func_args(self):
        """
        If the identity is valid, the original view function passed the original
        arguments.
        """
        @requires_identity
        def view_func(*a, **kwa):
            calls.append((a, kwa))

        calls = []
        args, kwargs = ("some", "args"), {"some": "kwargs"}

        identity = _identity()
        payload = _encode_header({"identity": identity._asdict()})
        with self._request({_IDENTITY_HEADER: payload}):
            view_func(*args, **kwargs)

        self.assertEqual(calls[0], (args, kwargs))

    def test_return(self):
        """
        If the identity is valid, the return value of the original view function is
        returned.
        """
        @requires_identity
        def view_func():
            return return_value

        return_value = "some return value"

        identity = _identity()
        payload = _encode_header({"identity": identity._asdict()})
        with self._request({_IDENTITY_HEADER: payload}):
            result = view_func()

        self.assertEqual(return_value, result)


class AuthLoginFailedTestCase(TestCase):
    """
    The request is aborted with a Forbidden status.
    """

    def test_abort(self):
        """
        The current request is aborted with a Forbidden status.
        """
        with self.assertRaises(Forbidden):
            _login_failed()


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
