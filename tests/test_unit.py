#!/usr/bin/env python
from base64 import b64encode
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from itertools import product
from json import dumps
from random import choice
from unittest import main
from unittest import TestCase
from unittest.mock import ANY
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

from confluent_kafka import KafkaException

from api import api_operation
from api import custom_escape
from api.host_query_db import _order_how
from api.host_query_db import params_to_order_by
from api.parsing import custom_fields_parser
from api.parsing import customURIParser
from app import create_app
from app import SPECIFICATION_FILE
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.auth.identity import Identity
from app.auth.identity import SHARED_SECRET_ENV_VAR
from app.config import Config
from app.culling import _Config as CullingConfig
from app.culling import Timestamps
from app.environment import RuntimeEnvironment
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import Host
from app.models import HostSchema
from app.models import SystemProfileNormalizer
from app.queue.event_producer import EventProducer
from app.queue.event_producer import logger as event_producer_logger
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.serialization import _deserialize_canonical_facts
from app.serialization import _deserialize_facts
from app.serialization import _deserialize_tags
from app.serialization import _deserialize_tags_dict
from app.serialization import _deserialize_tags_list
from app.serialization import _serialize_datetime
from app.serialization import _serialize_uuid
from app.serialization import deserialize_canonical_facts
from app.serialization import deserialize_host
from app.serialization import serialize_canonical_facts
from app.serialization import serialize_facts
from app.serialization import serialize_host
from app.serialization import serialize_host_system_profile
from app.utils import Tag
from lib import host_kafka
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


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
        return Identity(USER_IDENTITY)


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
                    self.assertEqual(expected_identity.__dict__, actual_identity.__dict__)
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
            Identity(USER_IDENTITY)
            self.assertTrue(True)
        except ValueError:
            self.fail()

    def test_invalid_org_id(self):
        test_identity = deepcopy(USER_IDENTITY)
        org_ids = [None, ""]
        for org_id in org_ids:
            with self.subTest(org_id=org_id):
                test_identity["org_id"] = org_id
                with self.assertRaises(ValueError):
                    Identity(test_identity)

    def test_invalid_type(self):
        test_identity = deepcopy(USER_IDENTITY)
        identity_types = [None, ""]
        for identity_type in identity_types:
            with self.subTest(identity_type=identity_type):
                test_identity["type"] = identity_type
                with self.assertRaises(ValueError):
                    Identity(test_identity)

    def test_invalid_system_obj(self):
        test_identity = deepcopy(SYSTEM_IDENTITY)
        system_objects = [None, ""]
        for system_object in system_objects:
            with self.subTest(system_object=system_object):
                test_identity["system"] = system_object
                with self.assertRaises(ValueError):
                    Identity(test_identity)

    def test_invalid_auth_types(self):
        test_identities = [deepcopy(USER_IDENTITY), deepcopy(SYSTEM_IDENTITY)]
        auth_types = ["", "foo"]
        for test_identity in test_identities:
            for auth_type in auth_types:
                with self.subTest(auth_type=auth_type):
                    test_identity["auth_type"] = auth_type
                    with self.assertRaises(ValueError):
                        Identity(test_identity)

    def test_invalid_cert_types(self):
        test_identity = deepcopy(SYSTEM_IDENTITY)
        cert_types = [None, "", "foo"]
        for cert_type in cert_types:
            with self.subTest(cert_type=cert_type):
                test_identity["system"]["cert_type"] = cert_type
                with self.assertRaises(ValueError):
                    Identity(test_identity)

    def test_case_insensitive_cert_types(self):
        # Validate that cert_type is case-insensitive
        test_identity = deepcopy(SYSTEM_IDENTITY)
        cert_types = ["RHUI", "Satellite", "system"]
        for cert_type in cert_types:
            with self.subTest(cert_type=cert_type):
                test_identity["system"]["cert_type"] = cert_type
                try:
                    Identity(test_identity)
                    self.assertTrue(True)
                except Exception:
                    self.fail()

    def test_case_insensitive_auth_types(self):
        # Validate that auth_type is case-insensitive
        test_identity = deepcopy(SYSTEM_IDENTITY)
        auth_types = ["JWT-AUTH", "Cert-Auth", "basic-auth"]
        for auth_type in auth_types:
            with self.subTest(auth_type=auth_type):
                test_identity["auth_type"] = auth_type
                try:
                    Identity(test_identity)
                    self.assertTrue(True)
                except Exception:
                    self.fail()

    def test_obsolete_auth_type(self):
        # Validate that removed auth_type not working anymore
        test_identity = deepcopy(SYSTEM_IDENTITY)
        test_identity["auth_type"] = "CLASSIC-PROXY"
        with self.assertRaises(ValueError):
            Identity(test_identity)

    def test_missing_auth_type(self):
        # auth_type must be provided
        test_identity = deepcopy(SYSTEM_IDENTITY)
        test_identity["auth_type"] = None
        with self.assertRaises(ValueError):
            Identity(test_identity)


class TrustedIdentityTestCase(TestCase):
    shared_secret = "ImaSecret"

    def _build_id(self):
        identity = from_bearer_token(self.shared_secret)
        return identity

    def test_validation(self):
        with set_environment({SHARED_SECRET_ENV_VAR: self.shared_secret}):
            self._build_id()

    def test_validation_with_invalid_identity(self):
        with self.assertRaises(ValueError):
            from_bearer_token("InvalidPassword")

    def test_validation_env_var_not_set(self):
        with set_environment({}):
            with self.assertRaises(ValueError):
                self._build_id()

    def test_validation_token_is_None(self):
        tokens = [None, ""]
        for token in tokens:
            with self.subTest(token_value=token):
                with self.assertRaises(ValueError):
                    Identity(token=token)

    def test_is_trusted_system(self):
        with set_environment({SHARED_SECRET_ENV_VAR: self.shared_secret}):
            identity = self._build_id()

        self.assertEqual(identity.is_trusted_system, True)

    def test_org_id_is_not_set_for_trusted_system(self):
        with set_environment({SHARED_SECRET_ENV_VAR: self.shared_secret}):
            identity = self._build_id()

        self.assertFalse(hasattr(identity, "org_id"))


