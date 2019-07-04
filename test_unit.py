#!/usr/bin/env python
from base64 import b64encode
from datetime import datetime
from datetime import timezone
from json import dumps
from random import choice
from unittest import main
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

from api import api_operation
from api.host import _order_how
from api.host import _params_to_order_by
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.auth.identity import Identity
from app.auth.identity import SHARED_SECRET_ENV_VAR
from app.auth.identity import validate
from app.config import Config
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.models import Host
from app.models import HostSchema
from app.serialization import _deserialize_canonical_facts
from app.serialization import _deserialize_facts
from app.serialization import _serialize_datetime
from app.serialization import _serialize_facts
from app.serialization import _serialize_uuid
from app.serialization import deserialize_host
from app.serialization import serialize_canonical_facts
from app.serialization import serialize_host
from app.serialization import serialize_host_system_profile
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
        return Identity(account_number="some acct")


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
            identity = Identity(account_number="some acct")
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
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
class HostParamsToOrderByTestCase(TestCase):
    def test_default_is_updated_desc(self, modified_on, id_, order_how):
        actual = _params_to_order_by(None, None)
        expected = (modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_default_for_updated_is_desc(self, modified_on, id_, order_how):
        actual = _params_to_order_by("updated", None)
        expected = (modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_order_by_updated_asc(self, modified_on, id_, order_how):
        actual = _params_to_order_by("updated", "ASC")
        expected = (order_how.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "ASC")

    def test_order_by_updated_desc(self, modified_on, id_, order_how):
        actual = _params_to_order_by("updated", "DESC")
        expected = (order_how.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "DESC")

    @patch("api.host.Host.display_name")
    def test_default_for_display_name_is_asc(self, display_name, modified_on, id_, order_how):
        actual = _params_to_order_by("display_name")
        expected = (display_name.asc.return_value, modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_asc(self, display_name, modified_on, id_, order_how):
        actual = _params_to_order_by("display_name", "ASC")
        expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(display_name, "ASC")

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_desc(self, display_name, modified_on, id_, order_how):
        actual = _params_to_order_by("display_name", "DESC")
        expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
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
        tag = Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al")

        expected_string_tag = "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"

        self._base_structured_to_string_test(tag, expected_string_tag)

    def test_string_to_structured_with_special_characters(self):
        string_tag = "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"

        expected_structured_tag = Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al")

        self._base_string_to_structured_test(string_tag, expected_structured_tag)


class SerializationBaseTestCase(TestCase):
    def _format_uuid_without_hyphens(self, uuid_):
        return uuid_.hex

    def _format_uuid_with_hyphens(self, uuid_):
        return str(uuid_)


class SerializationDeserializeHostCompoundTestCase(TestCase):
    def test_with_all_fields(self):
        canonical_facts = {
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "external_id": "i-05d2313e6b9a42b16",
        }
        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "someacct",
        }
        host_init_data = {
            **canonical_facts,
            **unchanged_data,
            "facts": [
                {"namespace": "some namespace", "facts": {"some key": "some value"}},
                {"namespace": "another namespace", "facts": {"another key": "another value"}},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }

        actual = deserialize_host(host_init_data)
        expected = {
            "canonical_facts": canonical_facts,
            **unchanged_data,
            "facts": {item["namespace"]: item["facts"] for item in host_init_data["facts"]},
            "system_profile_facts": host_init_data["system_profile"],
        }

        self.assertIs(Host, type(actual))
        for key, value in expected.items():
            self.assertEqual(value, getattr(actual, key))

    def test_with_only_required_fields(self):
        account = "some acct"
        canonical_facts = {"fqdn": "some fqdn"}
        host = deserialize_host({"account": account, **canonical_facts})

        self.assertIs(Host, type(host))
        self.assertEqual(canonical_facts, host.canonical_facts)
        self.assertIsNone(host.display_name)
        self.assertIsNone(host.ansible_host)
        self.assertEqual(account, host.account)
        self.assertEqual({}, host.facts)
        self.assertEqual({}, host.system_profile_facts)

    def test_with_invalid_input(self):
        inputs = (
            {},
            {"account": ""},
            {"account": "some account", "fqdn": "some fqdn"},
            {"account": "someacct", "fqdn": None},
            {"account": "someacct", "fqdn": ""},
            {"account": "someacct", "fqdn": "x" * 256},
            {"account": "someacct", "fqdn": "some fqdn", "facts": {"some ns": {"some key": "some value"}}},
        )
        for input in inputs:
            with self.subTest(input=input):
                with self.assertRaises(ValidationException) as context:
                    deserialize_host(input)

                expected_errors = HostSchema().load(input).errors
                self.assertEqual(str(expected_errors), str(context.exception))


@patch("app.serialization.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
@patch("app.serialization.HostSchema")
class SerializationDeserializeHostMockedTestCase(SerializationBaseTestCase):
    class ValidationError(Exception):
        """
        Marshmallow ValidationError mock.
        """

        def __init__(self, messages):
            self.messages = messages

    def _assertRaisedContext(self, exception, context):
        self.assertIs(context, exception.__context__)

    def _assertRaisedFromNone(self, exception):
        self.assertTrue(exception.__suppress_context__)
        self.assertIsNone(exception.__cause__)

    def test_with_all_fields(
        self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host
    ):
        host_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "someacct",
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "external_id": "i-05d2313e6b9a42b16",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }
        host_schema.return_value.load.return_value.data = input

        result = deserialize_host(host_data)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_data)
        deserialize_facts.assert_called_once_with(host_data["facts"])
        deserialize_tags.assert_called_once_with(input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_data["display_name"],
            host_data["ansible_host"],
            host_data["account"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_data["system_profile"],
        )

    def test_without_facts(self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "someacct",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }
        host_schema.return_value.load.return_value.data = input

        result = deserialize_host({})
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_data)
        deserialize_facts.assert_called_once_with(None)
        deserialize_tags.assert_called_once_with(input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_data["display_name"],
            host_data["ansible_host"],
            host_data["account"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_data["system_profile"],
        )

    def test_without_display_name(
        self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host
    ):
        host_data = {
            "ansible_host": "some ansible host",
            "account": "someacct",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }
        host_schema.return_value.load.return_value.data = input

        result = deserialize_host({})
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_data)
        deserialize_facts.assert_called_once_with(host_data["facts"])
        deserialize_tags.assert_called_once_with(input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            None,
            host_data["ansible_host"],
            host_data["account"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_data["system_profile"],
        )

    def test_without_system_profile(
        self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host
    ):
        host_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "someacct",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
        }
        host_schema.return_value.load.return_value.data = input

        result = deserialize_host({})
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_data)
        deserialize_facts.assert_called_once_with(host_data["facts"])
        deserialize_tags.assert_called_once_with(input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_data["display_name"],
            host_data["ansible_host"],
            host_data["account"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            {},
        )

    def test_host_validation(
        self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host
    ):
        input = {"ansible_host": "some ansible host", "account": "some acct"}

        deserialize_host(input)

        host_schema.assert_called_once_with(strict=True)
        host_schema.return_value.load.assert_called_with(input)

    @patch("app.serialization.ValidationError", new=ValidationError)
    def test_invalid_host_error(
        self, host_schema, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host
    ):
        caught_exception = self.ValidationError(["first message", "second message"])
        host_schema.return_value.load.side_effect = caught_exception

        with self.assertRaises(ValidationException) as raises_context:
            deserialize_host({})

        raised_exception = raises_context.exception

        self.assertEqual(str(caught_exception.messages), str(raised_exception))
        self._assertRaisedContext(raised_exception, caught_exception)
        self._assertRaisedFromNone(raised_exception)

        deserialize_canonical_facts.assert_not_called()
        deserialize_facts.assert_not_called()
        host.assert_not_called()

        host_schema.return_value.load.return_value.data.get.assert_not_called()


class SerializationSerializeHostBaseTestCase(SerializationBaseTestCase):
    def _timestamp_to_str(self, timestamp):
        return timestamp.astimezone(timezone.utc).isoformat()

    def _add_saved_fields_to_host(self, host):
        host.id = uuid4()
        host.created_on = datetime.now()
        host.modified_on = datetime.now()

    def _serialize_host_saved_fields(self, host):
        return {
            "id": self._format_uuid_with_hyphens(host.id),
            "created": self._timestamp_to_str(host.created_on),
            "updated": self._timestamp_to_str(host.modified_on),
        }

    def _all_canonical_facts(self, canonical_facts):
        fields = (
            "insights_id",
            "rhel_machine_id",
            "subscription_manager_id",
            "satellite_id",
            "bios_uuid",
            "ip_addresses",
            "fqdn",
            "mac_addresses",
            "external_id",
        )
        return {field: canonical_facts.get(field) for field in fields}


class SerializationSerializeHostCompoundTestCase(SerializationSerializeHostBaseTestCase, SerializationBaseTestCase):
    def test_with_all_fields(self):
        canonical_facts = {
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "external_id": "i-05d2313e6b9a42b16",
        }
        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "someacct",
        }
        host_init_data = {
            "canonical_facts": canonical_facts,
            **unchanged_data,
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
        }
        host = Host(**host_init_data)
        self._add_saved_fields_to_host(host)
        actual = serialize_host(host)
        expected = {
            **canonical_facts,
            **unchanged_data,
            "facts": [
                {"namespace": namespace, "facts": facts} for namespace, facts in host_init_data["facts"].items()
            ],
            **self._serialize_host_saved_fields(host),
        }
        self.assertEqual(expected, actual)

    def test_with_only_required_fields(self):
        unchanged_data = {"display_name": None, "account": None}
        host_init_data = {"canonical_facts": {"fqdn": "some fqdn"}, **unchanged_data, "facts": {}}
        host = Host(**host_init_data)
        self._add_saved_fields_to_host(host)

        actual = serialize_host(host)
        expected = {
            **self._all_canonical_facts(host_init_data["canonical_facts"]),
            "ansible_host": None,
            **unchanged_data,
            "facts": [],
            **self._serialize_host_saved_fields(host),
        }
        self.assertEqual(expected, actual)


@patch("app.serialization._serialize_facts")
@patch("app.serialization.serialize_canonical_facts")
class SerializationSerializeHostMockedTestCase(SerializationSerializeHostBaseTestCase, SerializationBaseTestCase):
    def test_with_all_fields(self, serialize_canonical_facts, serialize_facts):
        canonical_facts = {"insights_id": self._format_uuid_with_hyphens(uuid4()), "fqdn": "some fqdn"}
        serialize_canonical_facts.return_value = canonical_facts
        facts = [
            {"namespace": "some namespace", "facts": {"some key": "some value"}},
            {"namespace": "another namespace", "facts": {"another key": "another value"}},
        ]
        serialize_facts.return_value = facts

        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
        }
        host_init_data = {"canonical_facts": canonical_facts, **unchanged_data, "facts": facts}
        host = Host(**host_init_data)

        host_attr_data = {"id": uuid4(), "created_on": datetime.utcnow(), "modified_on": datetime.utcnow()}
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        actual = serialize_host(host)
        expected = {
            **canonical_facts,
            **unchanged_data,
            "facts": serialize_facts.return_value,
            "id": self._format_uuid_with_hyphens(host_attr_data["id"]),
            "created": self._timestamp_to_str(host_attr_data["created_on"]),
            "updated": self._timestamp_to_str(host_attr_data["modified_on"]),
        }
        self.assertEqual(expected, actual)

        serialize_canonical_facts.assert_called_once_with(host_init_data["canonical_facts"])
        serialize_facts.assert_called_once_with(host_init_data["facts"])


