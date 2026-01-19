#!/usr/bin/env python
from base64 import b64encode
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from json import dumps
from random import choice
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

import pytest
from confluent_kafka import KafkaException
from connexion.exceptions import BadRequestProblem
from marshmallow import ValidationError

from api import api_operation
from api import custom_escape
from api.host_query import staleness_timestamps
from api.host_query_db import _order_how
from api.host_query_db import params_to_order_by
from api.parsing import custom_fields_parser
from api.parsing import customURIParser
from app import SPECIFICATION_FILE
from app import create_app
from app.auth.identity import SHARED_SECRET_ENV_VAR
from app.auth.identity import Identity
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.config import DEFAULT_INSIGHTS_ID
from app.config import Config
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.culling import Timestamps
from app.culling import _Config as CullingConfig
from app.environment import RuntimeEnvironment
from app.exceptions import InputFormatException
from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import Host
from app.models import HostSchema
from app.models import SystemProfileNormalizer
from app.queue.event_producer import EventProducer
from app.queue.event_producer import logger as event_producer_logger
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import _deserialize_canonical_facts
from app.serialization import _deserialize_facts
from app.serialization import _deserialize_tags
from app.serialization import _deserialize_tags_dict
from app.serialization import _deserialize_tags_list
from app.serialization import _serialize_datetime
from app.serialization import deserialize_canonical_facts
from app.serialization import deserialize_host
from app.serialization import serialize_canonical_facts
from app.serialization import serialize_facts
from app.serialization import serialize_host
from app.serialization import serialize_host_system_profile
from app.serialization import serialize_uuid
from app.staleness_serialization import get_sys_default_staleness
from app.utils import Tag
from lib import host_kafka
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment


@patch("api.segmentio_track")
@patch("api.api_request_count.inc")
def test_counter_is_incremented(inc, _segmentio_track):
    """
    Test the API operation decorator that increments the request counter with every
    call.
    """

    @api_operation
    def func():
        pass

    func()
    inc.assert_called_once_with()


@patch("api.segmentio_track")
def test_arguments_are_passed(_segmentio_track):
    old_func = Mock()
    old_func.__name__ = "old_func"
    new_func = api_operation(old_func)

    args = (Mock(),)
    kwargs = {"some_arg": Mock()}

    new_func(*args, **kwargs)
    old_func.assert_called_once_with(*args, **kwargs)


@patch("api.segmentio_track")
def test_return_value_is_passed(_segmentio_track):
    old_func = Mock()
    old_func.__name__ = "old_func"
    new_func = api_operation(old_func)
    assert old_func.return_value == new_func()


@patch("api.segmentio_track")
def test_segmentio_track_called(segmentio_track):
    @api_operation
    def func():
        pass

    func()
    segmentio_track.assert_called()


def _identity():
    """
    Helper function for Identity module constructors.
    """
    return Identity(USER_IDENTITY)


def test_valid_auth_identity_from_auth_header(subtests):
    """
    Tests creating an Identity from a Base64 encoded JSON string, which is what is in
    the HTTP header.
    Initialize the Identity object with an encoded payload – a base64-encoded JSON.
    That would typically be a raw HTTP header content.
    """
    expected_identity = _identity()

    identity_data = expected_identity._asdict()

    identity_data_dicts = [
        identity_data,
        # Test with extra data in the identity dict
        {**identity_data, **{"extra_data": "value"}},
    ]

    for identity_data in identity_data_dicts:
        with subtests.test(identity_data=identity_data):
            identity = {"identity": identity_data}
            json = dumps(identity)
            base64 = b64encode(json.encode())

            actual_identity = from_auth_header(base64)
            assert expected_identity.__dict__ == actual_identity.__dict__
            assert actual_identity.is_trusted_system is False


def test_invalid_type_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an invalid type that can't be a Base64
    encoded payload should raise a TypeError.
    """
    with pytest.raises(TypeError):
        from_auth_header(["not", "a", "string"])


def test_invalid_value_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an invalid Base6č encoded payload should
    raise a ValueError.
    """
    with pytest.raises(ValueError):
        from_auth_header("invalid Base64")


def test_invalid_format_auth_identity_from_auth_header():
    """
    Initializing the Identity object with an valid Base64 encoded payload
    that does not contain the "identity" field.
    """
    identity = _identity()

    dict_ = identity._asdict()
    json = dumps(dict_)
    base64 = b64encode(json.encode())

    with pytest.raises(KeyError):
        from_auth_header(base64)


def test_valid_auth_identity_validate():
    Identity(USER_IDENTITY)


def test_invalid_org_id_auth_identity_validate(subtests):
    test_identity = deepcopy(USER_IDENTITY)
    org_ids = [None, ""]
    for org_id in org_ids:
        with subtests.test(org_id=org_id):
            test_identity["org_id"] = org_id
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_type_auth_identity_validate(subtests):
    test_identity = deepcopy(USER_IDENTITY)
    identity_types = [None, ""]
    for identity_type in identity_types:
        with subtests.test(identity_type=identity_type):
            test_identity["type"] = identity_type
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_system_obj_auth_identity_validate(subtests):
    test_identity = deepcopy(SYSTEM_IDENTITY)
    system_objects = [None, ""]
    for system_object in system_objects:
        with subtests.test(system_object=system_object):
            test_identity["system"] = system_object
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_service_account_obj_auth_identity_validate(subtests):
    test_identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    service_account_objects = [
        None,
        "",
        {
            "client_id": SERVICE_ACCOUNT_IDENTITY["service_account"]["client_id"],
            "username": "",
        },
        {"client_id": "", "username": SERVICE_ACCOUNT_IDENTITY["service_account"]["username"]},
    ]
    for service_account_object in service_account_objects:
        with subtests.test(service_account_object=service_account_object):
            test_identity["service_account"] = service_account_object
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_invalid_auth_types_auth_identity_validate(subtests):
    test_identities = [deepcopy(USER_IDENTITY), deepcopy(SYSTEM_IDENTITY), deepcopy(SERVICE_ACCOUNT_IDENTITY)]
    auth_types = ["", "foo"]
    for test_identity in test_identities:
        for auth_type in auth_types:
            with subtests.test(auth_type=auth_type):
                test_identity["auth_type"] = auth_type
                with pytest.raises(ValueError):
                    Identity(test_identity)


def test_invalid_cert_types_auth_identity_validate(subtests):
    test_identity = deepcopy(SYSTEM_IDENTITY)
    cert_types = [None, "", "foo"]
    for cert_type in cert_types:
        with subtests.test(cert_type=cert_type):
            test_identity["system"]["cert_type"] = cert_type
            with pytest.raises(ValueError):
                Identity(test_identity)


def test_case_insensitive_cert_types_auth_identity_validate(subtests):
    # Validate that cert_type is case-insensitive
    test_identity = deepcopy(SYSTEM_IDENTITY)
    cert_types = ["RHUI", "Satellite", "system"]
    for cert_type in cert_types:
        with subtests.test(cert_type=cert_type):
            test_identity["system"]["cert_type"] = cert_type
            Identity(test_identity)


def test_case_insensitive_auth_types_auth_identity_validate(subtests):
    # Validate that auth_type is case-insensitive
    test_identity = deepcopy(SYSTEM_IDENTITY)
    auth_types = ["JWT-AUTH", "Cert-Auth", "basic-auth"]
    for auth_type in auth_types:
        with subtests.test(auth_type=auth_type):
            test_identity["auth_type"] = auth_type
            Identity(test_identity)


def test_obsolete_auth_type_auth_identity_validate():
    # Validate that removed auth_type not working anymore
    test_identity = deepcopy(SYSTEM_IDENTITY)
    test_identity["auth_type"] = "CLASSIC-PROXY"
    with pytest.raises(ValueError):
        Identity(test_identity)


def test_missing_auth_type_auth_identity_validate():
    # auth_type must be provided
    test_identity = deepcopy(SYSTEM_IDENTITY)
    test_identity["auth_type"] = None
    with pytest.raises(ValueError):
        Identity(test_identity)


