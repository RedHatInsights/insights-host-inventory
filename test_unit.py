#!/usr/bin/env python
from base64 import b64encode
from json import dumps
from unittest import main
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

from api import api_operation
from api.host import _order_how
from api.host import _params_to_order_by
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.auth.identity import Identity
from app.auth.identity import SHARED_SECRET_ENV_VAR
from app.auth.identity import validate
from app.config import Config
from app.utils import Tag
from test_utils import set_environment


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


class AuthIdentityFromAuthHeaderTestCase(AuthIdentityConstructorTestCase):
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

        identity_data_dicts = [
            identity_data,
            # Test with extra data in the identity dict
            {**identity_data, **{"extra_data": "value"}},
        ]

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

    def _build_id(self):
        identity = from_bearer_token(self.shared_secret)
        return identity

    def test_validation(self):
        identity = self._build_id()

        with set_environment({SHARED_SECRET_ENV_VAR: self.shared_secret}):
            validate(identity)

    def test_validation_with_invalid_identity(self):
        identity = from_bearer_token("InvalidPassword")

        with self.assertRaises(ValueError):
            validate(identity)

    def test_validation_env_var_not_set(self):
        identity = self._build_id()

        with set_environment({}):
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

    def test_account_number_is_not_set_for_trusted_system(self):
        identity = self._build_id()

        self.assertEqual(identity.account_number, None)


class ConfigTestCase(TestCase):
    def test_configuration_with_env_vars(self):
        app_name = "brontocrane"
        path_prefix = "r/slaterock/platform"
        expected_base_url = f"/{path_prefix}/{app_name}"
        expected_api_path = f"{expected_base_url}/v1"
        expected_mgmt_url_path_prefix = "/mgmt_testing"

        new_env = {
            "INVENTORY_DB_USER": "fredflintstone",
            "INVENTORY_DB_PASS": "bedrock1234",
            "INVENTORY_DB_HOST": "localhost",
            "INVENTORY_DB_NAME": "SlateRockAndGravel",
            "INVENTORY_DB_POOL_TIMEOUT": "3",
            "INVENTORY_DB_POOL_SIZE": "8",
            "APP_NAME": app_name,
            "PATH_PREFIX": path_prefix,
            "INVENTORY_MANAGEMENT_URL_PATH_PREFIX": expected_mgmt_url_path_prefix,
        }

        with set_environment(new_env):

            conf = Config()

            self.assertEqual(conf.db_uri, "postgresql://fredflintstone:bedrock1234@localhost/SlateRockAndGravel")
            self.assertEqual(conf.db_pool_timeout, 3)
            self.assertEqual(conf.db_pool_size, 8)
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)

    def test_config_default_settings(self):
        expected_api_path = "/api/inventory/v1"
        expected_mgmt_url_path_prefix = "/"

        # Make sure the environment variables are not set
        with set_environment(None):

            conf = Config()

            self.assertEqual(conf.db_uri, "postgresql://insights:insights@localhost/insights")
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)
            self.assertEqual(conf.db_pool_timeout, 5)
            self.assertEqual(conf.db_pool_size, 5)

    def test_config_development_settings(self):
        with set_environment({"INVENTORY_DB_POOL_TIMEOUT": "3"}):

            conf = Config()

            self.assertEqual(conf.db_pool_timeout, 3)


class HostOrderHowTestCase(TestCase):
    def test_asc(self):
        column = Mock()
        result = _order_how(column, "ASC")
        self.assertEqual(result, column.asc())

    def test_desc(self):
        column = Mock()
        result = _order_how(column, "DESC")
        self.assertEqual(result, column.desc())

    def test_error(self):
        invalid_values = (None, "asc", "desc", "BBQ")
        for invalid_value in invalid_values:
            with self.subTest(order_how=invalid_value):
                with self.assertRaises(ValueError):
                    _order_how(Mock(), invalid_value)


