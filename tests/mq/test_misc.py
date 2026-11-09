from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import pytest
from connexion import FlaskApp
from pytest_mock import MockerFixture
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from api.staleness_query import get_staleness_obj
from app import create_app
from app.environment import RuntimeEnvironment
from app.exceptions import ValidationException
from app.logging import threadctx
from app.models import Host
from app.models import db
from app.queue.event_producer import EventProducer
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import OperationResult
from app.queue.host_mq import WorkspaceMessageConsumer
from app.queue.host_mq import _sanitize_json_object_for_postgres
from app.queue.host_mq import cache_ingested_system
from app.queue.host_mq import write_add_update_event_message
from app.queue.host_mq import write_delete_event_message
from inv_mq_service import build_topic_to_consumer_map
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.db_utils import create_reference_host_in_db
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import generate_kessel_workspace_message
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import OWNER_ID
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import valid_system_profile


def test_request_id_is_reset(mocker, flask_app, ingress_message_consumer_mock):
    with flask_app.app.app_context():
        mock_event_producer = mocker.Mock()
        mock_notification_event_producer = mocker.Mock()
        metadata = get_platform_metadata()

        message = wrap_message(minimal_host().data(), "add_host", metadata)
        result = ingress_message_consumer_mock.handle_message(json.dumps(message))
        write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)
        assert json.loads(mock_event_producer.write_event.call_args[0][0])["metadata"]["request_id"] == metadata.get(
            "request_id"
        )
        assert threadctx.request_id == metadata.get("request_id")

        metadata["request_id"] = None
        message = wrap_message(minimal_host().data(), "add_host", metadata)
        result = ingress_message_consumer_mock.handle_message(json.dumps(message))

        assert threadctx.request_id is None


def test_threadctx_account_number_is_reset(flask_app, ingress_message_consumer_mock):
    with flask_app.app.app_context():
        # Create a host in one org
        host = minimal_host(org_id=SYSTEM_IDENTITY["org_id"], account=SYSTEM_IDENTITY["account_number"])
        message = wrap_message(host.data(), "add_host", get_platform_metadata(SYSTEM_IDENTITY))
        ingress_message_consumer_mock.handle_message(json.dumps(message))
        assert threadctx.account_number == SYSTEM_IDENTITY["account_number"]

        # Create a host in a different org that has no account number
        identity = deepcopy(SYSTEM_IDENTITY)
        identity["org_id"] = "1234567890"
        del identity["account_number"]
        host = minimal_host(org_id=identity["org_id"])
        message = wrap_message(host.data(), "add_host", get_platform_metadata(identity))
        ingress_message_consumer_mock.handle_message(json.dumps(message))
        assert threadctx.account_number is None


@mock.patch.object(IngressMessageConsumer, "handle_message", return_value=None, side_effect=[None, None])
def test_shutdown_handler(handle_message_mock, mocker, flask_app):
    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage(), FakeMessage()]

    fake_event_producer = mocker.Mock()
    fake_notification_event_producer = mocker.Mock()
    consumer = IngressMessageConsumer(fake_consumer, flask_app, fake_event_producer, fake_notification_event_producer)
    consumer.event_loop(interrupt=mocker.Mock(side_effect=(False, True)))
    fake_consumer.consume.assert_called_once()

    assert handle_message_mock.call_count == 2


@pytest.mark.parametrize(
    "expected_value, system_profile",
    [
        ("False", {}),
        ("False", {"bootc_status": {}}),
        ("True", {"bootc_status": {"booted": {}}}),
        ("True", {"bootc_status": {"booted": {"image": "192.168.0.1:5000/foo/foo:latest"}}}),
    ],
)
def test_verify_bootc_in_headers(expected_value, system_profile, mq_create_or_update_host):
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=generate_uuid(),
        system_profile=system_profile,
    )

    _, _, headers = mq_create_or_update_host(host, return_all_data=True)
    assert "is_bootc" in headers
    assert headers["is_bootc"] == expected_value


def test_valid_string_is_ok():
    result = _sanitize_json_object_for_postgres("naïve fiancé 👰🏻")
    assert result == "naïve fiancé 👰🏻"


def test_invalid_string_raises_exception():
    with pytest.raises(UnicodeEncodeError):
        _sanitize_json_object_for_postgres("hello\udce2\udce2")


def test_dicts_are_traversed(mocker):
    mock = mocker.patch("app.queue.host_mq._sanitize_json_object_for_postgres", side_effect=lambda x: x)

    _sanitize_json_object_for_postgres({"first": "item", "second": "value"})

    mock.assert_has_calls(
        (mocker.call("first"), mocker.call("item"), mocker.call("second"), mocker.call("value")), any_order=True
    )


def test_lists_are_traversed(mocker):
    mock = mocker.patch("app.queue.host_mq._sanitize_json_object_for_postgres", side_effect=lambda x: x)

    _sanitize_json_object_for_postgres(["first", "second"])

    mock.assert_has_calls((mocker.call("first"), mocker.call("second")), any_order=True)


@pytest.mark.parametrize(
    "obj",
    (
        {"first": "naïve fiancé 👰🏻", "second": "hello\udce2\udce2"},
        {"first": {"subkey": "hello\udce2\udce2"}, "second": "🤷🏻‍♂️"},
        [{"first": "hello\udce2\udce2"}],
        {"deep": ["deeper", {"deepest": ["Mariana trench", {"Earth core": "hello\udce2\udce2"}]}]},
    ),
)
def test_invalid_string_is_found_in_dict_value(obj):
    with pytest.raises(UnicodeEncodeError):
        _sanitize_json_object_for_postgres(obj)


@pytest.mark.parametrize(
    "obj",
    (
        {"naïve fiancé 👰🏻": "first", "hello\udce2\udce2": "second"},
        {"first": {"hello\udce2\udce2": "subvalue"}, "🤷🏻‍♂️": "second"},
        [{"hello\udce2\udce2": "first"}],
        {"deep": ["deeper", {"deepest": ["Mariana trench", {"hello\udce2\udce2": "Earth core"}]}]},
    ),
)
def test_invalid_string_is_found_in_dict_key(obj):
    with pytest.raises(UnicodeEncodeError):
        _sanitize_json_object_for_postgres(obj)