class SerializationHostFromToJsonCompoundTestCase(SerializationHostToJsonBaseTestCase):
    def test_with_all_fields(self):
        system_profile = {
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            }
        }
        unchanged_data = {
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "external_id": "i-05d2313e6b9a42b16",
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "facts": [
                {"namespace": "some namespace", "facts": {"some key": "some value"}},
                {"namespace": "another namespace", "facts": {"another key": "another value"}},
            ],
        }

        host_init_data = {**unchanged_data, **system_profile}
        host = SerializationHost.from_json(host_init_data)
        self._add_saved_fields_to_host(host)

        actual = SerializationHost.to_json(host)
        expected = {**unchanged_data, **self._serialize_host_saved_fields(host)}
        self.assertEqual(expected, actual)

    def test_with_only_required_fields(self):
        canonical_facts = {"fqdn": "some fqdn"}
        host = SerializationHost.from_json(canonical_facts)
        self._add_saved_fields_to_host(host)

        actual = SerializationHost.to_json(host)
        expected = {
            **self._all_canonical_facts(canonical_facts),
            "ansible_host": None,
            "display_name": None,
            "account": None,
            "facts": [],
            **self._serialize_host_saved_fields(host),
        }
        self.assertEqual(expected, actual)


class SerializationSerializeHostSystemProfileTestCase(SerializationBaseTestCase):
    def test_non_empty_profile_is_not_changed(self):
        system_profile_facts = {
            "number_of_cpus": 1,
            "number_of_sockets": 2,
            "cores_per_socket": 3,
            "system_memory_bytes": 4,
        }
        host = Host(
            canonical_facts={"fqdn": "some fqdn"},
            display_name="some display name",
            system_profile_facts=system_profile_facts,
        )
        host.id = uuid4()

        actual = serialize_host_system_profile(host)
        expected = {"id": self._format_uuid_with_hyphens(host.id), "system_profile": system_profile_facts}
        self.assertEqual(expected, actual)

    def test_empty_profile_is_empty_dict(self):
        host = Host(canonical_facts={"fqdn": "some fqdn"}, display_name="some display name")
        host.id = uuid4()
        host.system_profile_facts = None

        actual = serialize_host_system_profile(host)
        expected = {"id": self._format_uuid_with_hyphens(host.id), "system_profile": {}}
        self.assertEqual(expected, actual)


