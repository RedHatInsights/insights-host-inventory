#!/usr/bin/env python

import os

from api import api_operation
from app.config import Config
from app.auth.identity import (Identity,
                               validate,
                               from_auth_header,
                               from_bearer_token,
                               SHARED_SECRET_ENV_VAR)
from base64 import b64encode
from json import dumps
from unittest import main, TestCase
from unittest.mock import Mock, patch
import test.support
from test.support import EnvironmentVarGuard
from werkzeug.exceptions import Forbidden


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
        old_func.__name__ = "old_func"
        new_func = api_operation(old_func)

        args = (Mock(),)
        kwargs = {"some_arg": Mock()}

        new_func(*args, **kwargs)
        old_func.assert_called_once_with(*args, **kwargs)

    def test_return_value_is_passed(self):
        old_func = Mock()
        old_func.__name__ = "old_func"
        new_func = api_operation(old_func)
        self.assertEqual(old_func.return_value, new_func())


class AuthIdentityConstructorTestCase(TestCase):
    """
    Tests the Identity module constructors.
    """

    @staticmethod
    def _identity():
        return Identity(account_number="some number")


class AuthIdentityFromAuthHeaderTest(AuthIdentityConstructorTestCase):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    """

    def test_valid(self):
        """
        Initialize the Identity object with an encoded payload – a base64-encoded JSON.
        That would typically be a raw HTTP header content.
        """
        expected_identity = self._identity()

        identity_data = expected_identity._asdict()

        identity_data_dicts = [identity_data,
                               # Test with extra data in the identity dict
                               {**identity_data, **{"extra_data": "value"}}, ]

        for identity_data in identity_data_dicts:
            with self.subTest(identity_data=identity_data):
                identity = {"identity": identity_data}
                json = dumps(identity)
                base64 = b64encode(json.encode())

                try:
                    actual_identity = from_auth_header(base64)
                    self.assertEqual(expected_identity, actual_identity)
                except (TypeError, ValueError):
                    self.fail()

                self.assertEqual(actual_identity.is_trusted_system, False)

    def test_invalid_type(self):
        """
        Initializing the Identity object with an invalid type that can’t be a Base64
        encoded payload should raise a TypeError.
        """
        with self.assertRaises(TypeError):
            from_auth_header(["not", "a", "string"])

    def test_invalid_value(self):
        """
        Initializing the Identity object with an invalid Base6č encoded payload should
        raise a ValueError.
        """
        with self.assertRaises(ValueError):
            from_auth_header("invalid Base64")

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
            from_auth_header(base64)


class AuthIdentityValidateTestCase(TestCase):
    def test_valid(self):
        try:
            identity = Identity(account_number="some number")
            validate(identity)
            self.assertTrue(True)
        except ValueError:
            self.fail()

    def test_invalid(self):
        account_numbers = [None, ""]
        for account_number in account_numbers:
            with self.subTest(account_number=account_number):
                with self.assertRaises(ValueError):
                    Identity(account_number=account_number)


class TrustedIdentityTestCase(TestCase):
    shared_secret = "ImaSecret"

    def setUp(self):
        self.env = EnvironmentVarGuard()
        self.env.set(SHARED_SECRET_ENV_VAR, self.shared_secret)

    def _build_id(self):
        identity = from_bearer_token(self.shared_secret)
        return identity

    def test_validation(self):
        identity = self._build_id()

        with self.env:
            validate(identity)

    def test_validation_with_invalid_identity(self):
        identity = from_bearer_token("InvalidPassword")

        with self.assertRaises(ValueError):
            validate(identity)

    def test_validation_env_var_not_set(self):
        identity = self._build_id()

        self.env.unset(SHARED_SECRET_ENV_VAR)
        with self.env:
            with self.assertRaises(ValueError):
                validate(identity)

    def test_validation_token_is_None(self):
        tokens = [None, ""]
        for token in tokens:
            with self.subTest(token_value=token):
                with self.assertRaises(ValueError):
                    Identity(token=token)

    def test_is_trusted_system(self):
        identity = self._build_id()

        self.assertEqual(identity.is_trusted_system, True)

    def test_is_account_number_valid_on_trusted_system(self):
        identity = self._build_id()

        self.assertEqual(identity.account_number, "<<TRUSTED IDENTITY>>")


class ConfigTestCase(TestCase):

    def test_configuration_with_env_vars(self):
        app_name = "brontocrane"
        path_prefix = "r/slaterock/platform"
        expected_base_url = f"/{path_prefix}/{app_name}"
        expected_api_path = f"{expected_base_url}/v1"
        expected_mgmt_url_path_prefix = "/mgmt_testing"

        with test.support.EnvironmentVarGuard() as env:
            env.unset(SHARED_SECRET_ENV_VAR)
            env.set("INVENTORY_DB_USER", "fredflintstone")
            env.set("INVENTORY_DB_PASS", "bedrock1234")
            env.set("INVENTORY_DB_HOST", "localhost")
            env.set("INVENTORY_DB_NAME", "SlateRockAndGravel")
            env.set("INVENTORY_DB_POOL_TIMEOUT", "3")
            env.set("INVENTORY_DB_POOL_SIZE", "8")
            env.set("APP_NAME", app_name)
            env.set("PATH_PREFIX", path_prefix)
            env.set("INVENTORY_MANAGEMENT_URL_PATH_PREFIX", expected_mgmt_url_path_prefix)

            conf = Config("testing")

            self.assertEqual(conf.db_uri, "postgresql://fredflintstone:bedrock1234@localhost/SlateRockAndGravel")
            self.assertEqual(conf.db_pool_timeout, 3)
            self.assertEqual(conf.db_pool_size, 8)
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)

    def test_config_default_settings(self):
        expected_api_path = "/api/inventory/v1"
        expected_mgmt_url_path_prefix = "/"

        with test.support.EnvironmentVarGuard() as env:
            # Make sure the environment variables are not set
            for env_var in ("INVENTORY_DB_USER", "INVENTORY_DB_PASS",
                            "INVENTORY_DB_HOST", "INVENTORY_DB_NAME",
                            "INVENTORY_DB_POOL_TIMEOUT", "INVENTORY_DB_POOL_SIZE",
                            "APP_NAME", "PATH_PREFIX"
                            "INVENTORY_MANAGEMENT_URL_PATH_PREFIX",):
                env.unset(env_var)

            conf = Config("testing")

            self.assertEqual(conf.db_uri, "postgresql://insights:insights@localhost/insights")
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)
            self.assertEqual(conf.db_pool_timeout, 5)
            self.assertEqual(conf.db_pool_size, 5)

    def test_config_development_settings(self):
        with test.support.EnvironmentVarGuard() as env:
            env.set("INVENTORY_DB_POOL_TIMEOUT", "3")

            # Test a different "type" (development) of config settings
            conf = Config("development")

            self.assertEqual(conf.db_pool_timeout, 3)


if __name__ == "__main__":
    main()