@pytest.mark.parametrize(
    "obj",
    (
        ["naïve fiancé 👰🏻", "hello\udce2\udce2"],
        {"first": ["hello\udce2\udce2"], "second": "🤷🏻‍♂️"},
        ["first", ["hello\udce2\udce2"]],
        ["deep", {"deeper": ["deepest", {"Mariana trench": ["Earth core", "hello\udce2\udce2"]}]}],
    ),
)
def test_invalid_string_is_found_in_list_item(obj):
    with pytest.raises(UnicodeEncodeError):
        _sanitize_json_object_for_postgres(obj)


@pytest.mark.parametrize("value", (1.23, 0, 123, -123, True, False, None))
def test_other_values_are_ignored(value):
    result = _sanitize_json_object_for_postgres(value)
    assert result == value


@pytest.mark.parametrize(
    "input_obj,expected_output",
    (
        # Simple string with NULL byte
        ("hello\x00world", "helloworld"),
        # Multiple NULL bytes in string
        ("hel\x00lo\x00wor\x00ld", "helloworld"),
        # String with only NULL bytes
        ("\x00\x00\x00", ""),
        # Dictionary with NULL byte in value
        ({"first": "hello\x00world", "second": "normal"}, {"first": "helloworld", "second": "normal"}),
        # Dictionary with NULL byte in key
        ({"hello\x00world": "value"}, {"helloworld": "value"}),
        # List with NULL byte
        (["hello\x00world", "normal"], ["helloworld", "normal"]),
        # Nested structure with NULL bytes
        (
            {
                "deep": ["deeper", {"deepest": ["Mariana\x00trench", {"Earth\x00core": "center\x00"}]}],
                "simple": "test\x00value",
            },
            {
                "deep": ["deeper", {"deepest": ["Marianatrench", {"Earthcore": "center"}]}],
                "simple": "testvalue",
            },
        ),
    ),
)
def test_null_bytes_are_sanitized(input_obj, expected_output):
    """Test that NULL bytes are removed from various data structures"""
    result = _sanitize_json_object_for_postgres(input_obj)
    assert result == expected_output


def test_null_byte_in_host_message(mq_create_or_update_host, db_get_host):
    """Integration test: NULL bytes in host data should be sanitized"""
    host = minimal_host(display_name="test\x00host", fqdn="example\x00.com")
    created_host = mq_create_or_update_host(host)

    retrieved_host = db_get_host(created_host.id)
    assert "\x00" not in retrieved_host.display_name
    assert retrieved_host.display_name == "testhost"
    assert "\x00" not in retrieved_host.fqdn
    assert retrieved_host.fqdn == "example.com"


def test_host_account_using_mq(mq_create_or_update_host, db_get_host, db_get_hosts):
    host = minimal_host(account=SYSTEM_IDENTITY["account_number"], fqdn="d44533.foo.redhat.co")
    host.account = SYSTEM_IDENTITY["account_number"]

    created_host = mq_create_or_update_host(host)
    assert db_get_host(created_host.id).account == SYSTEM_IDENTITY["account_number"]

    first_batch = db_get_hosts([created_host.id])

    # verify that the two hosts vars are pointing to the same resource.
    same_host = mq_create_or_update_host(host)

    second_batch = db_get_hosts([created_host.id, same_host.id])

    assert created_host.id == same_host.id
    assert len(first_batch.all()) == len(second_batch.all())


@pytest.mark.usefixtures("db_get_host")
def test_change_owner_id_of_existing_host(mq_create_or_update_host):
    expected_insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"], insights_id=expected_insights_id, fqdn="d44533.foo.redhat.co"
    )

    created_key, created_event, created_headers = mq_create_or_update_host(host, return_all_data=True)
    assert created_event["host"]["account"] == SYSTEM_IDENTITY["account_number"]
    assert created_event["host"]["system_profile"]["owner_id"] == OWNER_ID

    NEW_CN = "137c9d58-941c-4bb9-9426-7879a367c23b"
    new_id = deepcopy(SYSTEM_IDENTITY)
    new_id["system"]["cn"] = NEW_CN
    platform_metadata = get_platform_metadata(new_id)

    host = minimal_host(
        account=new_id["account_number"],
        insights_id=expected_insights_id,
        fqdn="d44533.foo.redhat.co",
        system_profile={"owner_id": NEW_CN},
    )

    updated_key, updated_event, updated_headers = mq_create_or_update_host(
        host, platform_metadata=platform_metadata, return_all_data=True
    )
    assert updated_key == created_key
    assert updated_event["host"]["system_profile"]["owner_id"] == NEW_CN


@pytest.mark.usefixtures("db_get_host")
def test_owner_id_present_in_existing_host_but_missing_from_payload(mq_create_or_update_host):
    expected_insights_id = generate_uuid()
    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        display_name="test_host",
        insights_id=expected_insights_id,
        system_profile={"owner_id": OWNER_ID},
        reporter="puptoo",
    )

    created_key, created_event, created_headers = mq_create_or_update_host(host, return_all_data=True)
    assert created_event["host"]["display_name"] == "test_host"
    assert created_event["host"]["system_profile"]["owner_id"] == OWNER_ID

    NEW_CN = "137c9d58-941c-4bb9-9426-7879a367c23b"

    # use new identity with a new 'CN'
    new_id = deepcopy(SYSTEM_IDENTITY)
    new_id["system"]["cn"] = NEW_CN
    platform_metadata = get_platform_metadata(new_id)

    host = minimal_host(insights_id=expected_insights_id, display_name="better_test_host", reporter="puptoo")

    updated_key, updated_event, updated_headers = mq_create_or_update_host(
        host, platform_metadata=platform_metadata, return_all_data=True
    )
    # explicitly test the posted event
    assert updated_key == created_key
    assert updated_event["host"]["system_profile"]["owner_id"] == NEW_CN
    assert updated_event["host"]["display_name"] == "better_test_host"