class SerializationDeserializeCanonicalFactsTestCase(SerializationBaseTestCase):
    def _randomly_formatted_uuid(self, uuid_):
        transformation = choice((self._format_uuid_without_hyphens, self._format_uuid_with_hyphens))
        return transformation(uuid_)

    def _randomly_formatted_sequence(self, seq):
        transformation = choice((list, tuple))
        return transformation(seq)

    def test_values_are_stored_unchanged(self):
        canonical_facts_data = {
            "insights_id": self._randomly_formatted_uuid(uuid4()),
            "rhel_machine_id": self._randomly_formatted_uuid(uuid4()),
            "subscription_manager_id": self._randomly_formatted_uuid(uuid4()),
            "satellite_id": self._randomly_formatted_uuid(uuid4()),
            "bios_uuid": self._randomly_formatted_uuid(uuid4()),
            "ip_addresses": self._randomly_formatted_sequence(("10.10.0.1", "10.10.0.2")),
            "fqdn": "some fqdn",
            "mac_addresses": self._randomly_formatted_sequence(("c2:00:d0:c8:61:01",)),
            "external_id": "i-05d2313e6b9a42b16",
        }
        result = _deserialize_canonical_facts(canonical_facts_data)
        self.assertEqual(result, canonical_facts_data)

    def test_unknown_fields_are_rejected(self):
        canonical_facts = {
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ("10.10.0.1", "10.10.0.2"),
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "external_id": "i-05d2313e6b9a42b16",
        }
        canonical_facts_init_data = {**canonical_facts, "unknown": "something"}
        result = _deserialize_canonical_facts(canonical_facts_init_data)
        self.assertEqual(result, canonical_facts)

    def test_empty_fields_are_rejected(self):
        canonical_facts = {"fqdn": "some fqdn"}
        canonical_facts_init_data = {
            **canonical_facts,
            "insights_id": "",
            "rhel_machine_id": None,
            "ip_addresses": [],
            "mac_addresses": tuple(),
        }
        result = _deserialize_canonical_facts(canonical_facts_init_data)
        self.assertEqual(result, canonical_facts)