SHARED_SECRET = "ImaSecret"


def _build_id(shared_secret):
    identity = from_bearer_token(shared_secret)
    return identity


def test_validation_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        _build_id(SHARED_SECRET)


def test_validation_with_invalid_identity_trusted_identity():
    with pytest.raises(ValueError):
        from_bearer_token("InvalidPassword")


def test_validation_env_var_not_set_trusted_identity():
    with set_environment({}):
        with pytest.raises(ValueError):
            _build_id(SHARED_SECRET)


def test_validation_token_is_None_trusted_identity(subtests):
    tokens = [None, ""]
    for token in tokens:
        with subtests.test(token_value=token):
            with pytest.raises(ValueError):
                Identity(token=token)


def test_is_trusted_system_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        identity = _build_id(SHARED_SECRET)

    assert identity.is_trusted_system is True


def test_org_id_is_not_set_for_trusted_system_trusted_identity():
    with set_environment({SHARED_SECRET_ENV_VAR: SHARED_SECRET}):
        identity = _build_id(SHARED_SECRET)

    assert not hasattr(identity, "org_id")


def _config():
    return Config(RuntimeEnvironment.SERVER)


def test_configuration_with_env_vars():
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
        conf = _config()

    assert conf.db_uri == "postgresql://fredflintstone:bedrock1234@localhost:5432/SlateRockAndGravel"
    assert conf.db_pool_timeout == 3
    assert conf.db_pool_size == 8
    assert conf.api_url_path_prefix == expected_api_path
    assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix
    assert conf.culling_stale_warning_offset_delta == timedelta(days=culling_stale_warning_offset_days)
    assert conf.culling_culled_offset_delta == timedelta(days=culling_culled_offset_days)


def test_config_default_settings():
    expected_api_path = "/api/inventory/v1"
    expected_mgmt_url_path_prefix = "/"

    # Make sure the runtime_environment variables are not set
    with set_environment(None):
        conf = _config()

    assert conf.db_uri == "postgresql://insights:insights@localhost:5432/insights"
    assert conf.api_url_path_prefix == expected_api_path
    assert conf.mgmt_url_path_prefix == expected_mgmt_url_path_prefix
    assert conf.db_pool_timeout == 5
    assert conf.db_pool_size == 5
    assert conf.culling_stale_warning_offset_delta == timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
    assert conf.culling_culled_offset_delta == timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)


def test_config_development_settings():
    with set_environment({"INVENTORY_DB_POOL_TIMEOUT": "3"}):
        conf = _config()

    assert conf.db_pool_timeout == 3


def test_kafka_produducer_acks(subtests):
    for value in (0, 1, "all"):
        with subtests.test(value=value):
            with set_environment({"KAFKA_PRODUCER_ACKS": f"{value}"}):
                assert _config().kafka_producer["acks"] == value


def test_kafka_producer_acks_unknown():
    with set_environment({"KAFKA_PRODUCER_ACKS": "2"}):
        with pytest.raises(ValueError):
            _config()


def test_kafka_producer_int_params(subtests):
    for param in (
        "retries",
        "batch.size",
        "linger.ms",
        "retry.backoff.ms",
        "max.in.flight.requests.per.connection",
    ):
        with subtests.test(param=param):
            with set_environment({f"KAFKA_PRODUCER_{param.upper()}": "2020"}):
                assert _config().kafka_producer[param] == 2020


def test_kafka_producer_int_params_invalid(subtests):
    for param in (
        "retries",
        "batch.size",
        "linger.ms",
        "retry.backoff.ms",
        "max.in.flight.requests.per.connection",
    ):
        with subtests.test(param=param):
            with set_environment({f"KAFKA_PRODUCER_{param.upper()}": "abc"}):
                with pytest.raises(ValueError):
                    _config()


def test_kafka_producer_defaults(subtests):
    config = _config()

    for param, expected_value in (
        ("acks", 1),
        ("retries", 0),
        ("batch.size", 65536),
        ("linger.ms", 0),
        ("retry.backoff.ms", 100),
        ("max.in.flight.requests.per.connection", 5),
    ):
        with subtests.test(param=param):
            assert config.kafka_producer[param] == expected_value


@patch(  # type: ignore [call-overload]
    "app.Config",
    **{
        "return_value.mgmt_url_path_prefix": "/",
        "return_value.unleash_token": "",
        "return_value.api_cache_max_thread_pool_workers": 5,
    },
)
def test_config_is_assigned_create_app_config(config):
    with patch("app.db.init_app"), patch("app.init_kessel"):
        application = create_app(RuntimeEnvironment.TEST)
    assert "INVENTORY_CONFIG" in application.app.config
    assert config.return_value == application.app.config["INVENTORY_CONFIG"]


@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
@patch("app.TranslatingParser")
def test_specification_is_provided_create_app_connexion(translating_parser, _init_app, app):
    create_app(RuntimeEnvironment.TEST)

    translating_parser.assert_called_once_with(SPECIFICATION_FILE)
    assert "lazy" not in translating_parser.mock_calls[0].kwargs

    assert app.return_value.add_api.call_count == 2
    args = app.return_value.add_api.mock_calls[0].args
    assert len(args) == 1
    assert args[0] is translating_parser.return_value.specification


@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
def test_specification_is_parsed_create_app_connexion(_init_app, app):
    create_app(RuntimeEnvironment.TEST)
    assert app.return_value.add_api.call_count == 2
    args = app.return_value.add_api.mock_calls[0].args
    assert len(args) == 1
    assert args[0] is not None


@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
def test_translatingparser_create_app_connexion(_init_app, app):
    # Test here the parsing is working with the referenced schemas from system_profile.spec.yaml
    # and the check parser.specification["components"]["schemas"] - this is more a library test
    create_app(RuntimeEnvironment.TEST)
    # Check whether SystemProfileNetworkInterface is inside the schemas section
    # add_api uses the specification as firts argument
    specification = app.return_value.add_api.mock_calls[0].args
    assert "SystemProfileNetworkInterface" in specification[0]["components"]["schemas"]

    # This will pass with openapi.json because the schemas are inlined
    # This will pass when the library acts as it should, inlining the referenced schemas


@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
@patch("app.SPECIFICATION_FILE", value="./swagger/api.spec.yaml")
def test_yaml_specification_create_app_connexion(_translating_parser, _init_app, _app):
    # Create an app with bad defs assert that it won't create and will raise an exception
    with patch("app.create_app", side_effect=Exception("mocked error")):
        with pytest.raises(Exception):  # noqa: B017
            create_app(RuntimeEnvironment.TEST)


def test_asc_host_order_how():
    column = Mock()
    result = _order_how(column, "ASC")
    assert result == column.asc()


def test_desc_host_order_how():
    column = Mock()
    result = _order_how(column, "DESC")
    assert result == column.desc()