@pytest.mark.parametrize(
    "user",
    (
        {"user": {"email": "tuser@redhat.com", "first_name": "test"}},
        {"user": {"email": "tuser@redhat.com"}},
        {"user": {"first_name": "test"}},
        {"user": {}},
        {},
    ),
)
def test_create_host_by_user_with_missing_details(mq_create_or_update_host, db_get_host, user):
    user_id = deepcopy(USER_IDENTITY)
    del user_id["user"]
    user_id.update(user)
    input_host = minimal_host(account=user_id["account_number"])

    created_host = mq_create_or_update_host(input_host)
    # find the just created host from the DB
    host_from_db = db_get_host(created_host.id)

    assert created_host.id == str(host_from_db.id)


@pytest.mark.usefixtures("event_datetime_mock")
def test_create_invalid_host_produces_message(mocker, mq_create_or_update_host):
    insights_id = generate_uuid()
    system_profile = valid_system_profile()
    mock_notification_event_producer = mocker.Mock()

    host = minimal_host(
        account=SYSTEM_IDENTITY["account_number"],
        insights_id=insights_id,
        system_profile=system_profile,
    )

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host, notification_event_producer=mock_notification_event_producer)
    mock_notification_event_producer.write_event.assert_called_once()


def test_groups_not_overwritten_for_existing_hosts(
    mq_create_or_update_host, db_get_hosts_for_group, db_create_group_with_hosts
):
    # Create a group with a host in it;
    # Modify one value on the host and update via MQ;
    # Assert that the modified field is changed & the "groups" field is unchanged
    group = db_create_group_with_hosts("existing_group", 1)
    host = db_get_hosts_for_group(group.id)[0]
    group_id = str(group.id)
    host_id = str(host.id)

    update_data = minimal_host(insights_id=str(host.insights_id), ansible_host="updated.ansible.host")
    created_key, created_event, _ = mq_create_or_update_host(update_data, return_all_data=True)

    assert created_key == host_id
    assert created_event["host"]["ansible_host"] == "updated.ansible.host"
    assert created_event["host"]["groups"][0]["id"] == group_id

    retrieved_host = db_get_hosts_for_group(group.id)[0]
    assert retrieved_host.groups[0]["ungrouped"] is False


def test_batch_mq_do_dedup_within_batch(
    mocker: MockerFixture,
    event_producer: EventProducer,
    flask_app: FlaskApp,
    db_get_hosts_by_subman_id: Callable[[str], list[Host]],
    api_get,
):
    """This test sends 2 kafka payloads for the same host in the same MQ batch and checks that
    HBI applies dedup logic for messages within the same batch and doesn't create duplicates.
    """
    subman_id = generate_uuid()
    insights_id = generate_uuid()
    rhc_client_id = generate_uuid()
    rhc_config_state = generate_uuid()
    host1 = minimal_host(
        subscription_manager_id=subman_id,
        insights_id=insights_id,
        fqdn=generate_random_string(),
        reporter="puptoo",
        system_profile={"rhc_client_id": rhc_client_id},
    ).data()
    host2 = minimal_host(
        subscription_manager_id=subman_id,
        insights_id=insights_id,
        satellite_id=generate_uuid(),
        reporter="cloud-connector",
        system_profile={"rhc_config_state": rhc_config_state},
    ).data()

    msgs = [json.dumps(wrap_message(host, "add_host", get_platform_metadata())) for host in (host1, host2)]

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=2,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
        ),
    )

    fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage(message=msg) for msg in msgs]]})

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=(False, True)))

    # Check that only 1 host was created and it contains data from both messages
    db_hosts = db_get_hosts_by_subman_id(subman_id)
    assert len(db_hosts) == 1
    assert db_hosts[0].fqdn == host1["fqdn"]
    assert db_hosts[0].subscription_manager_id == host2["subscription_manager_id"]
    assert str(db_hosts[0].satellite_id) == host2["satellite_id"]
    assert set(db_hosts[0].per_reporter_staleness) == {"puptoo", "cloud-connector"}
    assert str(db_hosts[0].static_system_profile.rhc_client_id) == rhc_client_id
    assert str(db_hosts[0].static_system_profile.rhc_config_state) == rhc_config_state
    status, response = api_get(build_hosts_url(query=f"?insights_id={insights_id}"))
    assert status == 200
    assert len(response["results"]) == 1
    assert response["results"][0]["id"] == str(db_hosts[0].id)
    assert set(response["results"][0]["per_reporter_staleness"]) == {"puptoo", "cloud-connector"}
    status, response = api_get(build_system_profile_url(str(db_hosts[0].id)))
    assert status == 200
    assert response["results"][0]["system_profile"]["rhc_client_id"] == rhc_client_id
    assert response["results"][0]["system_profile"]["rhc_config_state"] == rhc_config_state


def test_batch_mq_two_different_hosts(
    mocker: MockerFixture,
    event_producer: EventProducer,
    flask_app: FlaskApp,
    db_get_hosts_by_display_name: Callable[[str], list[Host]],
    api_get,
):
    """This test sends 2 kafka payloads for different hosts in one MQ batch and checks that
    2 different hosts are created.
    """
    display_name = generate_random_string()
    host1 = minimal_host(
        insights_id=generate_uuid(),
        subscription_manager_id=generate_uuid(),
        display_name=display_name,
    ).data()
    host2 = minimal_host(
        insights_id=generate_uuid(),
        subscription_manager_id=generate_uuid(),
        display_name=display_name,
    ).data()

    msgs = [json.dumps(wrap_message(host, "add_host", get_platform_metadata())) for host in (host1, host2)]

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=2,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
        ),
    )

    fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage(message=msg) for msg in msgs]]})

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=(False, True)))

    # Check that 2 different hosts have the same display_name
    db_hosts = db_get_hosts_by_display_name(display_name)
    assert len(db_hosts) == 2
    assert db_hosts[0].id != db_hosts[1].id
    assert db_hosts[0].subscription_manager_id != db_hosts[1].subscription_manager_id
    expected_insights_ids = {host1["insights_id"], host2["insights_id"]}
    assert {str(host.insights_id) for host in db_hosts} == expected_insights_ids
    assert {str(host.subscription_manager_id) for host in db_hosts} == {
        host1["subscription_manager_id"],
        host2["subscription_manager_id"],
    }
    status, response = api_get(build_hosts_url(query=f"?display_name={display_name}"))
    assert status == 200
    assert len(response["results"]) == 2
    assert {host["insights_id"] for host in response["results"]} == expected_insights_ids
    assert {host["id"] for host in response["results"]} == {str(host.id) for host in db_hosts}