class SerializationSerializeCanonicalFactsTestCase(SerializationBaseTestCase):
    def test_contains_all_values_unchanged(self):
        canonical_facts = {
            "insights_id": self._format_uuid_with_hyphens(uuid4()),
            "rhel_machine_id": self._format_uuid_with_hyphens(uuid4()),
            "subscription_manager_id": self._format_uuid_with_hyphens(uuid4()),
            "satellite_id": self._format_uuid_with_hyphens(uuid4()),
            "bios_uuid": self._format_uuid_with_hyphens(uuid4()),
            "ip_addresses": ("10.10.0.1", "10.10.0.2"),
            "fqdn": "some fqdn",
            "mac_addresses": ("c2:00:d0:c8:61:01",),
            "external_id": "i-05d2313e6b9a42b16",
        }
        self.assertEqual(canonical_facts, serialize_canonical_facts(canonical_facts))

    def test_missing_fields_are_filled_with_none(self):
        canonical_fact_fields = (
            "insights_id",
            "rhel_machine_id",
            "subscription_manager_id",
            "satellite_id",
            "bios_uuid",
            "ip_addresses",
            "fqdn",
            "mac_addresses",
            "external_id",
        )
        self.assertEqual({field: None for field in canonical_fact_fields}, serialize_canonical_facts({}))