class ConfigTestCase(TestCase):
    @staticmethod
    def _config():
        return Config(RuntimeEnvironment.SERVER)

    def test_configuration_with_env_vars(self):
        app_name = "brontocrane"
        path_prefix = "r/slaterock/platform"
        expected_base_url = f"/{path_prefix}/{app_name}"
        expected_api_path = f"{expected_base_url}/v1"
        expected_mgmt_url_path_prefix = "/mgmt_testing"
        culling_stale_warning_offset_days = 10
        culling_culled_offset_days = 20

        new_env = {
            "INVENTORY_DB_USER": "fredflintstone",
            "INVENTORY_DB_PASS": "bedrock1234",
            "INVENTORY_DB_HOST": "localhost",
            "INVENTORY_DB_PORT": "5432",
            "INVENTORY_DB_NAME": "SlateRockAndGravel",
            "INVENTORY_DB_POOL_TIMEOUT": "3",
            "INVENTORY_DB_POOL_SIZE": "8",
            "APP_NAME": app_name,
            "PATH_PREFIX": path_prefix,
            "INVENTORY_MANAGEMENT_URL_PATH_PREFIX": expected_mgmt_url_path_prefix,
            "CULLING_STALE_WARNING_OFFSET_DAYS": str(culling_stale_warning_offset_days),
            "CULLING_CULLED_OFFSET_DAYS": str(culling_culled_offset_days),
        }

        with set_environment(new_env):
            conf = self._config()

            self.assertEqual(conf.db_uri, "postgresql://fredflintstone:bedrock1234@localhost:5432/SlateRockAndGravel")
            self.assertEqual(conf.db_pool_timeout, 3)
            self.assertEqual(conf.db_pool_size, 8)
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)
            self.assertEqual(
                conf.culling_stale_warning_offset_delta, timedelta(days=culling_stale_warning_offset_days)
            )
            self.assertEqual(conf.culling_culled_offset_delta, timedelta(days=culling_culled_offset_days))

    def test_config_default_settings(self):
        expected_api_path = "/api/inventory/v1"
        expected_mgmt_url_path_prefix = "/"

        # Make sure the runtime_environment variables are not set
        with set_environment(None):
            conf = self._config()

            self.assertEqual(conf.db_uri, "postgresql://insights:insights@localhost:5432/insights")
            self.assertEqual(conf.api_url_path_prefix, expected_api_path)
            self.assertEqual(conf.mgmt_url_path_prefix, expected_mgmt_url_path_prefix)
            self.assertEqual(conf.db_pool_timeout, 5)
            self.assertEqual(conf.db_pool_size, 5)
            self.assertEqual(conf.culling_stale_warning_offset_delta, timedelta(days=7))
            self.assertEqual(conf.culling_culled_offset_delta, timedelta(days=14))

    def test_config_development_settings(self):
        with set_environment({"INVENTORY_DB_POOL_TIMEOUT": "3"}):
            conf = self._config()

            self.assertEqual(conf.db_pool_timeout, 3)

    def test_kafka_produducer_acks(self):
        for value in (0, 1, "all"):
            with self.subTest(value=value):
                with set_environment({"KAFKA_PRODUCER_ACKS": f"{value}"}):
                    self.assertEqual(self._config().kafka_producer["acks"], value)

    def test_kafka_producer_acks_unknown(self):
        with set_environment({"KAFKA_PRODUCER_ACKS": "2"}):
            with self.assertRaises(ValueError):
                self._config()

    def test_kafka_producer_int_params(self):
        for param in (
            "retries",
            "batch.size",
            "linger.ms",
            "retry.backoff.ms",
            "max.in.flight.requests.per.connection",
        ):
            with self.subTest(param=param):
                with set_environment({f"KAFKA_PRODUCER_{param.upper()}": "2020"}):
                    self.assertEqual(self._config().kafka_producer[param], 2020)

    def test_kafka_producer_int_params_invalid(self):
        for param in (
            "retries",
            "batch.size",
            "linger.ms",
            "retry.backoff.ms",
            "max.in.flight.requests.per.connection",
        ):
            with self.subTest(param=param):
                with set_environment({f"KAFKA_PRODUCER_{param.upper()}": "abc"}):
                    with self.assertRaises(ValueError):
                        self._config()

    def test_kafka_producer_defaults(self):
        config = self._config()

        for param, expected_value in (
            ("acks", 1),
            ("retries", 0),
            ("batch.size", 16384),
            ("linger.ms", 0),
            ("retry.backoff.ms", 100),
            ("max.in.flight.requests.per.connection", 5),
        ):
            with self.subTest(param=param):
                self.assertEqual(config.kafka_producer[param], expected_value)


@patch("app.db.get_engine")
@patch("app.Config", **{"return_value.mgmt_url_path_prefix": "/", "return_value.unleash_token": ""})
class CreateAppConfigTestCase(TestCase):
    def test_config_is_assigned(self, config, get_engine):
        app = create_app(RuntimeEnvironment.TEST)
        self.assertIn("INVENTORY_CONFIG", app.config)
        self.assertEqual(config.return_value, app.config["INVENTORY_CONFIG"])


@patch("app.connexion.App")
@patch("app.db.get_engine")
class CreateAppConnexionAppInitTestCase(TestCase):
    @patch("app.TranslatingParser")
    def test_specification_is_provided(self, translating_parser, get_engine, app):
        create_app(RuntimeEnvironment.TEST)

        translating_parser.assert_called_once_with(SPECIFICATION_FILE)
        assert "lazy" not in translating_parser.mock_calls[0].kwargs

        app.return_value.add_api.assert_called_once()
        args = app.return_value.add_api.mock_calls[0].args
        assert len(args) == 1
        assert args[0] is translating_parser.return_value.specification

    def test_specification_is_parsed(self, get_engine, app):
        create_app(RuntimeEnvironment.TEST)
        app.return_value.add_api.assert_called_once()
        args = app.return_value.add_api.mock_calls[0].args
        assert len(args) == 1
        assert args[0] is not None

    # Test here the parsing is working with the referenced schemas from system_profile.spec.yaml
    # and the check parser.specification["components"]["schemas"] - this is more a library test
    def test_translatingparser(self, get_engine, app):
        create_app(RuntimeEnvironment.TEST)
        # Check whether SystemProfileNetworkInterface is inside the schemas section
        # add_api uses the specification as firts argument
        specification = app.return_value.add_api.mock_calls[0].args
        assert "SystemProfileNetworkInterface" in specification[0]["components"]["schemas"]

        # This will pass with openapi.json because the schemas are inlined
        # This will pass when the library acts as it should, inlining the referenced schemas

    # Create an app with bad defs assert that it wont create and will raise and exception
    @patch("app.SPECIFICATION_FILE", value="./swagger/api.spec.yaml")
    def test_yaml_specification(self, translating_parser, get_engine, app):
        with patch("app.create_app", side_effect=Exception("mocked error")):
            with self.assertRaises(Exception):
                create_app(RuntimeEnvironment.TEST)


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


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
class HostParamsToOrderByTestCase(TestCase):
    def test_default_is_updated_desc(self, modified_on, id_, order_how):
        actual = params_to_order_by(None, None)
        expected = (modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_default_for_updated_is_desc(self, modified_on, id_, order_how):
        actual = params_to_order_by("updated", None)
        expected = (modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    def test_order_by_updated_asc(self, modified_on, id_, order_how):
        actual = params_to_order_by("updated", "ASC")
        expected = (order_how.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "ASC")

    def test_order_by_updated_desc(self, modified_on, id_, order_how):
        actual = params_to_order_by("updated", "DESC")
        expected = (order_how.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(modified_on, "DESC")

    @patch("api.host.Host.display_name")
    def test_default_for_display_name_is_asc(self, display_name, modified_on, id_, order_how):
        actual = params_to_order_by("display_name")
        expected = (display_name.asc.return_value, modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_not_called()

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_asc(self, display_name, modified_on, id_, order_how):
        actual = params_to_order_by("display_name", "ASC")
        expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(display_name, "ASC")

    @patch("api.host.Host.display_name")
    def test_order_by_display_name_desc(self, display_name, modified_on, id_, order_how):
        actual = params_to_order_by("display_name", "DESC")
        expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
        self.assertEqual(actual, expected)
        order_how.assert_called_once_with(display_name, "DESC")


class HostParamsToOrderByErrorsTestCase(TestCase):
    def test_order_by_bad_field_raises_error(self):
        with self.assertRaises(ValueError):
            params_to_order_by(Mock(), "fqdn")

    def test_order_by_only_how_raises_error(self):
        with self.assertRaises(ValueError):
            params_to_order_by(Mock(), order_how="ASC")


class TagFromStringTestCase(TestCase):
    def test_all_parts(self):
        self.assertEqual(Tag.from_string("NS/key=value"), Tag("NS", "key", "value"))

    def test_no_namespace(self):
        self.assertEqual(Tag.from_string("key=value"), Tag(None, "key", "value"))

    def test_no_value(self):
        self.assertEqual(Tag.from_string("NS/key"), Tag("NS", "key", None))

    def test_only_key(self):
        self.assertEqual(Tag.from_string("key"), Tag(None, "key", None))

    def test_special_characters_decode(self):
        self.assertEqual(
            Tag.from_string("Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"),
            Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al"),
        )

    def test_special_characters_allowed(self):
        special_characters = ";,?:@&+$-_.!~*'()#"
        self.assertEqual(
            Tag.from_string(f"{special_characters}/{special_characters}={special_characters}"),
            Tag(special_characters, special_characters, special_characters),
        )

    def test_delimiters(self):
        decoded = "a/b=c"
        encoded = "a%2Fb%3Dc"
        self.assertEqual(Tag.from_string(f"{encoded}/{encoded}={encoded}"), Tag(decoded, decoded, decoded))

    def test_encoded_too_long(self):
        decoded = "!" * 86
        encoded = "%21" * 86
        self.assertEqual(Tag.from_string(f"{encoded}/{encoded}={encoded}"), Tag(decoded, decoded, decoded))

    def test_decoded_too_long(self):
        too_long = "a" * 256
        for string_tag in (f"{too_long}/a=a", f"a/{too_long}=a", f"a/a={too_long}"):
            with self.subTest(string_tag=string_tag):
                with self.assertRaises(ValidationException):
                    Tag.from_string(f"{too_long}/{too_long}={too_long}")


class TagToStringTestCase(TestCase):
    def _base_structured_to_string_test(self, structured_tag, expected_string_tag):
        string_tag = structured_tag.to_string()
        self.assertEqual(string_tag, expected_string_tag)

    def test_all_parts(self):
        self.assertEqual(Tag("NS", "key", "value").to_string(), "NS/key=value")

    def test_no_value(self):
        self.assertEqual(Tag("namespace", "key").to_string(), "namespace/key")

    def test_no_namespace(self):
        self.assertEqual(Tag(key="key", value="value").to_string(), "key=value")

    def test_only_key(self):
        self.assertEqual(Tag(key="key").to_string(), "key")

    def test_special_characters(self):
        self.assertEqual(
            Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al").to_string(),
            "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal",
        )


class TagFromNestedTestCase(TestCase):
    def test_all_parts(self):
        self.assertEqual(Tag.from_nested({"NS": {"key": ["value"]}}), Tag("NS", "key", "value"))

    def test_no_value(self):
        self.assertEqual(Tag.from_nested({"NS": {"key": []}}), Tag("NS", "key"))


class TagToNestedTestCase(TestCase):
    def test_all_parts(self):
        self.assertEqual(Tag("NS", "key", "value").to_nested(), {"NS": {"key": ["value"]}})

    def test_no_value(self):
        self.assertEqual(Tag("NS", "key").to_nested(), {"NS": {"key": []}})


class TagFilterTagsTestCase(TestCase):
    def _base_structured_to_filtered_test(self, structured_tags, expected_filtered_structured_tags, searchTerm):
        flat_tags = Tag.create_flat_tags_from_structured(structured_tags)
        expected_filtered_flat_tags = Tag.create_flat_tags_from_structured(expected_filtered_structured_tags)
        filtered_tags = Tag.filter_tags(flat_tags, searchTerm)
        self.assertEqual(len(filtered_tags), len(expected_filtered_flat_tags))

        for i in range(len(filtered_tags)):
            self.assertEqual(filtered_tags[i]["namespace"], expected_filtered_flat_tags[i]["namespace"])
            self.assertEqual(filtered_tags[i]["key"], expected_filtered_flat_tags[i]["key"])
            self.assertEqual(filtered_tags[i]["value"], expected_filtered_flat_tags[i]["value"])

    def test_simple_filter(self):
        structured_tags = [Tag("NS1", "key", "val"), Tag(None, "key", "something"), Tag("NS2", "key2")]
        expected_filtered_tags = [Tag("NS1", "key", "val")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")

    def test_empty_tags(self):
        structured_tags = []
        expected_filtered_tags = []

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")

    def test_search_matches_namesapce(self):
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "NS1")

    def test_search_matches_tag_key(self):
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "key1")

    def test_complex_filter(self):
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "Value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "Value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "vA")

    def test_empty_filter(self):
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "")

    def test_space(self):
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = []

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, " ")

    def test_search_prefix(self):
        # namespace
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "N")

        # key
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "K")

        # value
        structured_tags = [
            Tag("NS1", "key1", "val"),
            Tag(None),
            Tag("NS2", "Key2", "something"),
            Tag("NS3", "key3", "value3"),
        ]
        expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")

    def test_search_suffix(self):
        # namespace
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS1", "key1", "val")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "S1")

        # key
        structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
        expected_filtered_tags = [Tag("NS2", "Key2")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "y2")

        # value
        structured_tags = [
            Tag("NS1", "key1", "val"),
            Tag(None),
            Tag("NS2", "Key2", "something"),
            Tag("NS3", "key3", "value3"),
        ]
        expected_filtered_tags = [Tag("NS3", "key3", "value3")]

        self._base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "ue3")


