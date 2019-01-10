#!/usr/bin/env python

import os

from api import api_operation
from api.host import (
    addHost,
    getHostById,
    getHostList,
    handleTagOperation,
    mergeFacts,
    replaceFacts
)
from app.auth import (
    _validate,
    _pick_identity,
)
from app.config import Config
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from json import dumps
from unittest import main, TestCase
from unittest.mock import Mock, patch
import pytest
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
        new_func = api_operation(old_func)

        args = (Mock(),)
        kwargs = {"some_arg": Mock()}

        new_func(*args, **kwargs)
        old_func.assert_called_once_with(*args, **kwargs)

    def test_return_value_is_passed(self):
        old_func = Mock()
        new_func = api_operation(old_func)
        self.assertEqual(old_func.return_value, new_func())


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


@patch("api.host.current_app")
@patch("api.host.metrics.api_request_count.inc")
@patch("app.auth._request_ctx_stack")
@patch("app.auth._validate")
@patch("app.auth._pick_identity")
class TestApiRequestCountTestCase(TestCase):
    """
    Tests that the API request count metrics counter is incremented on every API
    operation call.
    """

    @patch("api.host.current_identity")
    def test_add_host(
        self,
        current_identity,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the addHost operation is invoked,
        even if the request fails.
        """
        addHost(Mock())  # Fails with 400
        inc.assert_called_once_with()

    @patch("api.host._buildPaginatedHostListResponse")
    @patch("api.host.Host")
    @patch("api.host.current_identity")
    def test_get_host_list(
        self,
        current_identity,
        host,
        build_paginated_host_list_response,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the getHostList operation is
        invoked.
        """
        getHostList()  # Succeeds
        inc.assert_called_once_with()

    @patch("api.host._buildPaginatedHostListResponse")
    @patch("api.host.Host")
    @patch("api.host.current_identity")
    def test_get_host_by_id(
        self,
        current_identity,
        host,
        build_paginated_host_list_response,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the getHostById operation is
        invoked.
        """
        getHostById(Mock())  # Succeeds
        inc.assert_called_once_with()

    @patch("api.host.updateFactsByNamespace")
    def test_replace_facts(
        self,
        update_facts_by_namespace,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the replaceFacts operation is
        invoked.
        """
        replaceFacts(Mock(), Mock(), Mock())  # Succeeds
        inc.assert_called_once_with()

    @patch("api.host.updateFactsByNamespace")
    def test_merge_facts(
        self,
        update_facts_by_namespace,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the mergeFacts operation is invoked.
        """
        mergeFacts(Mock(), Mock(), Mock())  # Succeeds
        inc.assert_called_once_with()

    @patch("api.host.removeTagFromHosts")
    @patch("api.host.validateTagOperationRequest")
    def test_handle_fact_operation(
        self,
        validate_tag_operation_request,
        remove_tag_from_hosts,
        pick_identity,
        validate,
        request_ctx_stack,
        inc,
        current_app
    ):
        """
        The counter is incremented every time when the handleFactOperation operation is
        invoked.
        """
        handleTagOperation(Mock(), Mock())  # Succeeds
        inc.assert_called_once_with()


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