def test_error_host_order_how(subtests):
    invalid_values = (None, "asc", "desc", "BBQ")
    for invalid_value in invalid_values:
        with subtests.test(order_how=invalid_value):
            with pytest.raises(ValueError):
                _order_how(Mock(), invalid_value)


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_default_is_updated_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by(None, None)
    expected = (modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_default_for_updated_is_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", None)
    expected = (modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_order_by_updated_asc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", "ASC")
    expected = (order_how.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(modified_on, "ASC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
def test_order_by_updated_desc_host_params_to_order_by(modified_on, id_, order_how):
    actual = params_to_order_by("updated", "DESC")
    expected = (order_how.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(modified_on, "DESC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_default_for_display_name_is_asc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name")
    expected = (display_name.asc.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_not_called()


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_order_by_display_name_asc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name", "ASC")
    expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(display_name, "ASC")


@patch("api.host_query_db._order_how")
@patch("api.host.Host.id")
@patch("api.host.Host.modified_on")
@patch("api.host.Host.display_name")
def test_order_by_display_name_desc_host_params_to_order_by(display_name, modified_on, id_, order_how):
    actual = params_to_order_by("display_name", "DESC")
    expected = (order_how.return_value, modified_on.desc.return_value, id_.desc.return_value)
    assert actual == expected
    order_how.assert_called_once_with(display_name, "DESC")


def test_order_by_bad_field_raises_error_host_params_to_order_by():
    with pytest.raises(ValueError):
        params_to_order_by(Mock(), "fqdn")


def test_order_by_only_how_raises_error_host_params_to_order_by():
    with pytest.raises(ValueError):
        params_to_order_by(Mock(), order_how="ASC")


def test_all_parts_tag_from_string():
    assert Tag.from_string("NS/key=value") == Tag("NS", "key", "value")


def test_no_namespace_tag_from_string():
    assert Tag.from_string("key=value") == Tag(None, "key", "value")


def test_no_value_tag_from_string():
    assert Tag.from_string("NS/key") == Tag("NS", "key", None)


def test_only_key_tag_from_string():
    assert Tag.from_string("key") == Tag(None, "key", None)


def test_special_characters_decode_tag_from_string():
    assert Tag.from_string("Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal") == Tag(
        "Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al"
    )


def test_special_characters_allowed_tag_from_string():
    special_characters = ";,?:@&+$-_.!~*'()#"
    assert Tag.from_string(f"{special_characters}/{special_characters}={special_characters}") == Tag(
        special_characters, special_characters, special_characters
    )


def test_delimiters_tag_from_string():
    decoded = "a/b=c"
    encoded = "a%2Fb%3Dc"
    assert Tag.from_string(f"{encoded}/{encoded}={encoded}") == Tag(decoded, decoded, decoded)


def test_encoded_too_long_tag_from_string():
    decoded = "!" * 86
    encoded = "%21" * 86
    assert Tag.from_string(f"{encoded}/{encoded}={encoded}") == Tag(decoded, decoded, decoded)


def test_decoded_too_long_tag_from_string(subtests):
    too_long = "a" * 256
    for string_tag in (f"{too_long}/a=a", f"a/{too_long}=a", f"a/a={too_long}"):
        with subtests.test(string_tag=string_tag):
            with pytest.raises(ValidationException):
                Tag.from_string(f"{too_long}/{too_long}={too_long}")


def test_all_parts_tag_to_string():
    assert Tag("NS", "key", "value").to_string() == "NS/key=value"


def test_no_value_tag_to_string():
    assert Tag("namespace", "key").to_string() == "namespace/key"


def test_no_namespace_tag_to_string():
    assert Tag(key="key", value="value").to_string() == "key=value"


def test_only_key_tag_to_string():
    assert Tag(key="key").to_string() == "key"


def test_special_characters_tag_to_string():
    assert (
        Tag("Ns!@#$%^&()", "k/e=y\\", r"v:|\{\}''-+al").to_string()
        == "Ns%21%40%23%24%25%5E%26%28%29/k%2Fe%3Dy%5C=v%3A%7C%5C%7B%5C%7D%27%27-%2Bal"
    )


def test_all_parts_tag_from_nested():
    assert Tag.from_nested({"NS": {"key": ["value"]}}) == Tag("NS", "key", "value")


def test_no_value_tag_from_nested():
    assert Tag.from_nested({"NS": {"key": []}}) == Tag("NS", "key")


def test_all_parts_tag_to_nested():
    assert Tag("NS", "key", "value").to_nested() == {"NS": {"key": ["value"]}}


def test_no_value_tag_to_nested():
    assert Tag("NS", "key").to_nested() == {"NS": {"key": []}}


def _base_structured_to_filtered_test(structured_tags, expected_filtered_structured_tags, searchTerm):
    flat_tags = Tag.create_flat_tags_from_structured(structured_tags)
    expected_filtered_flat_tags = Tag.create_flat_tags_from_structured(expected_filtered_structured_tags)
    filtered_tags = Tag.filter_tags(flat_tags, searchTerm)
    assert len(filtered_tags) == len(expected_filtered_flat_tags)

    for i in range(len(filtered_tags)):
        assert filtered_tags[i]["namespace"] == expected_filtered_flat_tags[i]["namespace"]
        assert filtered_tags[i]["key"] == expected_filtered_flat_tags[i]["key"]
        assert filtered_tags[i]["value"] == expected_filtered_flat_tags[i]["value"]


def test_simple_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key", "val"), Tag(None, "key", "something"), Tag("NS2", "key2")]
    expected_filtered_tags = [Tag("NS1", "key", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_empty_tags_tag_filter_tags():
    structured_tags = []
    expected_filtered_tags = []

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_search_matches_namesapce_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "NS1")


def test_search_matches_tag_key_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "key1")


def test_complex_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "Value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "Value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "vA")


def test_empty_filter_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "")


def test_space_tag_filter_tags():
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = []

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, " ")


def test_search_prefix_tag_filter_tags():
    # namespace
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "N")

    # key
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "K")

    # value
    structured_tags = [
        Tag("NS1", "key1", "val"),
        Tag(None),
        Tag("NS2", "Key2", "something"),
        Tag("NS3", "key3", "value3"),
    ]
    expected_filtered_tags = [Tag("NS1", "key1", "val"), Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "val")


def test_search_suffix_tag_filter_tags():
    # namespace
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS1", "key1", "val")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "S1")

    # key
    structured_tags = [Tag("NS1", "key1", "val"), Tag(None), Tag("NS2", "Key2"), Tag("NS3", "key3", "value3")]
    expected_filtered_tags = [Tag("NS2", "Key2")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "y2")

    # value
    structured_tags = [
        Tag("NS1", "key1", "val"),
        Tag(None),
        Tag("NS2", "Key2", "something"),
        Tag("NS3", "key3", "value3"),
    ]
    expected_filtered_tags = [Tag("NS3", "key3", "value3")]

    _base_structured_to_filtered_test(structured_tags, expected_filtered_tags, "ue3")


def test_create_nested_combined_tag_create_nested_from_tags():
    tags = [Tag("NS1", "Key", "val"), Tag("NS2", "k2")]

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {"NS1": {"Key": ["val"]}, "NS2": {"k2": []}}

    assert nested_tags == expected_nested_tags


def test_create_nested_single_no_value_tag_create_nested_from_tags():
    tags = [Tag("NS2", "k2")]

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {"NS2": {"k2": []}}

    assert nested_tags == expected_nested_tags


def test_create_nested_from_tags_no_tags_tag_create_nested_from_tags():
    tags = []

    nested_tags = Tag.create_nested_from_tags(tags)

    expected_nested_tags = {}

    assert nested_tags == expected_nested_tags


# SerializationDeserializeHostCompoundTestCase converted to functions below
def test_with_all_fields(flask_app):
    with flask_app.app.app_context():
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
            **canonical_facts,
            **unchanged_input,
            "facts": {item["namespace"]: item["facts"] for item in full_input["facts"]},
            "system_profile_facts": full_input["system_profile"],
        }

        assert Host is type(actual)
        for key, value in expected.items():
            assert value == getattr(actual, key)


def test_with_only_required_fields_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        org_id = "some org_id"
        stale_timestamp = now()
        reporter = "puptoo"
        canonical_facts = {"subscription_manager_id": generate_uuid()}

        with subtests.test(schema=HostSchema):
            host = deserialize_host(
                {
                    "org_id": org_id,
                    "stale_timestamp": stale_timestamp.isoformat(),
                    "reporter": reporter,
                    **canonical_facts,
                }
            )

            assert Host is type(host)
            serialized_canonical = serialize_canonical_facts(host)
            for key, value in canonical_facts.items():
                assert value == serialized_canonical.get(key)
            assert host.display_name is None
            assert host.ansible_host is None
            assert org_id == host.org_id
            assert reporter == host.reporter
            assert host.facts == {}
            assert host.tags == {}
            assert host.system_profile_facts == {}


