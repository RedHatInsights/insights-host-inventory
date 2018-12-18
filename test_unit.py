#!/usr/bin/env python

import os

from api import api_operation
from api.host import FactOperations, update_facts_by_namespace
from app.auth import (
    _validate,
    _pick_identity,
)
from app.config import Config
from app.auth.identity import from_dict, from_encoded, from_json, Identity, validate
from base64 import b64encode
from json import dumps
from unittest import main, TestCase
from unittest.mock import ANY, call, DEFAULT, Mock, patch
import pytest
from werkzeug.exceptions import Forbidden


def list_of_mocks(count):
    mocks = []
    for _ in range(count):
        mocks.append(Mock())
    return mocks


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


@patch("api.host.db.session.commit")
@patch("api.host.current_app")
@patch("api.host.current_identity")
class ApiHostUpdateFactsFromNamespaceTestCase(TestCase):
    """
    Tests updating host facts, a function shared between facts replacement and merge.
    """

    def _sub_test_fact_operations(self, mocks=()):
        for fact_operation in [FactOperations.replace, FactOperations.merge]:
            with self.subTest(fact_operation=fact_operation):
                yield fact_operation

                for mock in mocks:
                    mock.reset_mock()

    @patch(
        "api.host.Host",
        **{"query.filter.return_value.all.return_value": list_of_mocks(2)}
    )
    def _test_counter_is_incremented_for_every_host(
        self, target_counter_name, other_counter_name, fact_operation, _h
    ):
        with patch.multiple(
            "api.host.metrics",
            **{target_counter_name: DEFAULT, other_counter_name: DEFAULT}
        ) as metrics:
            update_facts_by_namespace(fact_operation, range(2), "", {})

            metrics[target_counter_name].inc.assert_called_once_with(2)
            metrics[other_counter_name].inc.assert_called_once_with(0)

    def test_replace_facts_counter_is_incremented_for_every_host(self, _ci, _ca, _c):
        self._test_counter_is_incremented_for_every_host(
            "replace_facts_count", "merge_facts_count", FactOperations.replace
        )

    def test_merge_facts_count_is_incremented_for_every_host(self, _ci, _ca, _c):
        self._test_counter_is_incremented_for_every_host(
            "merge_facts_count", "replace_facts_count", FactOperations.merge
        )

    @patch("api.host.metrics.merge_facts_count.inc")
    @patch("api.host.metrics.replace_facts_count.inc")
    @patch(
        "api.host.Host",
        **{"query.filter.return_value.all.return_value": list_of_mocks(0)}
    )
    def test_counters_are_not_incremented_when_there_are_no_hosts(
        self, _h, replace_inc, merge_inc, _ci, _ca, _c
    ):
        sub_tests = self._sub_test_fact_operations((replace_inc, merge_inc))
        for fact_operation in sub_tests:
            update_facts_by_namespace(fact_operation, range(0), "", {})
            replace_inc.assert_called_once_with(0)
            merge_inc.assert_called_once_with(0)

    @patch("api.host.metrics.merge_facts_count.inc")
    @patch("api.host.metrics.replace_facts_count.inc")
    @patch(
        "api.host.Host",
        **{"query.filter.return_value.all.return_value": list_of_mocks(0)}
    )
    def test_counters_are_incremented_after_db_commit(
        self, _h, replace_inc, merge_inc, _ci, _ca, commit
    ):
        sub_tests = self._sub_test_fact_operations((replace_inc, merge_inc, commit))
        for fact_operation in sub_tests:
            mock_manager = Mock()
            mock_manager.attach_mock(replace_inc, "replace_inc")
            mock_manager.attach_mock(merge_inc, "merge_inc")
            mock_manager.attach_mock(commit, "commit")

            update_facts_by_namespace(fact_operation, range(0), "", {})

            mock_manager.assert_has_calls([
                call.commit(),
                call.replace_inc(ANY),
                call.merge_inc(ANY)
            ])

    @patch("api.host.metrics.merge_facts_count.inc")
    @patch("api.host.metrics.replace_facts_count.inc")
    @patch(
        "api.host.Host",
        **{"query.filter.return_value.all.return_value": list_of_mocks(1)}
    )
    def test_counters_are_not_incremented_on_failed_search(
        self, _h, replace_inc, merge_inc, _ci, _ca, _c
    ):
        sub_tests = self._sub_test_fact_operations((replace_inc, merge_inc))
        for fact_operation in sub_tests:
            update_facts_by_namespace(fact_operation, range(0), "", {})
            replace_inc.assert_not_called()
            merge_inc.assert_not_called()


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