def test_batch_mq_do_dedup_in_db(
    mocker: MockerFixture,
    event_producer: EventProducer,
    flask_app: FlaskApp,
    db_get_hosts_by_subman_id: Callable[[str], list[Host]],
    db_get_hosts_by_display_name: Callable[[str], list[Host]],
    mq_create_or_update_host,
    api_get,
):
    """This test sends 2 kafka payloads for different hosts in one MQ batch and checks that
    HBI falls back to do dedup on hosts in the DB if it can't find the host in already processed
    messages within the same batch.
    """
    subman_id = generate_uuid()
    display_name = generate_random_string()
    insights_id = generate_uuid()
    rhc_client_id = generate_uuid()
    rhc_config_state = generate_uuid()
    existing_host_data = minimal_host(
        subscription_manager_id=subman_id,
        insights_id=insights_id,
        fqdn=generate_random_string(),
        display_name=display_name,
        reporter="puptoo",
        system_profile={"rhc_client_id": rhc_client_id},
    )
    existing_host = mq_create_or_update_host(existing_host_data)

    msg_host1 = minimal_host(
        subscription_manager_id=generate_uuid(), insights_id=generate_uuid(), display_name=display_name
    ).data()
    msg_host2 = minimal_host(
        subscription_manager_id=subman_id,
        insights_id=insights_id,
        satellite_id=generate_uuid(),
        display_name=display_name,
        reporter="cloud-connector",
        system_profile={"rhc_config_state": rhc_config_state},
    ).data()

    msgs = [json.dumps(wrap_message(host, "add_host", get_platform_metadata())) for host in (msg_host1, msg_host2)]

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=2,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
        ),
    )

    fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage(message=msg) for msg in msgs]]})

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=(False, True)))

    # Check that 2 different hosts have the same display_name
    db_hosts = db_get_hosts_by_display_name(display_name)
    assert len(db_hosts) == 2
    expected_insights_ids = {insights_id, msg_host1["insights_id"]}
    assert {str(host.insights_id) for host in db_hosts} == expected_insights_ids
    assert len({host.id for host in db_hosts}) == 2
    status, response = api_get(build_hosts_url(query=f"?display_name={display_name}"))
    assert status == 200
    assert len(response["results"]) == 2
    assert {host["insights_id"] for host in response["results"]} == expected_insights_ids
    assert {host["id"] for host in response["results"]} == {str(host.id) for host in db_hosts}

    # Check that there is still only 1 host in DB with the same subman_id and it was properly updated
    db_hosts = db_get_hosts_by_subman_id(subman_id)
    assert len(db_hosts) == 1
    assert db_hosts[0].fqdn == existing_host.fqdn
    assert db_hosts[0].subscription_manager_id == msg_host2["subscription_manager_id"]
    assert str(db_hosts[0].id) == existing_host.id
    assert str(db_hosts[0].satellite_id) == msg_host2["satellite_id"]
    assert set(db_hosts[0].per_reporter_staleness) == {"puptoo", "cloud-connector"}
    assert str(db_hosts[0].static_system_profile.rhc_client_id) == rhc_client_id
    assert str(db_hosts[0].static_system_profile.rhc_config_state) == rhc_config_state
    original = next(host for host in response["results"] if host["id"] == existing_host.id)
    assert set(original["per_reporter_staleness"]) == {"puptoo", "cloud-connector"}
    status, response = api_get(build_system_profile_url(existing_host.id))
    assert status == 200
    assert response["results"][0]["system_profile"]["rhc_client_id"] == rhc_client_id
    assert response["results"][0]["system_profile"]["rhc_config_state"] == rhc_config_state


def test_batch_mq_three_hosts_and_org_keyed_update(mocker, flask_app, api_get):
    # The consumer deliberately ignores record keys; model an org-keyed record
    # rather than incorrectly putting the organization key in the JSON body.
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(mq_db_batch_max_messages=3, mq_db_batch_max_seconds=1),
    )
    hosts = [
        minimal_host(insights_id=generate_uuid(), display_name=f"batch-host-{index}").data() for index in range(3)
    ]
    records = []
    for index, host in enumerate(hosts):
        record = mocker.Mock(
            wraps=FakeMessage(message=json.dumps(wrap_message(host, platform_metadata=get_platform_metadata())))
        )
        record.key = mocker.Mock(return_value=SYSTEM_IDENTITY["org_id"].encode() if index == 0 else None)
        records.append(record)
    fake_consumer = mocker.Mock(**{"consume.return_value": records})
    producer = mocker.Mock()
    consumer = IngressMessageConsumer(fake_consumer, flask_app, producer, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=(False, True)))
    fake_consumer.consume.assert_called_once_with(num_messages=3, timeout=1)
    events = [json.loads(call.args[0]) for call in producer.write_event.call_args_list]
    assert len(events) == 3
    assert {event["host"]["insights_id"] for event in events} == {host["insights_id"] for host in hosts}
    assert len({event["host"]["id"] for event in events}) == 3
    for event in events:
        assert event["type"] == "created"
        status, response = api_get(build_hosts_url(query=f"?insights_id={event['host']['insights_id']}"))
        assert status == 200
        assert len(response["results"]) == 1
        assert response["results"][0]["id"] == event["host"]["id"]
        assert response["results"][0]["insights_id"] == event["host"]["insights_id"]

    original = next(event["host"] for event in events if event["host"]["insights_id"] == hosts[1]["insights_id"])
    hosts[1]["display_name"] = "org-keyed-replacement"
    record = mocker.Mock(
        wraps=FakeMessage(message=json.dumps(wrap_message(hosts[1], platform_metadata=get_platform_metadata())))
    )
    record.key = mocker.Mock(return_value=SYSTEM_IDENTITY["org_id"].encode())
    fake_consumer.consume.return_value = [record]
    producer.reset_mock()
    consumer.event_loop(mocker.Mock(side_effect=(False, True)))
    producer.write_event.assert_called_once()
    updated = json.loads(producer.write_event.call_args.args[0])
    assert updated["type"] == "updated"
    assert updated["host"]["id"] == original["id"]
    assert updated["host"]["display_name"] == "org-keyed-replacement"
    status, response = api_get(build_hosts_url(host_list_or_id=original["id"]))
    assert status == 200
    assert len(response["results"]) == 1
    assert response["results"][0]["id"] == original["id"]
    assert response["results"][0]["display_name"] == "org-keyed-replacement"