def test_with_invalid_input_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
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
            with subtests.test(input=inp):
                with pytest.raises(ValidationException) as context:
                    deserialize_host(inp)

                    expected_errors = HostSchema().validate(inp)
                    assert str(expected_errors) == str(context.value)


# Test that both of the host schemas will pass all of these fields
# needed because HTTP schema does not accept tags anymore (RHCLOUD - 5593)
def test_with_all_common_fields_serialization_deserialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
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

        with subtests.test(schema=HostSchema):
            actual = deserialize_host(full_input)
            expected = {
                **canonical_facts,
                **unchanged_input,
                "facts": {item["namespace"]: item["facts"] for item in full_input["facts"]},
                "system_profile_facts": full_input["system_profile"],
            }

            assert Host is type(actual)
            for key, value in expected.items():
                assert value == getattr(actual, key)


def test_with_tags_serialization_deserialize_host_compound(flask_app):
    with flask_app.app.app_context():
        tags = {
            "some namespace": {"some key": ["some value", "another value"], "another key": ["value"]},
            "another namespace": {"key": ["value"]},
        }
        host = deserialize_host(
            {
                "org_id": "3340851",
                "stale_timestamp": now().isoformat(),
                "reporter": "puptoo",
                "subscription_manager_id": generate_uuid(),
                "tags": tags,
            }
        )

        assert Host is type(host)
        assert tags == host.tags


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_with_all_fields_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})
        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_facts_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(None)
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_tags_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(None)
        host.assert_called_once_with(
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_display_name_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            None,
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_system_profile_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            {},
            host_input["stale_timestamp"],
            host_input["reporter"],
            host_input["groups"],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_without_groups_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_schema = Mock(**{"return_value.load.return_value": host_input, "build_model": HostSchema.build_model})

        result = deserialize_host({}, host_schema)
        assert host.return_value == result

        deserialize_canonical_facts.assert_called_once_with(host_input)
        deserialize_facts.assert_called_once_with(host_input["facts"])
        deserialize_tags.assert_called_once_with(host_input["tags"])
        host.assert_called_once_with(
            host_input["display_name"],
            host_input["ansible_host"],
            host_input["account"],
            host_input["org_id"],
            deserialize_facts.return_value,
            deserialize_tags.return_value,
            [],
            host_input["system_profile"],
            host_input["stale_timestamp"],
            host_input["reporter"],
            [],
            insights_id=host_input.get("insights_id"),
            subscription_manager_id=host_input.get("subscription_manager_id"),
            satellite_id=host_input.get("satellite_id"),
            fqdn=host_input.get("fqdn"),
            bios_uuid=host_input.get("bios_uuid"),
            ip_addresses=host_input.get("ip_addresses"),
            mac_addresses=host_input.get("mac_addresses"),
            provider_id=host_input.get("provider_id"),
            provider_type=host_input.get("provider_type"),
            openshift_cluster_id=host_input["openshift_cluster_id"],
        )


@patch("app.models.schemas.Host")
@patch("app.serialization._deserialize_tags")
@patch("app.serialization._deserialize_facts")
@patch("app.serialization._deserialize_canonical_facts")
def test_invalid_host_error_serialization_deserialize_host_mocked(
    deserialize_canonical_facts, deserialize_facts, deserialize_tags, host, flask_app
):
    with flask_app.app.app_context():
        data = {"field_1": "data_1"}
        messages = {"field_1": "Invalid value.", "field_2": "Missing required field."}
        caught_exception = ValidationError(messages)
        caught_exception.data = data
        host_schema = Mock(**{"return_value.load.side_effect": caught_exception})

        with pytest.raises(ValidationException) as raises_context:
            deserialize_host({}, host_schema)

        raised_exception = raises_context.value

        assert str(caught_exception.messages) in str(raised_exception)

        deserialize_canonical_facts.assert_not_called()
        deserialize_facts.assert_not_called()
        deserialize_tags.assert_not_called()
        host.assert_not_called()

        host_schema.return_value.load.return_value.get.assert_not_called()


def _timestamp_to_str(timestamp):
    return timestamp.astimezone(UTC).isoformat()


# SerializationSerializeHostCompoundTestCase converted to functions below
def _add_seconds(stale_timestamp, seconds):
    return stale_timestamp + timedelta(seconds=seconds)


def test_with_all_fields_serialization_serialize_host_compound(flask_app):
    with flask_app.app.app_context():
        canonical_facts = {
            "insights_id": generate_uuid(),
            "subscription_manager_id": generate_uuid(),
            "satellite_id": generate_uuid(),
            "bios_uuid": generate_uuid(),
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_init_data = {
            **canonical_facts,
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
            "last_check_in": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        config = CullingConfig(stale_warning_offset_delta=timedelta(days=7), culled_offset_delta=timedelta(days=14))
        staleness = get_sys_default_staleness()
        actual = serialize_host(host, Timestamps(config), False, ("tags",), staleness=staleness)

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
            "created": _timestamp_to_str(host_attr_data["created_on"]),
            "updated": _timestamp_to_str(host_attr_data["modified_on"]),
            "last_check_in": _timestamp_to_str(host_attr_data["last_check_in"]),
            "stale_timestamp": _timestamp_to_str(
                _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_SECONDS)
            ),
            "stale_warning_timestamp": _timestamp_to_str(
                _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ),
            "culled_timestamp": _timestamp_to_str(
                _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ),
            "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
        }
        expected["insights_id"] = str(expected["insights_id"])
        expected["subscription_manager_id"] = str(expected["subscription_manager_id"])
        expected["satellite_id"] = str(expected["satellite_id"])
        expected["bios_uuid"] = str(expected["bios_uuid"])

        assert expected == actual


def test_with_only_required_fields_serialization_serialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        for group_data in ({"groups": None}, {"groups": []}, {}):
            with subtests.test(group_data=group_data):
                unchanged_data = {
                    "display_name": None,
                    "org_id": "some org_id",
                    "account": None,
                    "reporter": "yupana",
                }
                host_init_data = {
                    "stale_timestamp": now(),
                    "subscription_manager_id": generate_uuid(),
                    **unchanged_data,
                    "facts": {},
                }
                host = Host(**host_init_data)

                host_attr_data = {
                    "id": uuid4(),
                    "created_on": now(),
                    "modified_on": now(),
                    "last_check_in": now(),
                    "per_reporter_staleness": host.per_reporter_staleness,
                    **group_data,
                }
                for k, v in host_attr_data.items():
                    setattr(host, k, v)

                staleness_offset = staleness_timestamps()
                staleness = get_sys_default_staleness()
                actual = serialize_host(host, staleness_offset, False, ("tags",), staleness=staleness)
                expected = {
                    "insights_id": DEFAULT_INSIGHTS_ID,
                    "fqdn": None,
                    "satellite_id": None,
                    "bios_uuid": None,
                    "ip_addresses": None,
                    "mac_addresses": None,
                    "ansible_host": None,
                    "provider_id": None,
                    "provider_type": None,
                    "openshift_cluster_id": None,
                    "subscription_manager_id": str(host_init_data.get("subscription_manager_id")),
                    **unchanged_data,
                    "facts": [],
                    "groups": [],
                    "tags": [],
                    "id": str(host_attr_data["id"]),
                    "created": _timestamp_to_str(host_attr_data["created_on"]),
                    "updated": _timestamp_to_str(host_attr_data["modified_on"]),
                    "last_check_in": _timestamp_to_str(host_attr_data["last_check_in"]),
                    "stale_timestamp": _timestamp_to_str(
                        _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_SECONDS)
                    ),
                    "stale_warning_timestamp": _timestamp_to_str(
                        _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
                    ),
                    "culled_timestamp": _timestamp_to_str(
                        _add_seconds(host_attr_data["last_check_in"], CONVENTIONAL_TIME_TO_DELETE_SECONDS)
                    ),
                    "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
                }

                assert expected == actual


