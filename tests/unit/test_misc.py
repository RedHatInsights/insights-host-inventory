import os
from copy import deepcopy
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

import pytest
from confluent_kafka import KafkaException
from connexion.exceptions import BadRequestProblem

from api import api_operation
from api import custom_escape
from api.parsing import custom_fields_parser
from api.parsing import customURIParser
from app import SPECIFICATION_FILE
from app import V2_SPECIFICATION_FILE
from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import threadctx
from app.models import Host
from app.models import HostSchema
from app.models import SystemProfileNormalizer
from app.queue.event_producer import EventProducer
from app.queue.event_producer import logger as event_producer_logger
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import _sanitize_workloads_none_values
from app.serialization import deserialize_host
from lib import host_kafka
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import make_config
from tests.helpers.test_utils import now
from tests.helpers.test_utils import set_environment


def _payload(system_profile):
    return {
        "account": "0000001",
        "org_id": "3340851",
        "system_profile": system_profile,
        "stale_timestamp": now().isoformat(),
        "reporter": "test",
    }


def _compile_filters_to_sql(filters: tuple) -> str:
    """Compile a tuple of filter expressions to a SQL string for structural assertions."""
    from sqlalchemy import and_
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect

    combined = and_(*filters) if len(filters) > 1 else filters[0]
    return str(combined.compile(dialect=pg_dialect()))


@pytest.fixture
def normalizer(flask_app):
    with flask_app.app.app_context():
        return SystemProfileNormalizer()


def _assert_system_profile_is_invalid(load_result):
    assert "system_profile" in load_result
    assert any(
        "System profile does not conform to schema." in message or "Key may not be empty." in message
        for message in load_result["system_profile"]
    )


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


def test_kafka_produducer_acks(subtests):
    for value in (0, 1, "all"):
        with subtests.test(value=value):
            with set_environment({"KAFKA_PRODUCER_ACKS": f"{value}"}):
                assert make_config().kafka_producer["acks"] == value


def test_kafka_producer_acks_unknown():
    with set_environment({"KAFKA_PRODUCER_ACKS": "2"}):
        with pytest.raises(ValueError):
            make_config()


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
                assert make_config().kafka_producer[param] == 2020


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
                    make_config()


def test_kafka_producer_defaults(subtests):
    config = make_config()

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


@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
@patch("app.SPECIFICATION_FILE", value="./swagger/api.spec.yaml")
def test_yaml_specification_create_app_connexion(_translating_parser, _init_app, _app):
    # Create an app with bad defs assert that it won't create and will raise an exception
    with patch("app.create_app", side_effect=Exception("mocked error")):
        with pytest.raises(Exception):  # noqa: B017
            create_app(RuntimeEnvironment.TEST)


@pytest.mark.parametrize(
    "v2_enabled",
    ["true", "false", None],
    ids=["v2-enabled", "v2-disabled", "v2-unset"],
)
@patch("app.connexion.FlaskApp")
@patch("app.db.init_app")
@patch("app.TranslatingParser")
def test_v2_api_registration(translating_parser, _init_app, app, v2_enabled):
    env_vars = {"HBI_V2_API_ENABLED": v2_enabled} if v2_enabled is not None else {}
    with patch.dict("os.environ", env_vars, clear=False):
        if v2_enabled is None:
            os.environ.pop("HBI_V2_API_ENABLED", None)
        create_app(RuntimeEnvironment.TEST)

    v2_add_api_calls = [
        call for call in app.return_value.add_api.call_args_list if call.kwargs.get("base_path") == "/api/inventory/v2"
    ]
    v2_parser_calls = [call for call in translating_parser.call_args_list if V2_SPECIFICATION_FILE in call.args]

    if v2_enabled == "true":
        assert v2_add_api_calls, "V2 API should be registered when HBI_V2_API_ENABLED is true"
        assert v2_parser_calls, "TranslatingParser should be called with V2 spec when V2 is enabled"
        v2_call = v2_add_api_calls[0]
        assert v2_call.kwargs["resolver"].default_module_name == "api.v2"
        assert v2_call.kwargs["arguments"] == {"title": "HBI V2 API"}
        assert v2_call.kwargs["validate_responses"] is True
        assert v2_call.kwargs["strict_validation"] is True
        assert v2_call.kwargs["validator_map"] is not None
    else:
        assert not v2_add_api_calls, "No V2 API should be registered when HBI_V2_API_ENABLED is not true"
        assert not v2_parser_calls, "TranslatingParser should not be called with V2 spec when V2 is not enabled"


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
        }

        assert Host is type(actual)
        for key, value in expected.items():
            assert value == getattr(actual, key)


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
                    topic=topic_name,
                    value=event.encode("utf-8"),
                    key=host_id.encode("utf-8"),
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
                    topic=topic_name,
                    value=event.encode("utf-8"),
                    key=host_id.encode("utf-8"),
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
        (
            ("fields", ["system_profile"], ['["arch"]']),
            [{"system_profile": {"arch": True}}],
        ),
        (
            ("fields", ["system_profile"], ['["arch","host_type"]']),
            [{"system_profile": {"arch": True, "host_type": True}}],
        ),
        (
            ("fields", ["system_profile"], ['["os_version", "arch", "yum_repos"]']),
            [{"system_profile": {"os_version": True, "arch": True, "yum_repos": True}}],
        ),
    ):
        root_key, response, is_deep_object = custom_fields_parser(*parser_input)
        assert root_key == parser_input[0]
        assert response == output
        assert is_deep_object is True