def test_batch_mq_graceful_rollback(mocker, flask_app):
    # Verifies that when the DB session runs into a StaleDataError, it's handled gracefully
    # with retry logic and the event loop continues processing instead of crashing the pod
    msg_list = []
    for _ in range(5):
        msg_list.append(json.dumps(wrap_message(minimal_host().data(), "add_host", get_platform_metadata())))

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=3,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
        ),
    )

    # Make it so the commit raises a StaleDataError on first batch, succeeds on retry, then succeeds on second batch
    commit_mock = mocker.patch(
        "app.queue.host_mq.db.session.commit",
        side_effect=[
            StaleDataError("Stale data"),  # First batch attempt 1
            None,  # First batch attempt 2 (retry succeeds)
            None,  # Second batch
            None,  # Extra for teardown
            None,
            None,
        ],
    )
    rollback_mock = mocker.patch("app.queue.host_mq.db.session.rollback")
    write_batch_patch = mocker.patch("app.queue.host_mq.write_message_batch")
    metrics_mock = mocker.patch("app.queue.host_mq.metrics.ingress_message_handler_failure.inc")

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg_list[i]) for i in range(3)],  # First batch (replayed on retry)
                [FakeMessage(message=msg_list[i]) for i in range(3, 5)],  # Second batch
                [],  # Exit
            ]
        }
    )
    consumer = IngressMessageConsumer(fake_consumer, flask_app, mocker.Mock(), mocker.Mock())

    # First iteration encounters StaleDataError, retries and succeeds
    # Second iteration should succeed
    # Third iteration exits (empty messages)
    consumer.event_loop(interrupt=mocker.Mock(side_effect=[False, False, False, True]))

    # Verify rollback was called when StaleDataError occurred
    assert rollback_mock.call_count >= 1
    # Verify the failure metric was incremented (once for the StaleDataError)
    assert metrics_mock.call_count == 1
    # Verify that the event loop continued and processed both batches successfully
    # (1 failed + 1 successful retry for first batch + 1 for second batch = at least 3)
    assert commit_mock.call_count >= 3
    # write_batch should be called for both batches (first batch succeeds on retry, second batch succeeds)
    assert write_batch_patch.call_count == 2
    # First batch consumed once (retries replay in memory); second batch + empty exit poll.
    assert fake_consumer.consume.call_count == 3


@pytest.mark.parametrize(
    "workspace_type",
    (
        "standard",
        "ungrouped-hosts",
    ),
)
def test_workspace_mq_create(workspace_message_consumer_mock, workspace_type, db_get_group_by_id):
    workspace_id = generate_uuid()
    workspace_name = "test-kessel-workspace"
    workspace_created = "2025-01-15T12:00:00+00:00"
    workspace_modified = "2025-01-15T13:00:00+00:00"
    message = generate_kessel_workspace_message(
        "create",
        str(workspace_id),
        workspace_name,
        workspace_type,
        created=workspace_created,
        modified=workspace_modified,
    )

    workspace_message_consumer_mock.handle_message(json.dumps(message))
    found_group = db_get_group_by_id(workspace_id)

    assert found_group.name == workspace_name
    assert found_group.ungrouped == (workspace_type == "ungrouped-hosts")
    assert found_group.created_on == datetime.fromisoformat(workspace_created)
    assert found_group.modified_on == datetime.fromisoformat(workspace_modified)


@pytest.mark.parametrize(
    "workspace_type",
    (
        "standard",
        "ungrouped-hosts",
    ),
)
@pytest.mark.parametrize("ungrouped", (True, False))
def test_workspace_mq_create_already_exists(
    db_create_group, workspace_message_consumer_mock, db_get_group_by_id, workspace_type, ungrouped
):
    original_workspace_name = "Existing Group"

    # Create a group
    workspace_id = db_create_group("Existing Group", ungrouped=ungrouped).id

    # Generate a workspace message with the same ID
    message = generate_kessel_workspace_message("create", str(workspace_id), "test-kessel-workspace", workspace_type)

    workspace_message_consumer_mock.handle_message(json.dumps(message))
    found_group = db_get_group_by_id(workspace_id)

    assert found_group.name == original_workspace_name
    assert found_group.ungrouped == ungrouped


def test_workspace_mq_create_foreign_key_violation(monkeypatch, workspace_message_consumer_mock):
    # Generate a workspace message that would trigger a foreign key violation
    message = generate_kessel_workspace_message(
        "create", "nonexistent_foreign_key", "test-kessel-workspace", "standard"
    )
    # Monkeypatch the consumer to raise an IntegrityError simulating a foreign key violation
    monkeypatch.setattr(
        workspace_message_consumer_mock,
        "handle_message",
        lambda _: (_ for _ in ()).throw(IntegrityError("Foreign key violation", None, None)),
    )
    # Verify that the IntegrityError propagates (or, optionally, that logging is used appropriately)
    import pytest

    with pytest.raises(IntegrityError) as exc_info:
        workspace_message_consumer_mock.handle_message(json.dumps(message))
    assert "Foreign key violation" in str(exc_info.value)