def test_stale_timestamp_config_serialization_serialize_host_compound(subtests, flask_app):
    with flask_app.app.app_context():
        for stale_warning_offset_seconds, culled_offset_seconds in (
            (CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS, CONVENTIONAL_TIME_TO_DELETE_SECONDS),
        ):
            with subtests.test(
                stale_warning_offset_seconds=stale_warning_offset_seconds,
                culled_offset_seconds=culled_offset_seconds,
            ):
                stale_timestamp = now() + timedelta(days=1)
            host = Host(
                subscription_manager_id=generate_uuid(),
                facts={},
                stale_timestamp=stale_timestamp,
                reporter="some reporter",
                org_id=USER_IDENTITY["org_id"],
            )

            for k, v in (("id", uuid4()), ("created_on", now()), ("modified_on", now())):
                setattr(host, k, v)

            config = CullingConfig(timedelta(days=stale_warning_offset_seconds), timedelta(days=culled_offset_seconds))
            staleness = get_sys_default_staleness()
            serialized = serialize_host(host, Timestamps(config), False, staleness=staleness)

            assert (
                _timestamp_to_str(_add_seconds(host.last_check_in, stale_warning_offset_seconds))
                == serialized["stale_warning_timestamp"]
            )
            assert (
                _timestamp_to_str(_add_seconds(host.last_check_in, culled_offset_seconds))
                == serialized["culled_timestamp"]
            )


@patch("app.serialization._serialize_tags")
@patch("app.serialization.serialize_facts")
@patch("app.serialization.serialize_canonical_facts")
def test_with_all_fields_serialization_serialize_host_mocked(
    serialize_canonical_facts, serialize_facts, serialize_tags, flask_app
):
    insights_id = generate_uuid()
    fqdn = "some fqdn"
    with flask_app.app.app_context():
        canonical_facts = {"insights_id": insights_id, "fqdn": fqdn}
        serialized_canonical_facts = {
            "insights_id": str(insights_id),
            "fqdn": fqdn,
        }
        serialize_canonical_facts.return_value = serialized_canonical_facts
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
            "openshift_cluster_id": str(uuid4()),
        }
        host_init_data = {
            **canonical_facts,
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
            "last_check_in": now(),
            "per_reporter_staleness": host.per_reporter_staleness,
        }
        for k, v in host_attr_data.items():
            setattr(host, k, v)

        staleness_offset = staleness_timestamps()
        staleness = get_sys_default_staleness()
        actual = serialize_host(host, staleness_offset, False, ("tags",), staleness=staleness)
        expected = {
            **serialized_canonical_facts,
            **unchanged_data,
            "facts": serialize_facts.return_value,
            "tags": serialize_tags.return_value,
            "id": str(host_attr_data["id"]),
            "created": _timestamp_to_str(host_attr_data["created_on"]),
            "updated": _timestamp_to_str(host_attr_data["modified_on"]),
            "last_check_in": _timestamp_to_str(host_attr_data["last_check_in"]),
            "stale_timestamp": _timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)
            ),
            "stale_warning_timestamp": _timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
            ),
            "culled_timestamp": _timestamp_to_str(
                host_attr_data["last_check_in"] + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)
            ),
            "per_reporter_staleness": host_attr_data["per_reporter_staleness"],
        }

        assert expected == actual

        # It is called twice, because we have 2 test cases
        serialize_canonical_facts.assert_called_with(host)
        serialize_facts.assert_called_with(host_init_data["facts"])
        serialize_tags.assert_called_with(host_init_data["tags"])


def test_non_empty_profile_is_not_changed_serialization_serialize_host_system_profile(flask_app):
    with flask_app.app.app_context():
        system_profile_facts = {
            "number_of_cpus": 1,
            "number_of_sockets": 2,
            "cores_per_socket": 3,
            "system_memory_bytes": 4,
        }
        host = Host(
            subscription_manager_id=generate_uuid(),
            display_name="some display name",
            system_profile_facts=system_profile_facts,
            stale_timestamp=now(),
            reporter="yupana",
            org_id=USER_IDENTITY["org_id"],
        )
        host.id = uuid4()

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": system_profile_facts}
        assert expected == actual


def test_empty_profile_is_empty_dict_serialization_serialize_host_system_profile(flask_app):
    with flask_app.app.app_context():
        host = Host(
            subscription_manager_id=generate_uuid(),
            display_name="some display name",
            stale_timestamp=now(),
            reporter="yupana",
            org_id=USER_IDENTITY["org_id"],
        )
        host.id = uuid4()
        host.system_profile_facts = None

        actual = serialize_host_system_profile(host)
        expected = {"id": str(host.id), "system_profile": {}}
        assert expected == actual


def _format_uuid_without_hyphens(uuid_):
    return uuid_.hex


def _format_uuid_with_hyphens(uuid_):
    return str(uuid_)


def _randomly_formatted_uuid(uuid_):
    transformation = choice((_format_uuid_without_hyphens, _format_uuid_with_hyphens))
    return transformation(uuid_)


def _randomly_formatted_sequence(seq):
    transformation = choice((list, tuple))
    return transformation(seq)


def test_values_are_stored_unchanged_serialization_deserialize_canonical_facts():
    input = {
        "insights_id": _randomly_formatted_uuid(uuid4()),
        "subscription_manager_id": _randomly_formatted_uuid(uuid4()),
        "satellite_id": _randomly_formatted_uuid(uuid4()),
        "bios_uuid": _randomly_formatted_uuid(uuid4()),
        "ip_addresses": _randomly_formatted_sequence(("10.10.0.1", "10.10.0.2")),
        "fqdn": "some fqdn",
        "mac_addresses": _randomly_formatted_sequence(("c2:00:d0:c8:61:01",)),
    }
    result = _deserialize_canonical_facts(input)
    assert result == input


def test_unknown_fields_are_rejected_serialization_deserialize_canonical_facts():
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
    assert result == canonical_facts


def test_empty_fields_are_rejected_serialization_deserialize_canonical_facts():
    canonical_facts = {"fqdn": "some fqdn"}
    input = {**canonical_facts, "insights_id": "", "ip_addresses": [], "mac_addresses": tuple()}
    result = _deserialize_canonical_facts(input)
    assert result == canonical_facts


def test_empty_fields_are_not_rejected_when_all_is_passed_serialization_deserialize_canonical_facts():
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
    assert result == expected


def test_contains_all_values_unchanged_serialization_serialize_canonical_facts():
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
    assert canonical_facts == serialize_canonical_facts(minimal_host(**canonical_facts))


def test_missing_fields_are_filled_with_none_serialization_serialize_canonical_facts():
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
    expected = {field: None for field in canonical_fact_fields}
    # insights_id should never be None - it defaults to zero UUID
    expected["insights_id"] = DEFAULT_INSIGHTS_ID
    assert expected == serialize_canonical_facts({})


def test_non_empty_namespaces_become_dict_items_serialization_deserialize_facts():
    input = [
        {"namespace": "first namespace", "facts": {"first key": "first value", "second key": "second value"}},
        {"namespace": "second namespace", "facts": {"third key": "third value"}},
    ]
    assert {item["namespace"]: item["facts"] for item in input} == _deserialize_facts(input)


def test_empty_namespaces_remain_unchanged_serialization_deserialize_facts(subtests):
    for empty_facts in ({}, None):
        with subtests.test(empty_facts=empty_facts):
            input = [
                {"namespace": "first namespace", "facts": {"first key": "first value"}},
                {"namespace": "second namespace", "facts": empty_facts},
            ]
            assert {item["namespace"]: item["facts"] for item in input} == _deserialize_facts(input)


def test_duplicate_namespaces_are_merged_serialization_deserialize_facts():
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
    assert expected == actual


def test_none_becomes_empty_dict_serialization_deserialize_facts():
    assert _deserialize_facts(None) == {}