@patch("api.host._order_how")
@patch("api.host.Host.modified_on")
class HostParamsToOrderByTestCase(TestCase):
    def test_default_is_updated_desc(self, modified_on, order_how):
        actual = _params_to_order_by(None, None)
        expected = (modified_on.desc.return_value,)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_default_for_updated_is_desc(self, modified_on, order_how):
        actual = _params_to_order_by("updated", None)
        expected = (modified_on.desc.return_value,)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_order_by_updated_asc(self, modified_on, order_how):
        actual = _params_to_order_by("updated", "ASC")
        expected = (order_how.return_value,)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "ASC")

    def test_order_by_updated_desc(self, modified_on, order_how):
        actual = _params_to_order_by("updated", "DESC")
        expected = (order_how.return_value,)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "DESC")

    @patch("api.host.Host.display_name")
    def test_default_for_display_name_is_asc(self, display_name, modified_on, order_how):
        actual = _params_to_order_by("display_name")
        expected = (display_name.asc.return_value, modified_on.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_asc(self, display_name, modified_on, order_how):
        actual = _params_to_order_by("display_name", "ASC")
        expected = (order_how.return_value, modified_on.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(display_name, "ASC")

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_desc(self, display_name, modified_on, order_how):
        actual = _params_to_order_by("display_name", "DESC")
        expected = (order_how.return_value, modified_on.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(display_name, "DESC")


class HostParamsToOrderByErrorsTestCase(TestCase):
    def test_order_by_bad_field_raises_error(self):
        with self.assertRaises(ValueError):
            _params_to_order_by(Mock(), "fqdn")

    def test_order_by_only_how_raises_error(self):
        with self.assertRaises(ValueError):
            _params_to_order_by(Mock(), order_how="ASC")


class TagUtilsTestCase(TestCase):

    """
    string to structured tests
    """

    def _base_string_to_structured_test(self, string_tag, expected_structured_tag):
        structured_tag = Tag().from_string(string_tag)
        self.assertEqual(structured_tag.data(), expected_structured_tag.data())

    def test_simple_string_to_structured(self):
        self._base_string_to_structured_test("NS/key=value", Tag("NS", "key", "value"))

    def test_string_to_structured_no_namespace(self):
        self._base_string_to_structured_test("key=value", Tag(None, "key", "value"))

    def test_simple_string_to_structured_no_value(self):
        self._base_string_to_structured_test("NS/key", Tag("NS", "key", None))

    def test_simple_string_to_structured_only_key(self):
        self._base_string_to_structured_test("key", Tag(None, "key", None))

    """
    structured to string tests
    """

    def _base_structured_to_string_test(self, structured_tag, expected_string_tag):
        string_tag = structured_tag.to_string()
        self.assertEqual(string_tag, expected_string_tag)

    def test_simple_structured_to_string(self):
        structured_tag = Tag("NS", "key", "value")
        expected_string_tag = "NS/key=value"

        self._base_structured_to_string_test(structured_tag, expected_string_tag)

    def test_structured_to_string_no_value(self):
        structured_tag = Tag("namespace", "key")
        expected_string_tag = "namespace/key"

        self._base_structured_to_string_test(structured_tag, expected_string_tag)

    def test_structured_to_string_no_namespace(self):
        structured_tag = Tag(key="key", value="value")
        expected_string_tag = "key=value"

        self._base_structured_to_string_test(structured_tag, expected_string_tag)

    def test_structured_to_string_only_key(self):
        structured_tag = Tag(key="key")
        expected_string_tag = "key"

        self._base_structured_to_string_test(structured_tag, expected_string_tag)

    """
    nested to structured tests
    """

    def _base_nested_to_structured_test(self, nested_tag, expected_structured_tag):
        structured_tag = Tag().from_nested(nested_tag)
        self.assertEqual(structured_tag.data(), expected_structured_tag.data())

    def test_simple_nested_to_structured(self):
        nested_tag = {"NS": {"key": ["value"]}}
        expected_structured_tag = Tag("NS", "key", "value")

        self._base_nested_to_structured_test(nested_tag, expected_structured_tag)

    def test_simple_nested_to_structured_no_value(self):
        nested_tag = {"NS": {"key": []}}
        expected_structured_tag = Tag("NS", "key")

        self._base_nested_to_structured_test(nested_tag, expected_structured_tag)

    """
    structured to nested tests
    """

    def _base_structured_to_nested_test(self, structured_tag, expected_nested_tag):
        nested_tag = structured_tag.to_nested()
        self.assertEqual(nested_tag, expected_nested_tag)

    def test_simple_structured_to_nested(self):
        structured_tag = Tag("NS", "key", "value")
        expected_nested_tag = {"NS": {"key": ["value"]}}

        self._base_structured_to_nested_test(structured_tag, expected_nested_tag)

    def test_structured_to_nested_no_value(self):
        structured_tag = Tag("NS", "key")
        expected_nested_tag = {"NS": {"key": []}}

        self._base_structured_to_nested_test(structured_tag, expected_nested_tag)
    
    """
    create nested from many tags tests
    """

    def test_create_nested_combined(self):
        tags = [Tag("NS1", "Key", "val"), Tag("NS2", "k2")]

        nested_tags = Tag.create_nested_from_tags(tags)

        expected_nested_tags = {"NS1": {"Key": ["val"]}, "NS2": {"k2": []}}

        self.assertEqual(nested_tags, expected_nested_tags)

    def test_create_nested_single_no_value(self):
        tags = [Tag("NS2", "k2")]

        nested_tags = Tag.create_nested_from_tags(tags)

        expected_nested_tags = {"NS2": {"k2": []}}

        self.assertEqual(nested_tags, expected_nested_tags)

    def test_create_nested_from_tags_no_tags(self):
        tags = []

        nested_tags = Tag.create_nested_from_tags(tags)

        expected_nested_tags = {}

        self.assertEqual(nested_tags, expected_nested_tags)

    """
    tags from tag data tests
    """

    def test_create_structered_tags_from_tag_data_list(self):
        tag_data_list = [
            {"value": "val2", "key": "key2", "namespace": "NS2"},
            {"value": "val3", "key": "key3", "namespace": "NS3"},
            {"value": "val3", "key": "key3", "namespace": "NS1"},
        ]
        tag_list = Tag.create_structered_tags_from_tag_data_list(tag_data_list)

        expected_tag_list = [Tag("NS2", "key2", "val2"), Tag("NS3", "key3", "val3"), Tag("NS1", "key3", "val3")]

        self.assertEqual(len(tag_list), len(expected_tag_list))
        for tag, expected_tag in zip(tag_list, expected_tag_list):
            self.assertEqual(tag.data(), expected_tag.data())

    def test_create_structered_tags_from_tag_data_list_no_data(self):
        tag_data_list = None
        tag_list = Tag.create_structered_tags_from_tag_data_list(tag_data_list)

        expected_tag_list = []

        self.assertEqual(len(tag_list), len(expected_tag_list))
        self.assertEqual(tag_list, expected_tag_list)

    """
    special character tests
    """

    def test_structured_to_string_with_special_characters(self):
        tag = Tag("Ns!@#$%^&()","k/e=y\\","v:|\{\}''-+al")

        expected_string_tag = "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"

        self._base_structured_to_string_test(tag, expected_string_tag)

    def test_string_to_structured_with_special_characters(self):
        string_tag = "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"

        expected_structured_tag = Tag("Ns!@#$%^&()","k/e=y\\","v:|\{\}''-+al")

        self._base_string_to_structured_test(string_tag, expected_structured_tag)

if __name__ == "__main__":
    main()