@pytest.mark.parametrize("num_hosts", (0, 3))
def test_workspace_mq_delete(
    db_create_group_with_hosts, db_get_group_by_id, db_get_hosts_for_group, num_hosts, flask_app, mocker
):
    mock_event_producer = mocker.Mock()
    consumer = WorkspaceMessageConsumer(mocker.Mock(), flask_app, mock_event_producer, mocker.Mock())

    workspace_name = "kessel-deletable-workspace"
    workspace_id = db_create_group_with_hosts(workspace_name, num_hosts).id
    host_id_list = [str(host.id) for host in db_get_hosts_for_group(workspace_id)]
    message = generate_kessel_workspace_message("delete", str(workspace_id), workspace_name)

    consumer.handle_message(json.dumps(message))

    # Make sure the group was deleted
    assert not db_get_group_by_id(workspace_id)

    # Assert MQ messages were produced for hosts putting them in the ungrouped group
    assert mock_event_producer.write_event.call_count == num_hosts
    for call_arg in mock_event_producer.write_event.call_args_list:
        event = json.loads(call_arg[0][0])
        host = event["host"]
        assert host["id"] in host_id_list
        assert len(host["groups"]) == 1
        assert host["groups"][0]["ungrouped"] is True


def test_workspace_mq_delete_non_empty(
    workspace_message_consumer_mock,
    db_create_group_with_hosts,
    db_get_group_by_id,
    db_get_hosts_for_group,
    db_get_groups_for_host,
):
    workspace_name = "kessel-deletable-workspace"
    group = db_create_group_with_hosts(workspace_name, 3)
    workspace_id = str(group.id)
    host_id_list = [host.id for host in db_get_hosts_for_group(workspace_id)]

    message = generate_kessel_workspace_message("delete", workspace_id, workspace_name)
    workspace_message_consumer_mock.handle_message(json.dumps(message))

    # The group should no longer exist
    assert not db_get_group_by_id(workspace_id)

    # The hosts should now be in the "ungrouped" group
    assert db_get_groups_for_host(host_id_list[0])[0].ungrouped
    assert db_get_groups_for_host(host_id_list[1])[0].ungrouped
    assert db_get_groups_for_host(host_id_list[2])[0].ungrouped


def test_workspace_mq_delete_with_host_deleted_mid_process(
    workspace_message_consumer_mock,
    db_create_group_with_hosts,
    db_get_group_by_id,
    db_get_hosts_for_group,
    db_get_groups_for_host,
):
    """
    Test that workspace deletion handles the race condition where a host is deleted
    between when we query for group members and when we try to add them to ungrouped.
    This simulates the ForeignKeyViolation error in the issue.
    """
    workspace_name = "kessel-deletable-workspace-race"
    group = db_create_group_with_hosts(workspace_name, 3)
    workspace_id = str(group.id)
    hosts = db_get_hosts_for_group(workspace_id)
    host_id_list = [host.id for host in hosts]

    # Delete one of the hosts before the workspace delete processes
    # This simulates the race condition where the host is deleted mid-process
    host_to_delete = hosts[1]
    db.session.delete(host_to_delete)
    db.session.commit()

    message = generate_kessel_workspace_message("delete", workspace_id, workspace_name)
    # This should not raise a ForeignKeyViolation error
    workspace_message_consumer_mock.handle_message(json.dumps(message))

    # The group should no longer exist
    assert not db_get_group_by_id(workspace_id)

    # The remaining hosts should now be in the "ungrouped" group
    assert db_get_groups_for_host(host_id_list[0])[0].ungrouped
    # host_id_list[1] was deleted, so skip it
    assert db_get_groups_for_host(host_id_list[2])[0].ungrouped


def test_workspace_bulk_topic_uses_workspace_consumer():
    """The outbox.event.workspace and workspace-bulk topics should be mapped to WorkspaceMessageConsumer."""
    application = create_app(RuntimeEnvironment.SERVICE)
    config = application.app.config["INVENTORY_CONFIG"]

    topic_to_hbi_consumer = build_topic_to_consumer_map(config)

    assert config.workspaces_topic is not None
    assert topic_to_hbi_consumer[config.workspaces_topic] is WorkspaceMessageConsumer

    assert config.workspaces_bulk_topic is not None
    assert topic_to_hbi_consumer[config.workspaces_bulk_topic] is WorkspaceMessageConsumer


@pytest.mark.parametrize(
    "workspace_type",
    (
        "standard",
        "ungrouped-hosts",
    ),
)
def test_workspace_bulk_mq_create(workspace_message_consumer_mock, workspace_type, db_get_group_by_id):
    """Bulk workspace consumer processes create events the same as the regular consumer."""
    workspace_id = generate_uuid()
    workspace_name = "bulk-workspace"
    workspace_created = "2025-01-15T12:00:00+00:00"
    workspace_modified = "2025-01-15T13:00:00+00:00"
    message = generate_kessel_workspace_message(
        "create",
        str(workspace_id),
        workspace_name,
        workspace_type,
        created=workspace_created,
        modified=workspace_modified,
    )

    workspace_message_consumer_mock.handle_message(json.dumps(message))
    found_group = db_get_group_by_id(workspace_id)

    assert found_group.name == workspace_name
    assert found_group.ungrouped == (workspace_type == "ungrouped-hosts")
    assert found_group.created_on == datetime.fromisoformat(workspace_created)
    assert found_group.modified_on == datetime.fromisoformat(workspace_modified)


def test_workspace_bulk_mq_batch_creates(workspace_message_consumer_mock, db_get_group_by_id):
    """Multiple workspace create events processed in sequence (simulating a batch)."""
    workspace_ids = [generate_uuid() for _ in range(5)]
    for i, ws_id in enumerate(workspace_ids):
        message = generate_kessel_workspace_message("create", str(ws_id), f"bulk-workspace-{i}")
        workspace_message_consumer_mock.handle_message(json.dumps(message))

    for i, ws_id in enumerate(workspace_ids):
        found_group = db_get_group_by_id(ws_id)
        assert found_group is not None
        assert found_group.name == f"bulk-workspace-{i}"