def test_missing_key_raises_exception_serialization_deserialize_facts(subtests):
    invalid_items = (
        {"spacename": "second namespace", "facts": {"second key": "second value"}},
        {"namespace": "second namespace", "fact": {"second key": "second value"}},
        {"namespace": "second namespace"},
        {},
    )
    for invalid_item in invalid_items:
        with subtests.test(invalid_item=invalid_item):
            input = [{"namespace": "first namespace", "facts": {"first key": "first value"}}, invalid_item]
            with pytest.raises(InputFormatException):
                _deserialize_facts(input)


def test_empty_dict_becomes_empty_list_serialization_serialize_facts():
    assert serialize_facts({}) == []


def test_non_empty_namespaces_become_list_of_dicts_serialization_serialize_facts():
    facts = {
        "first namespace": {"first key": "first value", "second key": "second value"},
        "second namespace": {"third key": "third value"},
    }
    assert [{"namespace": namespace, "facts": facts} for namespace, facts in facts.items()] == serialize_facts(facts)


def test_empty_namespaces_have_facts_as_empty_dicts_serialization_serialize_facts(subtests):
    for empty_value in {}, None:
        with subtests.test(empty_value=empty_value):
            facts = {
                "first namespace": empty_value or {},
                "second namespace": {"first key": "first value"},
            }
            assert [
                {"namespace": namespace, "facts": facts or {}} for namespace, facts in facts.items()
            ] == serialize_facts(facts)


def test_utc_timezone_is_used_serialization_serialize_datetime():
    _now = now()
    assert _now.isoformat() == _serialize_datetime(_now)


def test_iso_format_is_used_serialization_serialize_datetime():
    dt = datetime(2019, 7, 3, 1, 1, 4, 20647, UTC)
    assert _serialize_datetime(dt) == "2019-07-03T01:01:04.020647+00:00"


def test_uuid_has_hyphens_computed_serialization_serialize_uuid():
    u = uuid4()
    assert str(u) == serialize_uuid(u)


def test_uuid_has_hyphens_literal_serialization_serialize_uuid():
    u = "4950e534-bbef-4432-bde2-aa3dd2bd0a52"
    assert u == serialize_uuid(UUID(u))


def test_deserialize_structured_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        with subtests.test(function=function):
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

            assert sorted(["namespace1", "namespace2", "namespace3", "null"]) == sorted(nested_tags.keys())
            assert sorted(["key1", "key2"]) == sorted(nested_tags["namespace1"].keys())
            assert sorted(["value1", "value2"]) == sorted(nested_tags["namespace1"]["key1"])
            assert sorted(["value3"]) == sorted(nested_tags["namespace1"]["key2"])
            assert sorted(["key3"]) == sorted(nested_tags["namespace2"].keys())
            assert nested_tags["namespace2"]["key3"] == []
            assert sorted(["key4"]) == sorted(nested_tags["namespace3"].keys())
            assert sorted(["value4"]) == sorted(nested_tags["namespace3"]["key4"])
            assert sorted(["key5"]) == sorted(nested_tags["null"].keys())
            assert sorted(["value5", "value6", "value7"]) == sorted(nested_tags["null"]["key5"])


def test_deserialize_nested_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        with subtests.test(function=function):
            input_tags = {
                "namespace1": {"key1": ["value1", "value2"], "key2": ["value3", "value3"]},
                "namespace2": {"key3": []},
                "namespace3": {"key4": [None, ""]},
                "namespace4": {},
                "": {"key5": ["value4"]},
                "null": {"key5": ["value5"]},
            }
            deserialized_tags = function(input_tags)

            assert sorted(["namespace1", "namespace2", "namespace3", "namespace4", "null"]) == sorted(
                deserialized_tags.keys()
            )
            assert sorted(["key1", "key2"]) == sorted(deserialized_tags["namespace1"].keys())
            assert sorted(["value1", "value2"]) == sorted(deserialized_tags["namespace1"]["key1"])
            assert sorted(["value3"]) == sorted(deserialized_tags["namespace1"]["key2"])
            assert sorted(["key3"]) == sorted(deserialized_tags["namespace2"].keys())
            assert deserialized_tags["namespace2"]["key3"] == []
            assert sorted(["key4"]) == sorted(deserialized_tags["namespace3"].keys())
            assert deserialized_tags["namespace3"]["key4"] == []
            assert deserialized_tags["namespace4"] == {}
            assert sorted(["key5"]) == sorted(deserialized_tags["null"].keys())
            assert sorted(["value4", "value5"]) == sorted(deserialized_tags["null"]["key5"])


def test_deserialize_structured_empty_list_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        with subtests.test(function=function):
            deserialized_tags = function([])
            assert deserialized_tags == {}


def test_deserialize_structured_no_key_error_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_list):
        for key in (None, ""):
            with subtests.test(function=function, key=key):
                with pytest.raises(ValueError):
                    structured_tags = [{"namespace": "namespace", "key": key, "value": "value"}]
                    function(structured_tags)


def test_deserialize_nested_empty_dict_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        with subtests.test(function=function):
            deserialized_tags = function({})
            assert deserialized_tags == {}


def test_deserialize_nested_no_key_error_serialization_deserialize_tags(subtests):
    for function in (_deserialize_tags, _deserialize_tags_dict):
        for key in (None, ""):
            with subtests.test(function=function, key=key):
                with pytest.raises(ValueError):
                    nested_tags = {"namespace": {key: ["value"]}}
                    function(nested_tags)


@pytest.fixture
def event_producer_setup():
    """Fixture for EventProducer tests setup."""
    config = Config(RuntimeEnvironment.TEST)
    with patch("app.queue.event_producer.KafkaProducer"):
        event_producer = EventProducer(config, config.event_topic)
        topic_name = config.event_topic
        threadctx.request_id = str(uuid4())
        basic_host = {
            "id": str(uuid4()),
            "stale_timestamp": now().isoformat(),
            "reporter": "test_reporter",
            "account": "test",
            "org_id": "test",
            "subscription_manager_id": generate_uuid(),
        }
        yield {
            "config": config,
            "event_producer": event_producer,
            "topic_name": topic_name,
            "basic_host": basic_host,
        }


@patch("app.queue.event_producer.KafkaProducer")
def test_happy_path_event_producer(subtests, flask_app):
    with flask_app.app.app_context():
        config = Config(RuntimeEnvironment.TEST)
        event_producer = EventProducer(config, config.event_topic)
        topic_name = config.event_topic
        threadctx.request_id = str(uuid4())
        basic_host = {
            "id": str(uuid4()),
            "stale_timestamp": now().isoformat(),
            "reporter": "test_reporter",
            "account": "test",
            "org_id": "test",
            "subscription_manager_id": generate_uuid(),
        }

        produce = event_producer._kafka_producer.produce
        poll = event_producer._kafka_producer.poll
        host_id = basic_host["id"]

        for event_type, host in (
            (EventType.created, basic_host),
            (EventType.updated, basic_host),
            (EventType.delete, deserialize_host(basic_host)),
        ):
            with subtests.test(event_type=event_type):
                event = build_event(event_type, host)
                headers = message_headers(event_type, host_id)

                event_producer.write_event(event, host_id, headers)

                produce.assert_called_once_with(
                    topic_name,
                    event.encode("utf-8"),
                    host_id.encode("utf-8"),
                    callback=ANY,
                    headers=ANY,
                )
                poll.assert_called_once()

                produce.reset_mock()
                poll.reset_mock()