def test_sparse_fields_validator_resolves_bracket_query_before_lookup():
    """Bracket-style fields[system_profile] must be validated, not skipped.

    ParameterValidator.validate() builds a ConnexionRequest whose query_params
    property runs the URI parser. The sparse-field check then looks up "fields".
    If that resolution did not happen first, the raw key fields[system_profile]
    would miss the lookup and an unknown field would be accepted.
    """
    from connexion.lifecycle import ConnexionRequest

    from app.custom_validator import CustomParameterValidator

    parameters = [
        {
            "name": "fields",
            "in": "query",
            "style": "deepObject",
            "explode": True,
            "x-validator": "sparseFields",
            "schema": {"type": "object"},
        }
    ]
    parser = customURIParser(parameters, {})
    validator = CustomParameterValidator(
        parameters,
        uri_parser=parser,
        strict_validation=True,
        system_profile_spec={"arch": {}},
    )

    def scope_for(query_string: str) -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/hosts",
            "raw_path": b"/hosts",
            "query_string": query_string.encode(),
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("testserver", 80),
        }

    unknown_scope = scope_for("fields[system_profile]=not_a_real_field")
    request = ConnexionRequest(unknown_scope, uri_parser=parser)
    assert list(request.query_params) == ["fields"]
    assert request.query_params["fields"] == {"system_profile": {"not_a_real_field": True}}

    with pytest.raises(BadRequestProblem, match="not_a_real_field"):
        validator.validate(unknown_scope)

    validator.validate(scope_for("fields[system_profile]=arch"))


@pytest.mark.parametrize("legacy_field", ("crowdstrike", "ibm_db2", "oracle_db"))
@pytest.mark.parametrize(
    "query_string",
    (
        "fields[system_profile]={field}",
        'fields[system_profile]=["{field}"]',
    ),
    ids=("comma-separated", "json-array"),
)
def test_sparse_fields_validator_allows_legacy_workload_root_fields_absent_from_schema(legacy_field, query_string):
    from app.custom_validator import CustomParameterValidator

    parameters = [
        {
            "name": "fields",
            "in": "query",
            "style": "deepObject",
            "explode": True,
            "x-validator": "sparseFields",
            "schema": {"type": "object"},
        }
    ]
    parser = customURIParser(parameters, {})
    validator = CustomParameterValidator(
        parameters,
        uri_parser=parser,
        strict_validation=True,
        system_profile_spec={"arch": {}},
    )

    def scope_for(query: str) -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/hosts",
            "raw_path": b"/hosts",
            "query_string": query.encode(),
            "headers": [],
            "client": ("127.0.0.1", 123),
            "server": ("testserver", 80),
        }

    validator.validate(scope_for(query_string.format(field=legacy_field)))


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


@pytest.mark.parametrize(
    "key,value",
    [
        # Single-level filter paths with plain string values should be rejected
        # because they would set the entire system_profile to a string instead of a nested filter
        ("filter[system_profile]", ["plain_string"]),
        ("filter[system_profile]", ["true"]),
        ("filter[system_profile]", ["123"]),
        ("filter[other_field]", ["some_value"]),
    ],
)
def test_single_level_filter_path_requires_json_object(key, value):
    """Test that filter[X]=plain_value (single path element) raises BadRequestProblem."""
    with pytest.raises(BadRequestProblem) as exc_info:
        customURIParser._make_deep_object(key, value)
    assert "must be a JSON object or use bracket notation" in str(exc_info.value.detail)


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


