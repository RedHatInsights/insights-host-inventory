#!/usr/bin/env python

import os

from app.auth import (
    _IDENTITY_HEADER,
    InvalidIdentityError,
    _validate,
    _pick_identity,
    requires_identity,
)
from app.config import Config
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from flask import abort
from json import dumps
from unittest import main, TestCase
from unittest.mock import Mock, patch
import pytest
from werkzeug.exceptions import Forbidden


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
    The identity is read and decoded from the header. If it’s missing or undecodeable,
    an Exception is raised.
    """

    @patch("app.auth.from_encoded")
    @patch("app.auth.request", headers={})
    def test_header_missing(self, request, from_encoded):
        """
        If the identity header is missing, the identity is considered invalid.
        """
        with self.assertRaises(InvalidIdentityError):
            _pick_identity()
        from_encoded.assert_not_called()

    @patch("app.auth.from_encoded")
    @patch("app.auth.request", headers={_IDENTITY_HEADER: Mock()})
    def test_decode(self, request, from_encoded):
        """
        If the identity header is present, it is decoded to obtain the identity object.
        """
        _pick_identity()
        from_encoded.assert_called_once_with(request.headers[_IDENTITY_HEADER])

    @patch("app.auth.request", headers={_IDENTITY_HEADER: Mock()})
    def test_decode_fail(self, request):
        """
        If the identity header decode fails, the identity is considered invalid.
        """
        for error in [KeyError, TypeError, ValueError]:
            with self.subTest(error=error):
                with patch("app.auth.from_encoded", side_effect=error) as from_encoded:
                    with self.assertRaises(InvalidIdentityError):
                        _pick_identity()

    @patch("app.auth.from_encoded")
    @patch("app.auth.request", headers={_IDENTITY_HEADER: Mock()})
    def test_return(self, request, from_encoded):
        """
        The decoded identity is returned.
        """
        result = _pick_identity()
        self.assertEqual(result, from_encoded.return_value)


@patch("app.auth.abort")
@patch("app.auth.login_failure_count.inc")
class AuthLoginFailedTestCase(TestCase):
    """
    A login failure is logged and the current request is aborted with a Forbidden
    status.
    """

    def test_counter(self, inc, abort):
        """
        The login failure counter is incremented.
        """
        _login_failed()
        inc.assert_called_once_with()

    def test_abort(self, inc, abort):
        """
        The current request is aborted with a Forbidden status.
        """
        _login_failed()
        abort.assert_called_once_with(Forbidden.code)


class AuthRequiresIdentityTestCase(TestCase):
    """
    Tests the requires_identity decorator for that it doesn’t accept a request with an
    invalid identity header.
    """
    @requires_identity
    def _view_func(self):
        pass

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth.abort", wraps=abort)
    @patch("app.auth._validate")
    @patch("app.auth._pick_identity", side_effect=InvalidIdentityError)
    def test_pick_identity_fail(self, pick_identity, validate, abort, request_ctx_stack):
        """
        If an InvalidIdentityError is raised while grabbing the identity header, the
        request is aborted as Forbidden before assigning anything to the current
        request context.
        """
        original_identity = request_ctx_stack.top.identity

        with self.assertRaises(Forbidden):
            self._view_func()

        abort.assert_called_once_with(Forbidden.code)
        self.assertIs(original_identity, request_ctx_stack.top.identity)

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth.abort", wraps=abort)
    @patch("app.auth._validate", side_effect=InvalidIdentityError)
    @patch("app.auth._pick_identity")
    def test_validate_fail(self, pick_identity, validate, abort, request_ctx_stack):
        """
        If an InvalidIdentityError is raised while validating the identity header, the
        request is aborted as Forbidden before assigning anything to the current
        request context.
        """
        original_identity = request_ctx_stack.top.identity

        with self.assertRaises(Forbidden):
            self._view_func()

        abort.assert_called_once_with(Forbidden.code)
        self.assertIs(original_identity, request_ctx_stack.top.identity)

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth._validate")
    @patch("app.auth._pick_identity")
    def test_identity_assignment(self, pick_identity, validate, request_ctx_stack):
        """
        If the identity is valid, it is assigned to the current request context.
        """
        self._view_func()
        self.assertEqual(request_ctx_stack.top.identity, pick_identity.return_value)

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth._validate")
    @patch("app.auth._pick_identity")
    def test_view_func_call(self, pick_identity, validate, request_ctx_stack):
        """
        If the identity is valid, the original view function is called with the original
        arguments.
        """
        mock = Mock()
        view_func = requires_identity(mock)

        args = (Mock(),)
        kwargs = {"mock": Mock()}
        view_func(*args, **kwargs)
        mock.assert_called_once_with(*args, **kwargs)

    @patch("app.auth._request_ctx_stack")
    @patch("app.auth._validate")
    @patch("app.auth._pick_identity")
    def test_return(self, pick_identity, validate, request_ctx_stack):
        """
        If the identity is valid, the return value of the original view function is
        returned.
        """
        mock = Mock()
        view_func = requires_identity(mock)
        result = view_func()
        self.assertEqual(result, mock.return_value)


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