@patch("app.queue.event_producer.KafkaProducer")
def test_producer_poll_event_producer(subtests, flask_app):
    with flask_app.app.app_context():
        config = Config(RuntimeEnvironment.TEST)
        event_producer = EventProducer(config, config.event_topic)
        topic_name = config.event_topic
        threadctx.request_id = str(uuid4())
        basic_host = {
            "id": str(uuid4()),
            "stale_timestamp": now().isoformat(),
            "reporter": "test_reporter",
            "account": "test",
            "org_id": "test",
            "subscription_manager_id": generate_uuid(),
        }

        produce = event_producer._kafka_producer.produce
        poll = event_producer._kafka_producer.poll
        host_id = basic_host["id"]

        for event_type, host in (
            (EventType.created, basic_host),
            (EventType.updated, basic_host),
            (EventType.delete, deserialize_host(basic_host)),
        ):
            with subtests.test(event_type=event_type):
                event = build_event(event_type, host)
                headers = message_headers(event_type, host_id)

                event_producer.write_event(event, host_id, headers)

                produce.assert_called_once_with(
                    topic_name,
                    event.encode("utf-8"),
                    host_id.encode("utf-8"),
                    callback=ANY,
                    headers=ANY,
                )
                poll.assert_called_once()

                produce.reset_mock()
                poll.reset_mock()


@patch("app.queue.event_producer.KafkaProducer")
@patch("app.queue.event_producer.message_not_produced")
def test_kafka_exceptions_are_caught_event_producer(message_not_produced_mock, flask_app):
    with flask_app.app.app_context():
        config = Config(RuntimeEnvironment.TEST)
        event_producer = EventProducer(config, config.event_topic)
        threadctx.request_id = str(uuid4())
        basic_host = {
            "id": str(uuid4()),
            "stale_timestamp": now().isoformat(),
            "reporter": "test_reporter",
            "account": "test",
            "org_id": "test",
            "subscription_manager_id": generate_uuid(),
        }

        event_type = EventType.created
        event = build_event(event_type, basic_host)
        key = basic_host["id"]
        headers = message_headers(event_type, basic_host["id"])

        kafkex = KafkaException()
        event_producer._kafka_producer.produce.side_effect = kafkex

        with pytest.raises(KafkaException):
            event_producer.write_event(event, key, headers)

        # convert headers to a list of tuples as done write_event
        headersTuple = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]

        message_not_produced_mock.assert_called_once_with(
            event_producer_logger,
            kafkex,
            config.event_topic,
            event=str(event).encode("utf-8"),
            key=key.encode("utf-8"),
            headers=headersTuple,
        )


@pytest.fixture
def normalizer(flask_app):
    with flask_app.app.app_context():
        return SystemProfileNormalizer()


def test_root_keys_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    original = {"number_of_cpus": 1}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_object_keys_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    original = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"]}]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_root_keys_are_removed_models_system_profile_normalizer_filter_keys(normalizer):
    payload = {"number_of_cpus": 1, "number_of_gpus": 2}
    normalizer.filter_keys(payload)
    expected = {"number_of_cpus": 1}
    assert expected == payload


def test_array_items_object_keys_removed_models_system_profile_normalizer_filter_keys(normalizer):
    payload = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"], "mac_addresses": ["aa:bb:cc:dd:ee:ff"]}]}
    normalizer.filter_keys(payload)
    expected = {"network_interfaces": [{"ipv4_addresses": ["10.0.0.1"]}]}
    assert expected == payload


def test_root_non_object_keys_without_type_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"] = {"properties": {"number_of_cpus": {"type": "integer"}}}
    payload = {"number_of_gpus": 1}
    original = deepcopy(payload)
    normalizer.filter_keys(payload)
    assert original == payload