class SerializationDeserializeFactsTestCase(TestCase):
    def test_non_empty_namespaces_become_dict_items(self):
        facts_data = [
            {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
            {"namespace": "second namespace", "facts": {"third key": "third value"}},
        ]
        self.assertEqual({item["namespace"]: item["facts"] for item in facts_data}, _deserialize_facts(facts_data))

    def test_empty_namespaces_remain_unchanged(self):
        for empty_facts in ({}, None):
            with self.subTest(empty_facts=empty_facts):
                facts_data = [
                    {"namespace": "first namespace", "facts": {"first key": "first value"}},
                    {"namespace": "second namespace", "facts": empty_facts},
                ]
                self.assertEqual(
                    {item["namespace"]: item["facts"] for item in facts_data}, _deserialize_facts(facts_data)
                )

    def test_duplicate_namespaces_are_merged(self):
        facts_data = [
            {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
            {"namespace": "second namespace", "facts": {"third key": "third value"}},
            {"namespace": "first namespace", "facts": {"first key": "fourth value"}},
        ]
        actual = _deserialize_facts(facts_data)
        expected = {
            "first namespace": {"first key": "fourth value", "second key": "second value"},
            "second namespace": {"third key": "third value"},
        }
        self.assertEqual(expected, actual)

    def test_none_becomes_empty_dict(self):
        self.assertEqual({}, _deserialize_facts(None))

    def test_missing_key_raises_exception(self):
        invalid_items = (
            {"spacename": "second namespace", "facts": {"second key": "second value"}},
            {"namespace": "second namespace", "fact": {"second key": "second value"}},
            {"namespace": "second namespace"},
            {},
        )
        for invalid_item in invalid_items:
            with self.subTest(invalid_item=invalid_item):
                facts_data = [{"namespace": "first namespace", "facts": {"first key": "first value"}}, invalid_item]
                with self.assertRaises(InputFormatException):
                    _deserialize_facts(facts_data)


class SerializationSerializeFactsTestCase(TestCase):
    def test_empty_dict_becomes_empty_list(self):
        self.assertEqual([], _serialize_facts({}))

    def test_non_empty_namespaces_become_list_of_dicts(self):
        facts = {
            "first namespace": {"first key": "first value", "second key": "second value"},
            "second namespace": {"third key": "third value"},
        }
        self.assertEqual(
            [{"namespace": namespace, "facts": facts} for namespace, facts in facts.items()], _serialize_facts(facts)
        )

    def test_empty_namespaces_have_facts_as_empty_dicts(self):
        for empty_value in {}, None:
            with self.subTest(empty_value=empty_value):
                facts = {"first namespace": empty_value, "second namespace": {"first key": "first value"}}
                self.assertEqual(
                    [{"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()],
                    _serialize_facts(facts),
                )


class SerializationSerializeDatetime(TestCase):
    def test_utc_timezone_is_used(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(now.isoformat(), _serialize_datetime(now))

    def test_iso_format_is_used(self):
        dt = datetime(2019, 7, 3, 1, 1, 4, 20647, timezone.utc)
        self.assertEqual("2019-07-03T01:01:04.020647+00:00", _serialize_datetime(dt))


class SerializationSerializeUuid(TestCase):
    def test_uuid_has_hyphens_computed(self):
        u = uuid4()
        self.assertEqual(str(u), _serialize_uuid(u))

    def test_uuid_has_hyphens_literal(self):
        u = "4950e534-bbef-4432-bde2-aa3dd2bd0a52"
        self.assertEqual(u, _serialize_uuid(UUID(u)))


if __name__ == "__main__":
    main()