class TagCreateNestedFromTagsTestCase(TestCase):
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


class SerializationDeserializeHostCompoundTestCase(TestCase):
    def test_with_all_fields(self):
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
        }
        unchanged_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "some org_id",
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
            "reporter": "puptoo",
        }
        stale_timestamp = now()
        full_input = {
            **canonical_facts,
            **unchanged_input,
            "stale_timestamp": stale_timestamp.isoformat(),
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

        actual = deserialize_host(full_input)
        expected = {
            "canonical_facts": canonical_facts,
            **unchanged_input,
            "stale_timestamp": stale_timestamp,
            "facts": {item["namespace"]: item["facts"] for item in full_input["facts"]},
            "system_profile_facts": full_input["system_profile"],
        }

        self.assertIs(Host, type(actual))
        for key, value in expected.items():
            self.assertEqual(value, getattr(actual, key))

    def test_with_only_required_fields(self):
        org_id = "some org_id"
        stale_timestamp = now()
        reporter = "puptoo"
        canonical_facts = {"fqdn": "some fqdn"}

        with self.subTest(schema=HostSchema):
            host = deserialize_host(
                {
                    "org_id": org_id,
                    "stale_timestamp": stale_timestamp.isoformat(),
                    "reporter": reporter,
                    **canonical_facts,
                }
            )

            self.assertIs(Host, type(host))
            self.assertEqual(canonical_facts, host.canonical_facts)
            self.assertIsNone(host.display_name)
            self.assertIsNone(host.ansible_host)
            self.assertEqual(org_id, host.org_id)
            self.assertEqual(stale_timestamp, host.stale_timestamp)
            self.assertEqual(reporter, host.reporter)
            self.assertEqual({}, host.facts)
            self.assertEqual({}, host.tags)
            self.assertEqual({}, host.system_profile_facts)

    def test_with_invalid_input(self):
        stale_timestamp = now().isoformat()
        inputs = (
            {},
            {"org_id": "some org_id", "stale_timestamp": stale_timestamp},
            {"org_id": "some org_id", "reporter": "some reporter"},
            {"stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {"org_id": "", "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {
                "org_id": "some org_id that's wayyyyyyyyyy too long",
                "fqdn": "some fqdn",
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {"org_id": "some org_id", "fqdn": None, "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {"org_id": "some org_id", "fqdn": "", "stale_timestamp": stale_timestamp, "reporter": "some reporter"},
            {
                "org_id": "some org_id",
                "fqdn": "x" * 256,
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "facts": {"some ns": {"some key": "some value"}},
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "mac_addresses": ["00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00:11:22:33:44"],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "fqdn": "some fqdn",
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "insights_id": str(uuid4()) + str(uuid4()),  # longer than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": str(uuid4()) + str(uuid4()),  # longer than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "bios_uuid": "01234567890abcd",  # test shorter than 36 chars
                "tags": [{"namespace": "namespace", "value": "value"}],
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "subscription_manager_id": str(uuid4()).replace(
                    "-", ""
                ),  # uuid witout dashes not allowed for dedup control
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
            {
                "org_id": "some org_id",
                "satellite_id": None,  # test for null
                "stale_timestamp": stale_timestamp,
                "reporter": "some reporter",
            },
        )
        for inp in inputs:
            with self.subTest(input=inp):
                with self.assertRaises(ValidationException) as context:
                    deserialize_host(inp)

                    expected_errors = HostSchema().validate(inp)
                    self.assertEqual(str(expected_errors), str(context.exception))

    # Test that both of the host schemas will pass all of these fields
    # needed because HTTP schema does not accept tags anymore (RHCLOUD - 5593)
    def test_with_all_common_fields(self):
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
        }
        unchanged_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "org_id": "some org_id",
            "reporter": "puptoo",
        }
        stale_timestamp = now()
        full_input = {
            **canonical_facts,
            **unchanged_input,
            "stale_timestamp": stale_timestamp.isoformat(),
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

        with self.subTest(schema=HostSchema):
            actual = deserialize_host(full_input)
            expected = {
                "canonical_facts": canonical_facts,
                **unchanged_input,
                "stale_timestamp": stale_timestamp,
                "facts": {item["namespace"]: item["facts"] for item in full_input["facts"]},
                "system_profile_facts": full_input["system_profile"],
            }

            self.assertIs(Host, type(actual))
            for key, value in expected.items():
                self.assertEqual(value, getattr(actual, key))

    def test_with_tags(self):
        tags = {
            "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
            "another namespace": {"key": ["value"]},
        }
        host = deserialize_host(
            {
                "org_id": "3340851",
                "stale_timestamp": now().isoformat(),
                "reporter": "puptoo",
                "fqdn": "some fqdn",
                "tags": tags,
            }
        )

        self.assertIs(Host, type(host))
        self.assertEqual(tags, host.tags)


@patch("app.models.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
class SerializationDeserializeHostMockedTestCase(TestCase):
    class ValidationError(Exception):
        """
        Marshmallow ValidationError mock.
        """

        def __init__(self, messages, data):
            self.messages = messages
            self.data = data

    def _assertRaisedContext(self, exception, context):
        self.assertIs(context, exception.__context__)

    def _assertRaisedFromNone(self, exception):
        self.assertTrue(exception.__suppress_context__)
        self.assertIsNone(exception.__cause__)

    def test_with_all_fields(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "provider_id": "i-05d2313e6b9a42b16",
            "provider_type": "aws",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})
        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
        )

    def test_without_facts(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(None)
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
        )

    def test_without_tags(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(None)
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
        )

    def test_without_display_name(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
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
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            None,
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
        )

    def test_without_system_profile(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
            "groups": [
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 1",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
                {
                    "id": str(uuid4()),
                    "org_id": "3340851",
                    "account": "some acct",
                    "name": "group 2",
                    "created": now().isoformat(),
                    "updated": now().isoformat(),
                },
            ],
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            {},
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
        )

    def test_without_groups(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "org_id": "3340851",
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
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "stale_timestamp": now().isoformat(),
            "reporter": "some reporter",
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        self.assertEqual(host.return_value, result)

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            deserialize_canonical_facts.return_value,
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            [],
        )

    def test_without_culling_fields(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        common_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some account",
            "tags": [
                {"namespace": "NS1", "key": "key1", "value": "value1"},
                {"namespace": "NS2", "key": "key2", "value": "value2"},
            ],
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "system_profile": {
                "number_of_cpus": 1,
                "number_of_sockets": 2,
                "cores_per_socket": 3,
                "system_memory_bytes": 4,
            },
        }
        for additional_data in ({"stale_timestamp": "2019-12-16T10:10:06.754201+00:00"}, {"reporter": "puptoo"}):
            with self.subTest(additional_data=additional_data):
                for thismock in (deserialize_canonical_facts, deserialize_facts, deserialize_tags):
                    thismock.reset_mock()

                all_data = {**common_data, **additional_data}
                host_schema = Mock(
                    **{"return_value.load.return_value": all_data, "build_model": HostSchema.build_model}
                )

                with self.assertRaises(KeyError):
                    deserialize_host({}, host_schema)

                deserialize_canonical_facts.assert_called_once_with(all_data)
                deserialize_facts.assert_called_once_with(common_data["facts"])
                deserialize_tags.assert_called_once_with(common_data["tags"])
                host.assert_not_called()

    def test_host_validation(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        host_input = {"ansible_host": "some ansible host", "org_id": "some org_id"}

        host_schema = MagicMock()
        deserialize_host(host_input, host_schema)

        host_schema.assert_called_once_with(system_profile_schema=None)
        host_schema.return_value.load.assert_called_with(host_input)

    @patch("app.serialization.ValidationError", new=ValidationError)
    def test_invalid_host_error(self, deserialize_canonical_facts, deserialize_facts, deserialize_tags, host):
        data = {"field_1": "data_1"}
        messages = {"field_1": "Invalid value.", "field_2": "Missing required field."}
        caught_exception = self.ValidationError(messages, data)
        host_schema = Mock(**{"return_value.load.side_effect": caught_exception})

        with self.assertRaises(ValidationException) as raises_context:
            deserialize_host({}, host_schema)

        raised_exception = raises_context.exception

        self.assertTrue(str(caught_exception.messages) in str(raised_exception))
        self._assertRaisedContext(raised_exception, caught_exception)
        self._assertRaisedFromNone(raised_exception)

        deserialize_canonical_facts.assert_not_called()
        deserialize_facts.assert_not_called()
        deserialize_tags.assert_not_called()
        host.assert_not_called()

        host_schema.return_value.load.return_value.get.assert_not_called()


class SerializationSerializeHostBaseTestCase(TestCase):
    def _timestamp_to_str(self, timestamp):
        return timestamp.astimezone(timezone.utc).isoformat()


class SerializationSerializeHostCompoundTestCase(SerializationSerializeHostBaseTestCase):
    @staticmethod
    def _add_days(stale_timestamp, days):
        return stale_timestamp + timedelta(days=days)

    def test_with_all_fields(self):
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ["10.10.0.1", "10.0.0.2"],
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
            "provider_id": "i-05d2313e6b9a42b16",
            "provider_type": "aws",
        }
        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "reporter": "insights",
            "groups": [],
        }
        host_init_data = {
            "canonical_facts": canonical_facts,
            **unchanged_data,
            "facts": {
                "some namespace": {"some key": "some value"},
                "another namespace": {"another key": "another value"},
            },
            "stale_timestamp": now(),
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
        }
        host = Host(**host_init_data)

        host_attr_data = {
            "id": uuid4(),
            "created_on": now(),
            "modified_on": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        config = CullingConfig(stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14))
        actual = serialize_host(host, Timestamps(config), False, ("tags",))
        expected = {
            **canonical_facts,
            **unchanged_data,
            "facts": [
                {"namespace": namespace, "facts": facts} for namespace, facts in host_init_data["facts"].items()
            ],
            "tags": [
                {"namespace": namespace, "key": key, "value": value}
                for namespace, ns_tags in host_init_data["tags"].items()
                for key, values in ns_tags.items()
                for value in values
            ],
            "id": str(host_attr_data["id"]),
            "created": self._timestamp_to_str(host_attr_data["created_on"]),
            "updated": self._timestamp_to_str(host_attr_data["modified_on"]),
            "stale_timestamp": self._timestamp_to_str(host_init_data["stale_timestamp"]),
            "stale_warning_timestamp": self._timestamp_to_str(
                self._add_days(host_init_data["stale_timestamp"], config.stale_warning_offset_delta.days)
            ),
            "culled_timestamp": self._timestamp_to_str(
                self._add_days(host_init_data["stale_timestamp"], config.culled_offset_delta.days)
            ),
            "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
        }
        self.assertEqual(expected, actual)

    def test_with_only_required_fields(self):
        self.maxDiff = None

        for group_data in ({"groups": None}, {"groups": ""}, {"groups": {}}, {"groups": []}, {}):
            with self.subTest(group_data=group_data):
                unchanged_data = {
                    "display_name": None,
                    "org_id": "some org_id",
                    "account": None,
                    "reporter": "yupana",
                }
                host_init_data = {
                    "stale_timestamp": now(),
                    "canonical_facts": {"fqdn": "some fqdn"},
                    **unchanged_data,
                    "facts": {},
                }
                host = Host(**host_init_data)

                host_attr_data = {
                    "id": uuid4(),
                    "created_on": now(),
                    "modified_on": now(),
                    "per_reporter_staleness": host.per_reporter_staleness,
                    **group_data,
                }
                for k, v in host_attr_data.items():
                    setattr(host, k, v)

                config = CullingConfig(
                    stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14)
                )
                actual = serialize_host(host, Timestamps(config), True, ("tags",))
                expected = {
                    **host_init_data["canonical_facts"],
                    "insights_id": None,
                    "subscription_manager_id": None,
                    "system_profile": {},
                    "satellite_id": None,
                    "bios_uuid": None,
                    "ip_addresses": None,
                    "mac_addresses": None,
                    "ansible_host": None,
                    "provider_id": None,
                    "provider_type": None,
                    **unchanged_data,
                    "facts": [],
                    "groups": [],
                    "tags": [],
                    "id": str(host_attr_data["id"]),
                    "created": self._timestamp_to_str(host_attr_data["created_on"]),
                    "updated": self._timestamp_to_str(host_attr_data["modified_on"]),
                    "stale_timestamp": self._timestamp_to_str(host_init_data["stale_timestamp"]),
                    "stale_warning_timestamp": self._timestamp_to_str(
                        self._add_days(host_init_data["stale_timestamp"], config.stale_warning_offset_delta.days)
                    ),
                    "culled_timestamp": self._timestamp_to_str(
                        self._add_days(host_init_data["stale_timestamp"], config.culled_offset_delta.days)
                    ),
                    "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
                }

                self.assertEqual(expected, actual)

    def test_stale_timestamp_config(self):
        for stale_warning_offset_days, culled_offset_days in ((1, 2), (7, 14), (100, 1000)):
            with self.subTest(
                stale_warning_offset_days=stale_warning_offset_days, culled_offset_days=culled_offset_days
            ):
                stale_timestamp = now() + timedelta(days=1)
                host = Host({"fqdn": "some fqdn"}, facts={}, stale_timestamp=stale_timestamp, reporter="some reporter")

                for k, v in (("id", uuid4()), ("created_on", now()), ("modified_on", now())):
                    setattr(host, k, v)

                config = CullingConfig(timedelta(days=stale_warning_offset_days), timedelta(days=culled_offset_days))
                serialized = serialize_host(host, Timestamps(config), False)
                self.assertEqual(
                    self._timestamp_to_str(self._add_days(stale_timestamp, stale_warning_offset_days)),
                    serialized["stale_warning_timestamp"],
                )
                self.assertEqual(
                    self._timestamp_to_str(self._add_days(stale_timestamp, culled_offset_days)),
                    serialized["culled_timestamp"],
                )


@patch("app.serialization._serialize_tags")
@patch("app.serialization.serialize_facts")
@patch("app.serialization.serialize_canonical_facts")
class SerializationSerializeHostMockedTestCase(SerializationSerializeHostBaseTestCase):
    def test_with_all_fields(self, serialize_canonical_facts, serialize_facts, serialize_tags):
        canonical_facts = {"insights_id": str(uuid4()), "fqdn": "some fqdn"}
        serialize_canonical_facts.return_value = canonical_facts
        facts = [
            {"namespace": "some namespace", "facts": {"some key": "some value"}},
            {"namespace": "another namespace", "facts": {"another key": "another value"}},
        ]
        serialize_facts.return_value = facts
        serialize_tags.return_value = [
            {"namespace": "some namespace", "key": "some key", "value": "some value"},
            {"namespace": "some namespace", "key": "some key", "value": "another value"},
            {"namespace": "some namespace", "key": "another key", "value": "value"},
            {"namespace": "another namespace", "key": "key", "value": "value"},
        ]
        stale_timestamp = now()

        unchanged_data = {
            "display_name": "some display name",
            "ansible_host": "some ansible host",
            "account": "some acct",
            "org_id": "3340851",
            "reporter": "some reporter",
            "groups": [],
        }
        host_init_data = {
            "canonical_facts": canonical_facts,
            **unchanged_data,
            "facts": facts,
            "stale_timestamp": stale_timestamp,
            "tags": {
                "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
                "another namespace": {"key": ["value"]},
            },
        }
        host = Host(**host_init_data)

        host_attr_data = {
            "id": uuid4(),
            "created_on": now(),
            "modified_on": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        staleness_offset = Mock(
            **{
                "stale_timestamp.return_value": now(),
                "stale_timestamp.stale_warning_timestamp": now() + timedelta(hours=1),
                "stale_timestamp.culled_timestamp": now() + timedelta(hours=2),
            }
        )
        actual = serialize_host(host, staleness_offset, False, ("tags",))
        expected = {
            **canonical_facts,
            **unchanged_data,
            "facts": serialize_facts.return_value,
            "tags": serialize_tags.return_value,
            "id": str(host_attr_data["id"]),
            "created": self._timestamp_to_str(host_attr_data["created_on"]),
            "updated": self._timestamp_to_str(host_attr_data["modified_on"]),
            "stale_timestamp": self._timestamp_to_str(staleness_offset.stale_timestamp.return_value),
            "stale_warning_timestamp": self._timestamp_to_str(staleness_offset.stale_warning_timestamp.return_value),
            "culled_timestamp": self._timestamp_to_str(staleness_offset.culled_timestamp.return_value),
            "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
        }
        self.assertEqual(expected, actual)

        serialize_canonical_facts.assert_called_once_with(host_init_data["canonical_facts"])
        serialize_facts.assert_called_once_with(host_init_data["facts"])
        serialize_tags.assert_called_once_with(host_init_data["tags"])


class SerializationSerializeHostSystemProfileTestCase(TestCase):
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
            stale_timestamp=now(),
            reporter="yupana",
        )
        host.id = uuid4()

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": system_profile_facts}
        self.assertEqual(expected, actual)

    def test_empty_profile_is_empty_dict(self):
        host = Host(
            canonical_facts={"fqdn": "some fqdn"},
            display_name="some display name",
            stale_timestamp=now(),
            reporter="yupana",
        )
        host.id = uuid4()
        host.system_profile_facts = None

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": {}}
        self.assertEqual(expected, actual)


class SerializationDeserializeCanonicalFactsTestCase(TestCase):
    def _format_uuid_without_hyphens(self, uuid_):
        return uuid_.hex

    def _format_uuid_with_hyphens(self, uuid_):
        return str(uuid_)

    def _randomly_formatted_uuid(self, uuid_):
        transformation = choice((self._format_uuid_without_hyphens, self._format_uuid_with_hyphens))
        return transformation(uuid_)

    def _randomly_formatted_sequence(self, seq):
        transformation = choice((list, tuple))
        return transformation(seq)

    def test_values_are_stored_unchanged(self):
        input = {
            "insights_id": self._randomly_formatted_uuid(uuid4()),
            "subscription_manager_id": self._randomly_formatted_uuid(uuid4()),
            "satellite_id": self._randomly_formatted_uuid(uuid4()),
            "bios_uuid": self._randomly_formatted_uuid(uuid4()),
            "ip_addresses": self._randomly_formatted_sequence(("10.10.0.1", "10.10.0.2")),
            "fqdn": "some fqdn",
            "mac_addresses": self._randomly_formatted_sequence(("c2:00:d0:c8:61:01",)),
        }
        result = _deserialize_canonical_facts(input)
        self.assertEqual(result, input)

    def test_unknown_fields_are_rejected(self):
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ("10.10.0.1", "10.10.0.2"),
            "fqdn": "some fqdn",
            "mac_addresses": ["c2:00:d0:c8:61:01"],
        }
        input = {**canonical_facts, "unknown": "something"}
        result = _deserialize_canonical_facts(input)
        self.assertEqual(result, canonical_facts)

    def test_empty_fields_are_rejected(self):
        canonical_facts = {"fqdn": "some fqdn"}
        input = {**canonical_facts, "insights_id": "", "ip_addresses": [], "mac_addresses": tuple()}
        result = _deserialize_canonical_facts(input)
        self.assertEqual(result, canonical_facts)

    def test_empty_fields_are_not_rejected_when_all_is_passed(self):
        canonical_facts = {"fqdn": "some fqdn", "insights_id": str(uuid4())}
        expected = {
            **canonical_facts,
            "ip_addresses": None,
            "mac_addresses": None,
            "bios_uuid": None,
            "provider_id": None,
            "provider_type": None,
            "satellite_id": None,
            "subscription_manager_id": None,
        }
        result = deserialize_canonical_facts(canonical_facts, all=True)
        self.assertEqual(result, expected)