def test_nested_non_object_keys_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
        "properties": {"enable_acpi": {"type": "boolean"}}
    }
    original = {"boot_options": {"safe_mode": False}}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_non_object_keys_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {
        "type": "array",
        "items": {"properties": {"model": {"type": "string"}}},
    }
    original = {"hid_devices": [{"model": "Keyboard 3in1", "manufacturer": "Logitech"}]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_root_object_keys_without_properties_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"] = {"type": "object"}
    payload = {"number_of_cpus": 1}
    original = deepcopy(payload)
    normalizer.filter_keys(payload)
    assert original == payload


def test_nested_object_keys_without_properties_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {"type": "object"}
    original = {"boot_options": {"enable_acpi": True}}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_object_keys_without_properties_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {
        "type": "array",
        "items": {"type": "object"},
    }
    original = {"hid_devices": [{"model": "Keyboard 3in1", "manufacturer": "Logitech"}]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_nested_object_keys_without_properties_are_kept_models_system_profile_normalizer_filter_keys(
    normalizer,
):
    original = {"disk_devices": [{"options": {"uid": "0"}}, {"options": "uid=0"}]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_without_schema_are_kept_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["hid_devices"] = {"type": "array"}
    original = {"hid_devices": [{"model": "Keyboard 3in1"}, "Keyboard 3in1"]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_additional_properties_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["additionalProperties"] = {"type": "integer"}
    payload = {"number_of_gpus": "1"}
    normalizer.filter_keys(payload)
    assert payload == {}


def test_required_properties_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["required"] = ["number_of_gpus"]
    payload = {"number_of_gpus": 1}
    normalizer.filter_keys(payload)
    assert payload == {}


def test_root_invalid_objects_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
        "type": "object",
        "properties": {"enable_acpi": {"type": "boolean"}},
    }
    original = {"boot_options": "enable_acpi=1"}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_invalid_objects_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    original = {"network_interfaces": ["eth0"]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_array_items_invalid_nested_objects_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["DiskDevice"]["properties"]["mount_options"] = {
        "type": "object",
        "properties": {"uid": {"type": "integer"}},
    }
    original = {"disk_devices": [{"mount_options": "uid=0"}]}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def test_root_invalid_arrays_are_ignored_models_system_profile_normalizer_filter_keys(normalizer):
    normalizer.schema["$defs"]["SystemProfile"]["properties"]["boot_options"] = {
        "type": "array",
        "items": {"type": "string"},
    }
    original = {"boot_options": "enable_acpi=1"}
    payload = deepcopy(original)
    normalizer.filter_keys(payload)
    assert original == payload


def _payload(system_profile):
    return {
        "account": "0000001",
        "org_id": "3340851",
        "system_profile": system_profile,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }


def _assert_system_profile_is_invalid(load_result):
    assert "system_profile" in load_result
    assert any(
        "System profile does not conform to schema." in message or "Key may not be empty." in message
        for message in load_result["system_profile"]
    )


def test_invalid_values_are_rejected_models_system_profile(subtests, flask_app):
    with flask_app.app.app_context():
        schema = HostSchema()
        for system_profile in INVALID_SYSTEM_PROFILES:
            with subtests.test(system_profile=system_profile):
                payload = _payload(system_profile)
                result = schema.validate(payload)
                _assert_system_profile_is_invalid(result)


def test_specification_file_is_used_models_system_profile(flask_app):
    with flask_app.app.app_context():
        payload = _payload({"number_of_cpus": 1})

        orig_spec = system_profile_specification()
        mock_spec = deepcopy(orig_spec)
        mock_spec["$defs"]["SystemProfile"]["properties"]["number_of_cpus"]["minimum"] = 2

        with mock_system_profile_specification(mock_spec):
            schema = HostSchema()
            result = schema.validate(payload)
            _assert_system_profile_is_invalid(result)


def test_types_are_coerced_models_system_profile(flask_app):
    with flask_app.app.app_context():
        payload = _payload({"number_of_cpus": "1"})
        schema = HostSchema()
        result = schema.load(payload)
        assert result["system_profile"] == {"number_of_cpus": 1}


def test_fields_are_filtered_models_system_profile(flask_app):
    with flask_app.app.app_context():
        payload = _payload(
            {
                "number_of_cpus": 1,
                "number_of_gpus": 2,
                "network_interfaces": [{"ipv4_addresses": ["10.10.10.1"], "mac_addresses": ["aa:bb:cc:dd:ee:ff"]}],
            }
        )
        schema = HostSchema()
        result = schema.load(payload)
        expected = {"number_of_cpus": 1, "network_interfaces": [{"ipv4_addresses": ["10.10.10.1"]}]}
        assert expected == result["system_profile"]


@patch("app.models.schemas.jsonschema_validate")
def test_type_coercion_happens_before_loading_models_system_profile(jsonschema_validate, flask_app):
    with flask_app.app.app_context():
        schema = HostSchema()
        payload = _payload({"number_of_cpus": "1"})
        schema.load(payload)
        jsonschema_validate.assert_called_once_with(
            {"number_of_cpus": 1}, HostSchema.system_profile_normalizer.schema, format_checker=ANY
        )


@patch("app.models.schemas.jsonschema_validate")
def test_type_filtering_happens_after_loading_models_system_profile(jsonschema_validate, flask_app):
    with flask_app.app.app_context():
        schema = HostSchema()
        payload = _payload({"number_of_gpus": 1})
        result = schema.load(payload)
        jsonschema_validate.assert_called_once_with(
            {"number_of_gpus": 1}, HostSchema.system_profile_normalizer.schema, format_checker=ANY
        )
        assert result["system_profile"] == {}


def test_custom_fields_parser_query_parameter_parsing():
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


def test_valid_deep_object_list_query_parameter_parsing():
    for key, value in (("asdf[foo]", ["bar"]), ("system_profile[field1][field2]", ["value1"])):
        _, _, is_deep_object = customURIParser._make_deep_object(key, value)
    assert is_deep_object


def test_invalid_deep_object_list_query_parameter_parsing():
    for key, value in (
        ("asdf[foo]", ["bar", "baz"]),
        ("system_profile[field1][field2]", ["value1", "value2", "value3"]),
    ):
        with pytest.raises(BadRequestProblem):
            customURIParser._make_deep_object(key, value)


def test_custom_regex_escape_custom_regex_method(subtests):
    for regex_input, output in (
        (".?well+", "\\.\\?well\\+"),
        ("&[^abc]~", "\\&\\[^abc\\]\\~"),
        ("some|*#thing", "some\\|\\*\\#thing"),
        ('.?+*|{}[]()"\\#@&<>~', '\\.\\?\\+\\*\\|\\{\\}\\[\\]\\(\\)\\"\\\\\\#\\@\\&\\<\\>\\~'),
        ("\\", "\\\\"),
    ):
        with subtests.test(regex_input=regex_input):
            result = custom_escape(regex_input)
        assert result == output


@patch("socket.socket.connect_ex")
def test_happy_path_kafka_availability(connect_ex):
    connect_ex.return_value = 0
    assert host_kafka.kafka_available()
    connect_ex.assert_called_once()


@patch("socket.socket.connect_ex")
def test_valid_server_kafka_availability(connect_ex):
    config = Config(RuntimeEnvironment.TEST)
    connect_ex.return_value = 0
    akafka = [config.bootstrap_servers]
    assert host_kafka.kafka_available(akafka)
    connect_ex.assert_called_once()


@patch("socket.socket.connect_ex")
def test_list_of_valid_servers_kafka_availability(connect_ex):
    connect_ex.return_value = 0
    kafka_servers = ["127.0.0.1:29092", "localhost:29092"]
    assert host_kafka.kafka_available(kafka_servers)
    connect_ex.assert_called_once()


@patch("socket.socket.connect_ex")
def test_list_with_first_bad_second_good_server_kafka_availability(connect_ex):
    connect_ex.return_value = 0
    kafka_servers = ["localhost29092", "127.0.0.1:29092"]
    assert host_kafka.kafka_available(kafka_servers)
    connect_ex.assert_called_once()


@patch("socket.socket.connect_ex")
def test_list_with_first_good_second_bad_server_kafka_availability(connect_ex):
    # second bad with missing ':'.  Returns as soon as the first kafka server found.
    connect_ex.return_value = 0
    kafka_servers = ["localhost:29092", "127.0.0.129092"]
    assert host_kafka.kafka_available(kafka_servers)
    connect_ex.assert_called_once()


@patch("socket.socket.connect_ex")
def test_invalid_kafka_server_kafka_availability(connect_ex):
    kafka_servers = ["localhos.129092"]
    assert host_kafka.kafka_available(kafka_servers) is False
    connect_ex.assert_not_called()


@patch("socket.socket.connect_ex")
def test_bogus_kafka_server_kafka_availability(connect_ex):
    kafka_servers = ["bogus-kafka29092"]
    assert host_kafka.kafka_available(kafka_servers) is False
    connect_ex.assert_not_called()


@patch("socket.socket.connect_ex")
def test_wrong_kafka_server_post_kafka_availability(connect_ex):
    connect_ex.return_value = 61
    kafka_servers = ["localhost:54321"]
    assert host_kafka.kafka_available(kafka_servers) is False
    connect_ex.assert_called_once()


# Tests for time conversion utility functions in app.culling module.


def test_days_to_seconds_standard_conversions_culling_utility_functions(subtests):
    """Test standard day to second conversions."""
    from app.culling import days_to_seconds

    test_cases = [
        (0, 0),
        (1, 86400),
        (2, 172800),
        (7, 604800),
        (30, 2592000),
        (365, 31536000),
    ]

    for days, expected_seconds in test_cases:
        with subtests.test(days=days):
            assert days_to_seconds(days) == expected_seconds


def test_seconds_to_days_exact_conversions_culling_utility_functions(subtests):
    """Test exact second to day conversions (no truncation needed)."""
    from app.culling import seconds_to_days

    test_cases = [
        (0, 0),
        (86400, 1),
        (172800, 2),
        (604800, 7),
        (2592000, 30),
        (31536000, 365),
    ]

    for seconds, expected_days in test_cases:
        with subtests.test(seconds=seconds):
            assert seconds_to_days(seconds) == expected_days


def test_seconds_to_days_truncation_culling_utility_functions(subtests):
    """Test that seconds_to_days correctly truncates partial days."""
    from app.culling import seconds_to_days

    # Test cases where seconds include partial days
    test_cases = [
        (1, 0),  # Less than a day
        (43200, 0),  # 12 hours (half a day)
        (86399, 0),  # Just under 1 day
        (86401, 1),  # Just over 1 day - should truncate to 1
        (129600, 1),  # 1.5 days - should truncate to 1
        (172799, 1),  # Just under 2 days - should truncate to 1
        (172801, 2),  # Just over 2 days - should truncate to 2
        (604799, 6),  # Just under 7 days - should truncate to 6
        (604801, 7),  # Just over 7 days - should truncate to 7
    ]

    for seconds, expected_days in test_cases:
        with subtests.test(seconds=seconds):
            result = seconds_to_days(seconds)
            assert result == expected_days
            # Verify truncation (result should always be floor division)
            assert result == seconds // 86400


def test_days_to_seconds_round_trip_culling_utility_functions(subtests):
    """Test that converting days to seconds and back yields the original value."""
    from app.culling import days_to_seconds
    from app.culling import seconds_to_days

    test_days = [0, 1, 7, 29, 30, 100, 365]

    for days in test_days:
        with subtests.test(days=days):
            seconds = days_to_seconds(days)
            converted_back = seconds_to_days(seconds)
            assert converted_back == days


def test_seconds_to_days_with_conventional_constants_culling_utility_functions():
    """Test seconds_to_days with the conventional staleness constants."""
    from app.culling import seconds_to_days

    # CONVENTIONAL_TIME_TO_STALE_SECONDS = 104400 (29 hours)
    assert seconds_to_days(104400) == 1  # 29 hours = 1 day (truncated)

    # CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS = 604800 (7 days)
    assert seconds_to_days(604800) == 7

    # CONVENTIONAL_TIME_TO_DELETE_SECONDS = 2592000 (30 days)
    assert seconds_to_days(2592000) == 30


def test_days_to_seconds_with_conventional_days_culling_utility_functions():
    """Test days_to_seconds with common staleness period values."""
    from app.culling import days_to_seconds

    # These should match the inverse of the conventional constants (for whole days)
    assert days_to_seconds(7) == 604800  # 7 days = CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
    assert days_to_seconds(30) == 2592000  # 30 days = CONVENTIONAL_TIME_TO_DELETE_SECONDS