def test_sanitize_workloads_none_values_removes_none_values():
    """
    Test that _sanitize_workloads_none_values removes None values from workloads.*.

    This ensures that None values in workloads.* fields (like workloads.ansible.hub_version)
    are removed from the response, which would otherwise cause OpenAPI spec validation failures
    since those fields are defined as type 'string' without nullable: true.
    """
    # Test case 1: ansible with None hub_version
    system_profile = {
        "workloads": {
            "ansible": {
                "controller_version": "4.5.6",
                "hub_version": None,
            }
        }
    }
    result = _sanitize_workloads_none_values(system_profile)

    assert "hub_version" not in result["workloads"]["ansible"]
    assert result["workloads"]["ansible"]["controller_version"] == "4.5.6"

    # Test case 2: crowdstrike with None falcon_version
    system_profile = {
        "workloads": {
            "crowdstrike": {
                "falcon_aid": "abc123",
                "falcon_version": None,
            }
        }
    }
    result = _sanitize_workloads_none_values(system_profile)

    assert "falcon_version" not in result["workloads"]["crowdstrike"]
    assert result["workloads"]["crowdstrike"]["falcon_aid"] == "abc123"

    # Test case 3: sap with None version
    system_profile = {
        "workloads": {
            "sap": {
                "sap_system": True,
                "sids": ["H2O"],
                "version": None,
            }
        }
    }
    result = _sanitize_workloads_none_values(system_profile)

    assert "version" not in result["workloads"]["sap"]
    assert result["workloads"]["sap"]["sap_system"] is True
    assert result["workloads"]["sap"]["sids"] == ["H2O"]


def test_sanitize_workloads_none_values_preserves_valid_values():
    """Test that _sanitize_workloads_none_values keeps non-None values."""
    system_profile = {
        "workloads": {
            "ansible": {
                "controller_version": "4.5.6",
                "hub_version": "1.2.3",
            },
            "crowdstrike": {
                "falcon_aid": "abc123",
                "falcon_backend": "us-1",
                "falcon_version": "7.14.16703.0",
            },
            "sap": {
                "sap_system": True,
                "sids": ["H2O"],
                "instance_number": "00",
                "version": "1.00.122.04.1478575636",
            },
        }
    }
    result = _sanitize_workloads_none_values(system_profile)

    assert result["workloads"]["ansible"]["controller_version"] == "4.5.6"
    assert result["workloads"]["ansible"]["hub_version"] == "1.2.3"
    assert result["workloads"]["crowdstrike"]["falcon_aid"] == "abc123"
    assert result["workloads"]["sap"]["sap_system"] is True
    assert result["workloads"]["sap"]["sids"] == ["H2O"]


def test_workloads_boolean_true_produces_exists(flask_app):
    """sap_system=true should produce an EXISTS subquery with @> containment."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter({"workloads": {"sap": {"sap_system": "true"}}})
        sql = _compile_filters_to_sql(filters)
        assert "EXISTS" in sql
        assert "NOT (EXISTS" not in sql
        assert "@>" in sql


def test_workloads_nil_produces_not_exists(flask_app):
    """sap_system=nil should produce a NOT EXISTS subquery."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter({"workloads": {"sap": {"sap_system": {"is": "nil"}}}})
        sql = _compile_filters_to_sql(filters)
        assert "NOT (EXISTS" in sql


def test_workloads_string_equality_produces_exists_with_containment(flask_app):
    """String equality on a non-wildcard field should produce EXISTS with full @> containment."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter({"workloads": {"crowdstrike": {"falcon_backend": "auto"}}})
        sql = _compile_filters_to_sql(filters)
        assert "EXISTS" in sql
        assert "@>" in sql
        # Should NOT fall back to #>> text extraction
        assert "#>>" not in sql


def test_workloads_wildcard_not_nil_produces_exists_with_containment(flask_app):
    """Wildcard fields like controller_version[is]=not_nil should hit the optimized path."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter({"workloads": {"ansible": {"controller_version": {"is": "not_nil"}}}})
        sql = _compile_filters_to_sql(filters)
        assert "EXISTS" in sql
        assert "@>" in sql
        assert "NOT (EXISTS" not in sql


def test_workloads_wildcard_exact_equality_produces_containment(flask_app):
    """Wildcard field with exact value (no *) should use @> containment."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter({"workloads": {"mssql": {"version": "15.3"}}})
        sql = _compile_filters_to_sql(filters)
        assert "EXISTS" in sql
        assert "@>" in sql
        assert "#>>" not in sql
        assert "ILIKE" not in sql.upper()


def test_workloads_multiple_positive_filters_produce_single_exists(flask_app):
    """Multiple positive workloads filters should merge into one EXISTS(... AND ...)."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter(
            {
                "workloads": {"sap": {"sap_system": "true"}},
                "ansible": {"controller_version": {"is": "not_nil"}},
            }
        )
        sql = _compile_filters_to_sql(filters)
        # Both filters in a single EXISTS — count occurrences
        assert sql.count("EXISTS") == 1
        assert "NOT (EXISTS" not in sql


def test_workloads_mixed_positive_and_nil_produces_exists_and_not_exists(flask_app):
    """Positive + nil workloads filters produce one EXISTS and one NOT EXISTS."""
    from api.filtering.db_custom_filters import build_system_profile_filter

    with flask_app.app.app_context():
        filters = build_system_profile_filter(
            {
                "workloads": {"sap": {"sap_system": "true"}},
                "mssql": {"version": {"is": "nil"}},
            }
        )
        sql = _compile_filters_to_sql(filters)
        assert "EXISTS" in sql
        assert "NOT (EXISTS" in sql