class SerializationSerializeCanonicalFactsTestCase(TestCase):
    def test_contains_all_values_unchanged(self):
        canonical_facts = {
            "insights_id": str(uuid4()),
            "subscription_manager_id": str(uuid4()),
            "satellite_id": str(uuid4()),
            "bios_uuid": str(uuid4()),
            "ip_addresses": ("10.10.0.1", "10.10.0.2"),
            "fqdn": "some fqdn",
            "mac_addresses": ("c2:00:d0:c8:61:01",),
            "provider_id": "i-05d2313e6b9a42b16",
            "provider_type": "aws",
        }
        self.assertEqual(canonical_facts, serialize_canonical_facts(canonical_facts))

    def test_missing_fields_are_filled_with_none(self):
        canonical_fact_fields = (
            "insights_id",
            "subscription_manager_id",
            "satellite_id",
            "bios_uuid",
            "ip_addresses",
            "fqdn",
            "mac_addresses",
            "provider_id",
            "provider_type",
        )
        self.assertEqual({field: None for field in canonical_fact_fields}, serialize_canonical_facts({}))


class SerializationDeserializeFactsTestCase(TestCase):
    def test_non_empty_namespaces_become_dict_items(self):
        input = [
            {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
            {"namespace": "second namespace", "facts": {"third key": "third value"}},
        ]
        self.assertEqual({item["namespace"]: item["facts"] for item in input}, _deserialize_facts(input))

    def test_empty_namespaces_remain_unchanged(self):
        for empty_facts in ({}, None):
            with self.subTest(empty_facts=empty_facts):
                input = [
                    {"namespace": "first namespace", "facts": {"first key": "first value"}},
                    {"namespace": "second namespace", "facts": empty_facts},
                ]
                self.assertEqual({item["namespace"]: item["facts"] for item in input}, _deserialize_facts(input))

    def test_duplicate_namespaces_are_merged(self):
        input = [
            {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
            {"namespace": "second namespace", "facts": {"third key": "third value"}},
            {"namespace": "first namespace", "facts": {"first key": "fourth value"}},
        ]
        actual = _deserialize_facts(input)
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
                input = [{"namespace": "first namespace", "facts": {"first key": "first value"}}, invalid_item]
                with self.assertRaises(InputFormatException):
                    _deserialize_facts(input)


class SerializationSerializeFactsTestCase(TestCase):
    def test_empty_dict_becomes_empty_list(self):
        self.assertEqual([], serialize_facts({}))

    def test_non_empty_namespaces_become_list_of_dicts(self):
        facts = {
            "first namespace": {"first key": "first value", "second key": "second value"},
            "second namespace": {"third key": "third value"},
        }
        self.assertEqual(
            [{"namespace": namespace, "facts": facts} for namespace, facts in facts.items()], serialize_facts(facts)
        )

    def test_empty_namespaces_have_facts_as_empty_dicts(self):
        for empty_value in {}, None:
            with self.subTest(empty_value=empty_value):
                facts = {"first namespace": empty_value, "second namespace": {"first key": "first value"}}
                self.assertEqual(
                    [{"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()],
                    serialize_facts(facts),
                )


class SerializationSerializeDatetime(TestCase):
    def test_utc_timezone_is_used(self):
        _now = now()
        self.assertEqual(_now.isoformat(), _serialize_datetime(_now))

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


class HostUpdateStaleTimestamp(TestCase):
    def _make_host(self, **values):
        return Host(**{"canonical_facts": {"fqdn": "some fqdn"}, **values})

    def test_always_updated(self):
        old_stale_timestamp = now() + timedelta(days=2)
        old_reporter = "old reporter"
        stale_timestamps = (old_stale_timestamp - timedelta(days=1), old_stale_timestamp - timedelta(days=2))
        reporters = (old_reporter, "new reporter")
        for new_stale_timestamp, new_reporter in product(stale_timestamps, reporters):
            with self.subTest(stale_timestamps=new_stale_timestamp, reporter=new_reporter):
                host = self._make_host(stale_timestamp=old_stale_timestamp, reporter=old_reporter)

                new_stale_timestamp = now() + timedelta(days=2)
                host._update_stale_timestamp(new_stale_timestamp, new_reporter)

                self.assertEqual(new_stale_timestamp, host.stale_timestamp)
                self.assertEqual(new_reporter, host.reporter)


class SerializationDeserializeTags(TestCase):
    def test_deserialize_structured(self):
        for function in (_deserialize_tags, _deserialize_tags_list):
            with self.subTest(function=function):
                structured_tags = [
                    {"namespace": "namespace1", "key": "key1", "value": "value1"},
                    {"namespace": "namespace1", "key": "key1", "value": "value2"},
                    {"namespace": "namespace1", "key": "key2", "value": "value3"},
                    {"namespace": "namespace1", "key": "key2", "value": "value3"},
                    {"namespace": "namespace2", "key": "key3", "value": None},
                    {"namespace": "namespace2", "key": "key3", "value": ""},
                    {"namespace": "namespace2", "key": "key3"},
                    {"namespace": "namespace3", "key": "key4", "value": None},
                    {"namespace": "namespace3", "key": "key4", "value": "value4"},
                    {"namespace": None, "key": "key5", "value": "value5"},
                    {"namespace": "", "key": "key5", "value": "value6"},
                    {"namespace": "null", "key": "key5", "value": "value7"},
                    {"key": "key5", "value": "value7"},
                ]
                nested_tags = function(structured_tags)

                self.assertCountEqual(["namespace1", "namespace2", "namespace3", "null"], nested_tags.keys())
                self.assertCountEqual(["key1", "key2"], nested_tags["namespace1"].keys())
                self.assertCountEqual(["value1", "value2"], nested_tags["namespace1"]["key1"])
                self.assertCountEqual(["value3"], nested_tags["namespace1"]["key2"])
                self.assertCountEqual(["key3"], nested_tags["namespace2"].keys())
                self.assertEqual([], nested_tags["namespace2"]["key3"])
                self.assertCountEqual(["key4"], nested_tags["namespace3"].keys())
                self.assertCountEqual(["value4"], nested_tags["namespace3"]["key4"])
                self.assertCountEqual(["key5"], nested_tags["null"].keys())
                self.assertCountEqual(["value5", "value6", "value7"], nested_tags["null"]["key5"])

    def test_deserialize_nested(self):
        for function in (_deserialize_tags, _deserialize_tags_dict):
            with self.subTest(function=function):
                input_tags = {
                    "namespace1": {"key1": ["value1", "value2"], "key2": ["value3", "value3"]},
                    "namespace2": {"key3": []},
                    "namespace3": {"key4": [None, ""]},
                    "namespace4": {},
                    "": {"key5": ["value4"]},
                    "null": {"key5": ["value5"]},
                }
                deserialized_tags = function(input_tags)

                self.assertCountEqual(
                    ["namespace1", "namespace2", "namespace3", "namespace4", "null"], deserialized_tags.keys()
                )
                self.assertCountEqual(["key1", "key2"], deserialized_tags["namespace1"].keys())
                self.assertCountEqual(["value1", "value2"], deserialized_tags["namespace1"]["key1"])
                self.assertCountEqual(["value3"], deserialized_tags["namespace1"]["key2"])
                self.assertCountEqual(["key3"], deserialized_tags["namespace2"].keys())
                self.assertEqual([], deserialized_tags["namespace2"]["key3"])
                self.assertCountEqual(["key4"], deserialized_tags["namespace3"].keys())
                self.assertEqual([], deserialized_tags["namespace3"]["key4"])
                self.assertEqual({}, deserialized_tags["namespace4"])
                self.assertCountEqual(["key5"], deserialized_tags["null"].keys())
                self.assertCountEqual(["value4", "value5"], deserialized_tags["null"]["key5"])

    def test_deserialize_structured_empty_list(self):
        for function in (_deserialize_tags, _deserialize_tags_list):
            with self.subTest(function=function):
                deserialized_tags = function([])
                self.assertEqual(deserialized_tags, {})

    def test_deserialize_structured_no_key_error(self):
        for function in (_deserialize_tags, _deserialize_tags_list):
            for key in (None, ""):
                with self.subTest(function=function, key=key):
                    with self.assertRaises(ValueError):
                        structured_tags = [{"namespace": "namespace", "key": key, "value": "value"}]
                        function(structured_tags)

    def test_deserialize_nested_empty_dict(self):
        for function in (_deserialize_tags, _deserialize_tags_dict):
            with self.subTest(function=function):
                deserialized_tags = function({})
                self.assertEqual(deserialized_tags, {})

    def test_deserialize_nested_no_key_error(self):
        for function in (_deserialize_tags, _deserialize_tags_dict):
            for key in (None, ""):
                with self.subTest(function=function, key=key):
                    with self.assertRaises(ValueError):
                        nested_tags = {"namespace": {key: ["value"]}}
                        function(nested_tags)


class EventProducerTests(TestCase):
    @patch("app.queue.event_producer.KafkaProducer")
    def setUp(self, mock_kafka_producer):
        super().setUp()

        self.config = Config(RuntimeEnvironment.TEST)
        self.event_producer = EventProducer(self.config, self.config.event_topic)
        self.topic_name = self.config.event_topic
        threadctx.request_id = str(uuid4())
        self.basic_host = {
            "id": str(uuid4()),
            "stale_timestamp": now().isoformat(),
            "reporter": "test_reporter",
            "account": "test",
            "org_id": "test",
            "fqdn": "fqdn",
        }

    def test_happy_path(self):
        produce = self.event_producer._kafka_producer.produce
        poll = self.event_producer._kafka_producer.poll
        host_id = self.basic_host["id"]

        for event_type, host in (
            (EventType.created, self.basic_host),
            (EventType.updated, self.basic_host),
            (EventType.delete, deserialize_host(self.basic_host)),
        ):
            with self.subTest(event_type=event_type):
                event = build_event(event_type, host)
                headers = message_headers(event_type, host_id)

                self.event_producer.write_event(event, host_id, headers)

                produce.assert_called_once_with(
                    self.topic_name,
                    event.encode("utf-8"),
                    host_id.encode("utf-8"),
                    callback=ANY,
                    headers=ANY,
                )
                poll.assert_called_once()

                produce.reset_mock()
                poll.reset_mock()

    def test_producer_poll(self):
        produce = self.event_producer._kafka_producer.produce
        poll = self.event_producer._kafka_producer.poll
        host_id = self.basic_host["id"]

        for event_type, host in (
            (EventType.created, self.basic_host),
            (EventType.updated, self.basic_host),
            (EventType.delete, deserialize_host(self.basic_host)),
        ):
            with self.subTest(event_type=event_type):
                event = build_event(event_type, host)
                headers = message_headers(event_type, host_id)

                self.event_producer.write_event(event, host_id, headers)

                produce.assert_called_once_with(
                    self.topic_name,
                    event.encode("utf-8"),
                    host_id.encode("utf-8"),
                    callback=ANY,
                    headers=ANY,
                )
                poll.assert_called_once()

                produce.reset_mock()
                poll.reset_mock()

    @patch("app.queue.event_producer.message_not_produced")
    def test_kafka_exceptions_are_caught(self, message_not_produced_mock):
        event_type = EventType.created
        event = build_event(event_type, self.basic_host)
        key = self.basic_host["id"]
        headers = message_headers(event_type, self.basic_host["id"])

        kafkex = KafkaException()
        self.event_producer._kafka_producer.produce.side_effect = kafkex

        with self.assertRaises(KafkaException):
            self.event_producer.write_event(event, key, headers)

        # convert headers to a list of tuples as done write_event
        headersTuple = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]

        message_not_produced_mock.assert_called_once_with(
            event_producer_logger,
            kafkex,
            self.config.event_topic,
            event=str(event).encode("utf-8"),
            key=key.encode("utf-8"),
            headers=headersTuple,
        )


class ModelsSystemProfileNormalizerFilterKeysTestCase(TestCase):
    def setUp(self):
        self.normalizer = SystemProfileNormalizer()

    def test_root_keys_are_kept(self):
        original = {"number_of_cpus": 1}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_object_keys_are_kept(self):
        original = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"]}]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_root_keys_are_removed(self):
        payload = {"number_of_cpus": 1, "number_of_gpus": 2}
        self.normalizer.filter_keys(payload)
        expected = {"number_of_cpus": 1}
        self.assertEqual(expected, payload)

    def test_array_items_object_keys_removed(self):
        payload = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"], "mac_addresses": ["aa:bb:cc:dd:ee:ff"]}]}
        self.normalizer.filter_keys(payload)
        expected = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"]}]}
        self.assertEqual(expected, payload)

    def test_root_non_object_keys_without_type_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"] = {"properties": {"number_of_cpus": {"type": "integer"}}}
        payload = {"number_of_gpus": 1}
        original = deepcopy(payload)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_nested_non_object_keys_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
            "properties": {"enable_acpi": {"type": "boolean"}}
        }
        original = {"boot_options": {"safe_mode": False}}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_non_object_keys_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {
            "type": "array",
            "items": {"properties": {"model": {"type": "string"}}},
        }
        original = {"hid_devices": [{"model": "Keyboard 3in1", "manufacturer": "Logitech"}]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_root_object_keys_without_properties_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"] = {"type": "object"}
        payload = {"number_of_cpus": 1}
        original = deepcopy(payload)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_nested_object_keys_without_properties_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {"type": "object"}
        original = {"boot_options": {"enable_acpi": True}}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_object_keys_without_properties_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {
            "type": "array",
            "items": {"type": "object"},
        }
        original = {"hid_devices": [{"model": "Keyboard 3in1", "manufacturer": "Logitech"}]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_nested_object_keys_without_properties_are_kept(self):
        original = {"disk_devices": [{"options": {"uid": "0"}}, {"options": "uid=0"}]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_without_schema_are_kept(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {"type": "array"}
        original = {"hid_devices": [{"model": "Keyboard 3in1"}, "Keyboard 3in1"]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_additional_properties_are_ignored(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["additionalProperties"] = {"type": "integer"}
        payload = {"number_of_gpus": "1"}
        self.normalizer.filter_keys(payload)
        self.assertEqual({}, payload)

    def test_required_properties_are_ignored(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["required"] = ["number_of_gpus"]
        payload = {"number_of_gpus": 1}
        self.normalizer.filter_keys(payload)
        self.assertEqual({}, payload)

    def test_root_invalid_objects_are_ignored(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
            "type": "object",
            "properties": {"enable_acpi": {"type": "boolean"}},
        }
        original = {"boot_options": "enable_acpi=1"}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_invalid_objects_are_ignored(self):
        original = {"network_interfaces": ["eth0"]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_array_items_invalid_nested_objects_are_ignored(self):
        self.normalizer.schema["$defs"]["DiskDevice"]["properties"]["mount_options"] = {
            "type": "object",
            "properties": {"uid": {"type": "integer"}},
        }
        original = {"disk_devices": [{"mount_options": "uid=0"}]}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)

    def test_root_invalid_arrays_are_ignored(self):
        self.normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
            "type": "array",
            "items": {"type": "string"},
        }
        original = {"boot_options": "enable_acpi=1"}
        payload = deepcopy(original)
        self.normalizer.filter_keys(payload)
        self.assertEqual(original, payload)


class ModelsSystemProfileTestCase(TestCase):
    def _payload(self, system_profile):
        return {
            "account": "0000001",
            "org_id": "3340851",
            "system_profile": system_profile,
            "stale_timestamp": now().isoformat(),
            "reporter": "test",
        }

    def _assert_system_profile_is_invalid(self, load_result):
        self.assertIn("system_profile", load_result)
        self.assertTrue(
            any("System profile does not conform to schema." in message for message in load_result["system_profile"])
        )

    def test_invalid_values_are_rejected(self):
        schema = HostSchema()
        for system_profile in INVALID_SYSTEM_PROFILES:
            with self.subTest(system_profile=system_profile):
                payload = self._payload(system_profile)
                result = schema.validate(payload)
                self._assert_system_profile_is_invalid(result)

    def test_specification_file_is_used(self):
        payload = self._payload({"number_of_cpus": 1})

        orig_spec = system_profile_specification()
        mock_spec = deepcopy(orig_spec)
        mock_spec["$defs"]["SystemProfile"]["properties"]["number_of_cpus"]["minimum"] = 2

        with mock_system_profile_specification(mock_spec):
            schema = HostSchema()
            result = schema.validate(payload)
            self._assert_system_profile_is_invalid(result)

    def test_types_are_coerced(self):
        payload = self._payload({"number_of_cpus": "1"})
        schema = HostSchema()
        result = schema.load(payload)
        self.assertEqual({"number_of_cpus": 1}, result["system_profile"])

    def test_fields_are_filtered(self):
        payload = self._payload(
            {
                "number_of_cpus": 1,
                "number_of_gpus": 2,
                "network_interfaces": [{"ipv4_addresses": ["10.10.10.1"], "mac_addresses": ["aa:bb:cc:dd:ee:ff"]}],
            }
        )
        schema = HostSchema()
        result = schema.load(payload)
        expected = {"number_of_cpus": 1, "network_interfaces": [{"ipv4_addresses": ["10.10.10.1"]}]}
        self.assertEqual(expected, result["system_profile"])

    @patch("app.models.jsonschema_validate")
    def test_type_coercion_happens_before_loading(self, jsonschema_validate):
        schema = HostSchema()
        payload = self._payload({"number_of_cpus": "1"})
        schema.load(payload)
        jsonschema_validate.assert_called_once_with(
            {"number_of_cpus": 1}, HostSchema.system_profile_normalizer.schema, format_checker=ANY
        )

    @patch("app.models.jsonschema_validate")
    def test_type_filtering_happens_after_loading(self, jsonschema_validate):
        schema = HostSchema()
        payload = self._payload({"number_of_gpus": 1})
        result = schema.load(payload)
        jsonschema_validate.assert_called_once_with(
            {"number_of_gpus": 1}, HostSchema.system_profile_normalizer.schema, format_checker=ANY
        )
        self.assertEqual({}, result["system_profile"])


class QueryParameterParsingTestCase(TestCase):
    def test_custom_fields_parser(self):
        for parser_input, output in (
            (("fields", ["foo"], ["bar"]), [{"foo": {"bar": True}}]),
            (("fields", ["foo"], ["bar,hello"]), [{"foo": {"bar": True, "hello": True}}]),
            (("fields", ["foo"], ["bar", "hello"]), [{"foo": {"bar": True, "hello": True}}]),
            (
                ("anything", ["profile"], ["bar,hello", "baz"]),
                [{"profile": {"bar": True, "hello": True, "baz": True}}],
            ),
            (
                ("fields", ["system_profile"], ["os_version,arch,yum_repos"]),
                [{"system_profile": {"os_version": True, "arch": True, "yum_repos": True}}],
            ),
        ):
            root_key, response, is_deep_object = custom_fields_parser(*parser_input)
            assert root_key == parser_input[0]
            assert response == output
            assert is_deep_object is True

    def test_valid_deep_object_list(self):
        for key, value in (("asdf[foo]", ["bar"]), ("system_profile[field1][field2]", ["value1"])):
            _, _, is_deep_object = customURIParser._make_deep_object(key, value)
            assert is_deep_object

    def test_invalid_deep_object_list(self):
        for key, value in (
            ("asdf[foo]", ["bar", "baz"]),
            ("system_profile[field1][field2]", ["value1", "value2", "value3"]),
        ):
            with self.assertRaises(ValidationException):
                customURIParser._make_deep_object(key, value)


class CustomRegexMethodTestCase(TestCase):
    def test_custom_regex_escape(self):
        for regex_input, output in (
            (".?well+", "\\.\\?well\\+"),
            ("&[^abc]~", "\\&\\[^abc\\]\\~"),
            ("some|*#thing", "some\\|\\*\\#thing"),
            ('.?+*|{}[]()"\\#@&<>~', '\\.\\?\\+\\*\\|\\{\\}\\[\\]\\(\\)\\"\\\\\\#\\@\\&\\<\\>\\~'),
            ("\\", "\\\\"),
        ):
            with self.subTest(regex_input=regex_input):
                result = custom_escape(regex_input)
                assert result == output


class KafkaAvailabilityTests(TestCase):
    def setUp(self):
        super().setUp()
        self.config = Config(RuntimeEnvironment.TEST)

    @patch("socket.socket.connect_ex")
    def test_happy_path(self, connect_ex):
        connect_ex.return_value = 0
        assert host_kafka.kafka_available()
        connect_ex.assert_called_once()

    @patch("socket.socket.connect_ex")
    def test_valid_server(self, connect_ex):
        connect_ex.return_value = 0
        akafka = [self.config.bootstrap_servers]
        assert host_kafka.kafka_available(akafka)
        connect_ex.assert_called_once()

    @patch("socket.socket.connect_ex")
    def test_list_of_valid_servers(self, connect_ex):
        connect_ex.return_value = 0
        kafka_servers = ["127.0.0.1:29092", "localhost:29092"]
        assert host_kafka.kafka_available(kafka_servers)
        connect_ex.assert_called_once()

    @patch("socket.socket.connect_ex")
    def test_list_with_first_bad_second_good_server(self, connect_ex):
        connect_ex.return_value = 0
        kafka_servers = ["localhost29092", "127.0.0.1:29092"]
        assert host_kafka.kafka_available(kafka_servers)
        connect_ex.assert_called_once()

    @patch("socket.socket.connect_ex")
    def test_list_with_first_good_second_bad_server(self, connect_ex):
        # second bad with missing ':'.  Returns as soon as the first kafka server found.
        connect_ex.return_value = 0
        kafka_servers = ["localhost:29092", "127.0.0.129092"]
        assert host_kafka.kafka_available(kafka_servers)
        connect_ex.assert_called_once()

    @patch("socket.socket.connect_ex")
    def test_invalid_kafka_server(self, connect_ex):
        kafka_servers = ["localhos.129092"]
        assert host_kafka.kafka_available(kafka_servers) is None
        connect_ex.assert_not_called()

    @patch("socket.socket.connect_ex")
    def test_bogus_kafka_server(self, connect_ex):
        kafka_servers = ["bogus-kafka29092"]
        assert host_kafka.kafka_available(kafka_servers) is None
        connect_ex.assert_not_called()

    @patch("socket.socket.connect_ex")
    def test_wrong_kafka_server_post(self, connect_ex):
        connect_ex.return_value = 61
        kafka_servers = ["localhost:54321"]
        assert host_kafka.kafka_available(kafka_servers) is None
        connect_ex.assert_called_once()


if __name__ == "__main__":
    main()