def test_workspace_bulk_mq_create_duplicate_skips(
    db_create_group, workspace_message_consumer_mock, db_get_group_by_id
):
    """Duplicate workspace create events are silently skipped."""
    workspace_id = db_create_group("bulk-workspace-original").id

    duplicate_message = generate_kessel_workspace_message("create", str(workspace_id), "bulk-workspace-duplicate")
    workspace_message_consumer_mock.handle_message(json.dumps(duplicate_message))

    found_group = db_get_group_by_id(workspace_id)
    assert found_group.name == "bulk-workspace-original"


def test_workspace_bulk_mq_duplicate_does_not_rollback_prior_creates(
    db_create_group, workspace_message_consumer_mock, db_get_group_by_id
):
    """A duplicate create must not roll back new groups created earlier in the same batch/transaction."""
    existing_group = db_create_group("pre-existing-workspace")

    new_workspace_id = generate_uuid()
    new_message = generate_kessel_workspace_message("create", new_workspace_id, "new-workspace")
    workspace_message_consumer_mock.handle_message(json.dumps(new_message))

    duplicate_message = generate_kessel_workspace_message("create", str(existing_group.id), "duplicate-workspace-name")
    workspace_message_consumer_mock.handle_message(json.dumps(duplicate_message))

    db.session.commit()

    assert db_get_group_by_id(new_workspace_id) is not None
    assert db_get_group_by_id(new_workspace_id).name == "new-workspace"

    assert db_get_group_by_id(existing_group.id).name == "pre-existing-workspace"


@pytest.mark.parametrize(
    "processed_rows,event_type,should_notify",
    [
        ([], EventType.created, False),
        (
            [OperationResult(mock.Mock(id="workspace-id"), None, None, EventType.created, lambda: None)],
            EventType.created,
            True,
        ),
        (
            [OperationResult(mock.Mock(id="workspace-id"), None, None, None, lambda: None)],
            None,
            False,
        ),
    ],
)
def test_post_process_rows_commit_and_notify(
    processed_rows, event_type, should_notify, flask_app, event_producer, mocker
):
    consumer = WorkspaceMessageConsumer(mocker.Mock(), flask_app, event_producer, mocker.Mock())
    notify_mock = mock.Mock()
    # Patch _pg_notify_workspace
    with (
        mock.patch("app.queue.host_mq._pg_notify_workspace", notify_mock),
        mock.patch.object(consumer, "processed_rows", processed_rows),
    ):
        # Patch processed_rows to have .event_type attribute
        for row in processed_rows:
            row.event_type = event_type
        # Note: Commit is now handled by event_loop before post_process_rows is called
        consumer.post_process_rows()
        if should_notify:
            notify_mock.assert_called_once()
        else:
            notify_mock.assert_not_called()


def test_post_process_rows_stale_data_error(mocker, flask_app, event_producer):
    # This test verifies that StaleDataError during commit is handled in event_loop, not post_process_rows
    consumer = IngressMessageConsumer(mocker.Mock(), flask_app, event_producer, mocker.Mock())
    db_session_mock = mock.Mock()
    db_session_mock.commit.side_effect = StaleDataError("stale")
    write_batch_mock = mocker.patch("app.queue.host_mq.write_message_batch")

    processed_rows = [mock.Mock()]
    with (
        mock.patch("app.queue.host_mq.db.session", db_session_mock),
        mock.patch.object(consumer, "processed_rows", processed_rows),
    ):
        # StaleDataError should be raised from event_loop's commit, causing rollback
        with pytest.raises(StaleDataError):
            db_session_mock.commit()  # Simulates what event_loop does

        # Verify commit was attempted
        assert db_session_mock.commit.called
        # post_process_rows should not be called if commit fails
        write_batch_mock.assert_not_called()


def test_mq_serialize_host_per_reporter_staleness_datetime_format(flask_app, mocker, db_create_host):
    """
    MQ path: host with new-format per_reporter_staleness (value is datetime string)
    is serialized correctly in the event message (output is full dict per reporter).
    """
    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()

    host = db_create_host(
        extra_data={
            "subscription_manager_id": generate_uuid(),
            "reporter": "puptoo",
            "org_id": USER_IDENTITY["org_id"],
        }
    )
    # Ensure host is fully loaded in session state (avoids expired state when
    # before_update runs on flush so flag_modified(host, "modified_on") succeeds).
    _ = host.modified_on
    # New DB format: reporter value is the last_check_in datetime string only
    host.per_reporter_staleness = {"puptoo": "2024-06-15T10:00:00+00:00"}

    with flask_app.app.app_context():
        staleness_obj = get_staleness_obj(USER_IDENTITY["org_id"])

        result = OperationResult(
            row=host,
            pm={"request_id": "mq-test"},
            so=staleness_obj,
            et=EventType.created,
            sl=mocker.Mock(),
        )
        write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

        event_payload = json.loads(mock_event_producer.write_event.call_args[0][0])
        prs = event_payload["host"]["per_reporter_staleness"]["puptoo"]
        assert isinstance(prs, dict)
        assert prs["last_check_in"] == "2024-06-15T10:00:00+00:00"
        assert "stale_timestamp" in prs
        assert "stale_warning_timestamp" in prs
        assert "culled_timestamp" in prs


def test_write_message_batch_produces_all_messages(mocker):
    """Each event in the batch should be produced via write_add_update_event_message (flushed per-message)."""
    from uuid import uuid4

    from app.queue.host_mq import write_message_batch

    mock_event_producer = mocker.Mock()
    notification_producer = mocker.Mock()

    mock_write = mocker.patch(
        "app.queue.host_mq.write_add_update_event_message",
    )

    mock_results = []
    for _ in range(5):
        result = mocker.Mock()
        result.row.id = uuid4()
        mock_results.append(result)

    write_message_batch(mock_event_producer, notification_producer, mock_results)

    assert mock_write.call_count == 5
    assert mock_event_producer.flush.call_count == 0, (
        "flush() should not be called; each event is flushed via wait=True"
    )


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_rhsm_preserves_ansible_containers(reporter, mq_create_or_update_host, db_get_host):
    """RHSM reporter should preserve existing ansible containers it can't populate."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "ansible": {
                "controller_version": "1.0",
                "containers": [{"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    update_sp = {"workloads": {"ansible": {"controller_version": "2.0"}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        reporter=reporter,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["ansible"]["controller_version"] == "2.0"
    assert workloads["ansible"]["containers"] == [
        {"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}
    ]


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_rhsm_preserves_satellite_containers(reporter, mq_create_or_update_host, db_get_host):
    """RHSM reporter should preserve existing satellite containers it can't populate."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "satellite": {
                "type": "server",
                "version": "6.17.0",
                "containers": [{"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    update_sp = {"workloads": {"satellite": {"type": "server", "version": "6.18.0", "foremanctl_version": "3.0.0"}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        reporter=reporter,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["satellite"]["version"] == "6.18.0"
    assert workloads["satellite"]["foremanctl_version"] == "3.0.0"
    assert workloads["satellite"]["containers"] == [
        {"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}
    ]


@pytest.mark.usefixtures("event_datetime_mock")
def test_non_rhsm_clears_ansible_containers(mq_create_or_update_host, db_get_host):
    """Non-RHSM reporter sending ansible without containers should clear existing containers."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "ansible": {
                "controller_version": "1.0",
                "containers": [{"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    update_sp = {"workloads": {"ansible": {"controller_version": "2.0"}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["ansible"]["controller_version"] == "2.0"
    assert "containers" not in workloads["ansible"]


@pytest.mark.usefixtures("event_datetime_mock")
def test_non_rhsm_clears_satellite_containers(mq_create_or_update_host, db_get_host):
    """Non-RHSM reporter sending satellite without containers should clear existing containers."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "satellite": {
                "type": "server",
                "version": "6.17.0",
                "containers": [{"name": "foreman", "image": "quay.io/foreman/foreman:nightly", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    update_sp = {"workloads": {"satellite": {"type": "server", "version": "6.18.0"}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["satellite"]["version"] == "6.18.0"
    assert "containers" not in workloads["satellite"]


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_rhsm_explicit_empty_containers_wins(reporter, mq_create_or_update_host, db_get_host):
    """RHSM reporter explicitly sending empty containers should update to empty."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "ansible": {
                "controller_version": "1.0",
                "containers": [{"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    update_sp = {"workloads": {"ansible": {"controller_version": "2.0", "containers": []}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        reporter=reporter,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["ansible"]["controller_version"] == "2.0"
    assert workloads["ansible"]["containers"] == []


def test_write_delete_event_message_invalidates_cache_synchronously(mocker):
    from uuid import UUID

    mock_event_producer = mocker.Mock()
    mock_success_logger = mocker.Mock()
    mock_delete_cache = mocker.patch("app.queue.host_mq.delete_cached_system_keys")
    mocker.patch("app.queue.host_mq.build_event_and_headers", return_value=("event", {}))

    insights_id = generate_uuid()
    owner_id = generate_uuid()
    org_id = "test-org"

    static_sp = mocker.Mock()
    static_sp.owner_id = UUID(owner_id)

    host_row = mocker.NonCallableMock()
    host_row.id = UUID(generate_uuid())
    host_row.insights_id = UUID(insights_id)
    host_row.org_id = org_id
    host_row.reporter = "puptoo"
    host_row.static_system_profile = static_sp

    result = OperationResult(
        row=host_row,
        pm=None,
        so=None,
        et=EventType.delete,
        sl=mock_success_logger,
    )

    write_delete_event_message(mock_event_producer, result, initiated_by_frontend=False)

    mock_event_producer.write_event.assert_called_once()
    mock_delete_cache.assert_called_once_with(insights_id=insights_id, org_id=org_id, owner_id=owner_id)
    mock_success_logger.assert_called_once()


def test_write_delete_event_message_without_owner_id_skips_cache_invalidation(mocker):
    from uuid import UUID

    mock_event_producer = mocker.Mock()
    mock_success_logger = mocker.Mock()
    mock_delete_cache = mocker.patch("app.queue.host_mq.delete_cached_system_keys")
    mocker.patch("app.queue.host_mq.build_event_and_headers", return_value=("event", {}))

    insights_id = generate_uuid()
    org_id = "test-org"

    host_row = mocker.NonCallableMock(spec=["id", "insights_id", "org_id", "reporter", "static_system_profile"])
    host_row.id = UUID(generate_uuid())
    host_row.insights_id = UUID(insights_id)
    host_row.org_id = org_id
    host_row.reporter = "puptoo"
    host_row.static_system_profile = None

    result = OperationResult(
        row=host_row,
        pm=None,
        so=None,
        et=EventType.delete,
        sl=mock_success_logger,
    )

    write_delete_event_message(mock_event_producer, result, initiated_by_frontend=False)

    mock_event_producer.write_event.assert_called_once()
    mock_delete_cache.assert_not_called()
    mock_success_logger.assert_called_once()


@pytest.mark.parametrize(
    ("created", "flag_enabled", "insights_id", "owner_id", "expect_invalidate"),
    (
        (True, True, "11111111-1111-1111-1111-111111111111", "owner-id", True),
        (True, False, "11111111-1111-1111-1111-111111111111", "owner-id", False),
        (False, True, "11111111-1111-1111-1111-111111111111", "owner-id", False),
        (True, True, None, "owner-id", False),
        (True, True, "11111111-1111-1111-1111-111111111111", None, False),
    ),
)
def test_created_host_invalidates_only_owner_system_cache(
    mocker, created, flag_enabled, insights_id, owner_id, expect_invalidate
):
    mocker.patch("app.queue.host_mq.get_flag_value", return_value=flag_enabled)
    mocker.patch("app.queue.host_mq.system_cache_has_multiple_hosts", return_value=False)
    mock_delete_cache = mocker.patch("app.queue.host_mq.delete_cached_system_keys")
    mocker.patch("app.queue.host_mq.set_cached_system")

    cache_ingested_system(
        {"org_id": "org-id", "system_profile": {"owner_id": owner_id} if owner_id else {}},
        insights_id,
        created=created,
        groups=[],
    )

    if expect_invalidate:
        mock_delete_cache.assert_called_once_with(insights_id=insights_id, org_id="org-id", owner_id=owner_id)
    else:
        mock_delete_cache.assert_not_called()
