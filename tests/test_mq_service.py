import json
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from functools import partial

import marshmallow
import pytest
from sqlalchemy import null
from sqlalchemy.exc import OperationalError

from app import db
from app.auth.identity import Identity
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.models import MqHostSchema
from app.queue.event_producer import Topic
from app.queue.queue import _validate_json_object_for_utf8
from app.queue.queue import event_loop
from app.queue.queue import handle_message
from app.serialization import deserialize_host
from lib.host_repository import AddHostResult
from tests.helpers.mq_utils import assert_mq_host_data
from tests.helpers.mq_utils import expected_headers
from tests.helpers.mq_utils import wrap_message
from tests.helpers.system_profile_utils import INVALID_SYSTEM_PROFILES
from tests.helpers.system_profile_utils import mock_system_profile_specification
from tests.helpers.system_profile_utils import system_profile_specification
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import valid_system_profile


def test_event_loop_exception_handling(mocker, flask_app):
    """
    Test to ensure that an exception in message handler method does not cause the
    event loop to stop processing messages
    """
    fake_consumer = mocker.Mock()
    fake_consumer.poll.return_value = {"poll1": [mocker.Mock(), mocker.Mock(), mocker.Mock()]}

    fake_event_producer = None
    handle_message_mock = mocker.Mock(side_effect=[None, KeyError("blah"), None])
    event_loop(
        fake_consumer,
        flask_app,
        fake_event_producer,
        handler=handle_message_mock,
        interrupt=mocker.Mock(side_effect=(False, True)),
    )
    assert handle_message_mock.call_count == 3


def test_handle_message_failure_invalid_json_message(mocker):
    invalid_message = "failure {} "

    mock_event_producer = mocker.Mock()

    with pytest.raises(json.decoder.JSONDecodeError):
        handle_message(invalid_message, mock_event_producer)

    mock_event_producer.assert_not_called()


def test_handle_message_failure_invalid_message_format(mocker):
    invalid_message = json.dumps({"operation": "add_host", "NOTdata": {}})  # Missing data field

    mock_event_producer = mocker.Mock()

    with pytest.raises(marshmallow.exceptions.ValidationError):
        handle_message(invalid_message, mock_event_producer)

    mock_event_producer.assert_not_called()


def test_handle_message_happy_path(mocker, event_datetime_mock, flask_app):
    expected_insights_id = generate_uuid()
    host_id = generate_uuid()
    timestamp_iso = event_datetime_mock.isoformat()

    mocker.patch(
        "app.queue.queue.add_host",
        return_value=(
            {"id": host_id, "insights_id": expected_insights_id},
            host_id,
            expected_insights_id,
            AddHostResult.created,
        ),
    )
    mock_event_producer = mocker.Mock()

    host = minimal_host(insights_id=expected_insights_id)
    message = wrap_message(host.data())
    handle_message(json.dumps(message), mock_event_producer)

    mock_event_producer.write_event.assert_called_once()

    assert json.loads(mock_event_producer.write_event.call_args[0][0]) == {
        "timestamp": timestamp_iso,
        "type": "created",
        "host": {"id": host_id, "insights_id": expected_insights_id},
        "platform_metadata": {},
        "metadata": {"request_id": "-1"},
    }


def test_shutdown_handler(mocker, flask_app):
    fake_consumer = mocker.Mock()
    fake_consumer.poll.return_value = {"poll1": [mocker.Mock(), mocker.Mock()]}

    fake_event_producer = None
    handle_message_mock = mocker.Mock(side_effect=[None, None])
    event_loop(
        fake_consumer,
        flask_app,
        fake_event_producer,
        handler=handle_message_mock,
        interrupt=mocker.Mock(side_effect=(False, True)),
    )
    fake_consumer.poll.assert_called_once()

    assert handle_message_mock.call_count == 2


def test_events_sent_to_correct_topic(mocker, flask_app, secondary_topic_enabled):
    host_id = generate_uuid()
    insights_id = generate_uuid()

    host = minimal_host(id=host_id, insights_id=insights_id)

    add_host = mocker.patch(
        "app.queue.queue.add_host", return_value=({"id": host_id}, host_id, insights_id, AddHostResult.created)
    )
    mock_event_producer = mocker.Mock()

    message = wrap_message(host.data())
    handle_message(json.dumps(message), mock_event_producer)

    # checking events sent to both egress and events topic
    assert mock_event_producer.write_event.call_count == 2
    assert mock_event_producer.write_event.call_args_list[0][0][3] == Topic.egress
    assert mock_event_producer.write_event.call_args_list[1][0][3] == Topic.events

    mock_event_producer.reset_mock()

    # for host update events
    add_host.return_value = ({"id": host_id}, host_id, insights_id, AddHostResult.updated)

    message["data"].update(stale_timestamp=(now() + timedelta(hours=26)).isoformat())
    handle_message(json.dumps(message), mock_event_producer)

    # checking events sent to both egress and events topic
    assert mock_event_producer.write_event.call_count == 2
    assert mock_event_producer.write_event.call_args_list[0][0][3] == Topic.egress
    assert mock_event_producer.write_event.call_args_list[1][0][3] == Topic.events


# Leaving this in as a reminder that we need to impliment this test eventually
# when the problem that it is supposed to test is fixed
# https://projects.engineering.redhat.com/browse/RHCLOUD-3503
# def test_handle_message_verify_threadctx_request_id_set_and_cleared(self):
#     # set the threadctx.request_id
#     # and clear it
#     pass


@pytest.mark.parametrize("display_name", ("\udce2\udce2", "\\udce2\\udce2", "\udce2\udce2\\udce2\\udce2"))
def test_handle_message_failure_invalid_surrogates(mocker, display_name):
    mocker.patch("app.queue.queue.build_event")
    add_host = mocker.patch("app.queue.queue.add_host", return_value=(mocker.MagicMock(), None))

    invalid_message = f'{{"operation": "", "data": {{"display_name": "hello{display_name}"}}}}'

    with pytest.raises(UnicodeError):
        handle_message(invalid_message, mocker.Mock())

    add_host.assert_not_called()


def test_handle_message_unicode_not_damaged(mocker, flask_app, subtests):
    mocker.patch("app.queue.queue.build_event")
    add_host = mocker.patch("app.queue.queue.add_host", return_value=(mocker.MagicMock(), None, None, None))

    operation_raw = "🧜🏿‍♂️"
    operation_escaped = json.dumps(operation_raw)[1:-1]

    messages = (
        f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_raw}", "account": "test"}}}}',
        f'{{"operation": "", "data": {{"display_name": "{operation_escaped}{operation_escaped}","account": "test"}}}}',
        f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_escaped}", "account": "test"}}}}',
    )

    for message in messages:
        with subtests.test(message=message):
            host_id = generate_uuid()
            add_host.reset_mock()
            add_host.return_value = ({"id": host_id}, host_id, None, AddHostResult.updated)
            handle_message(message, mocker.Mock())
            add_host.assert_called_once_with(
                {"display_name": f"{operation_raw}{operation_raw}", "account": "test"}, Identity(USER_IDENTITY)
            )


def test_handle_message_verify_metadata_pass_through(mq_create_or_update_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()

    host = minimal_host(id=host_id, insights_id=insights_id)
    metadata = {"request_id": generate_uuid(), "archive_url": "https://some.url"}

    key, event, headers = mq_create_or_update_host(host, platform_metadata=metadata, return_all_data=True)

    assert event["platform_metadata"] == metadata


def test_handle_message_verify_message_key_and_metadata_not_required(mocker, mq_create_or_update_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()

    host = minimal_host(id=host_id, insights_id=insights_id)
    host_data = host.data()

    mocker.patch("app.queue.queue.add_host", return_value=(host_data, host_id, insights_id, AddHostResult.created))

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert key == host_id
    assert event["host"] == host_data


@pytest.mark.parametrize("add_host_result", AddHostResult)
def test_handle_message_verify_message_headers(mocker, add_host_result, mq_create_or_update_host):
    host_id = generate_uuid()
    insights_id = generate_uuid()
    request_id = generate_uuid()

    host = minimal_host(id=host_id, insights_id=insights_id)

    mocker.patch("app.queue.queue.add_host", return_value=(host.data(), host_id, insights_id, add_host_result))

    key, event, headers = mq_create_or_update_host(
        host, platform_metadata={"request_id": request_id}, return_all_data=True
    )

    assert headers == expected_headers(add_host_result.name, request_id, insights_id)


def test_add_host_simple(event_datetime_mock, mq_create_or_update_host):
    """
    Tests adding a host with some simple data
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = event_datetime_mock.isoformat()

    host = minimal_host(insights_id=expected_insights_id)

    expected_results = {
        "host": {**host.data()},
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }

    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


def test_add_host_with_system_profile(event_datetime_mock, mq_create_or_update_host):
    """
     Tests adding a host with message containing system profile
    """
    expected_insights_id = generate_uuid()
    expected_system_profile = valid_system_profile()
    timestamp_iso = event_datetime_mock.isoformat()

    host = minimal_host(insights_id=expected_insights_id, system_profile=expected_system_profile)

    expected_results = {
        "host": {**host.data()},
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


def test_add_host_with_tags(event_datetime_mock, mq_create_or_update_host):
    """
     Tests adding a host with message containing tags
    """
    expected_insights_id = generate_uuid()
    expected_tags = [
        {"namespace": "insights-client", "key": "key3", "value": "val3"},
        {"namespace": "satellite", "key": "prod", "value": None},
        {"namespace": "satellite", "key": "dev", "value": ""},
        {"namespace": "satellite", "key": "test"},
        {"namespace": "satellite", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]
    timestamp_iso = event_datetime_mock.isoformat()

    host = minimal_host(insights_id=expected_insights_id, tags=expected_tags)

    expected_results = {
        "host": {**host.data()},
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }
    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)

    assert len(event["host"]["tags"]) == len(expected_tags)


@pytest.mark.parametrize(
    "tag",
    [
        {"namespace": "NS", "key": "", "value": "val"},
        {"namespace": "a" * 256, "key": "key", "value": "val"},
        {"namespace": "NS", "key": "a" * 256, "value": "val"},
        {"namespace": "NS", "key": "key", "value": "a" * 256},
        {"namespace": "NS", "key": None, "value": "a" * 256},
        {"namespace": "NS", "value": "a" * 256},
    ],
)
def test_add_host_with_invalid_tags(tag, mq_create_or_update_host):
    """
     Tests adding a host with message containing invalid tags
    """
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, tags=[tag])

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


@pytest.mark.system_profile
def test_add_host_empty_keys_system_profile(mq_create_or_update_host):
    system_profile = {"disk_devices": [{"options": {"": "invalid"}}]}
    host = minimal_host(system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


@pytest.mark.system_profile
@pytest.mark.parametrize(("system_profile",), ((system_profile,) for system_profile in INVALID_SYSTEM_PROFILES))
def test_add_host_long_strings_system_profile(mq_create_or_update_host, system_profile):
    host = minimal_host(system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


@pytest.mark.system_profile
@pytest.mark.parametrize(("baseurl",), (("http://www.example.com",), ("x" * 2049,)))
def test_add_host_yum_repos_baseurl_system_profile(mq_create_or_update_host, db_get_host, baseurl):
    yum_repo = {"name": "repo1", "gpgcheck": True, "enabled": True}
    host_to_create = minimal_host(system_profile={"yum_repos": [{**yum_repo, "baseurl": baseurl}]})
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {"yum_repos": [yum_repo]}


@pytest.mark.system_profile
def test_add_host_type_coercion_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(system_profile={"number_of_cpus": "1"})
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)

    assert created_host_from_db.system_profile_facts == {"number_of_cpus": 1}


@pytest.mark.system_profile
def test_add_host_key_filtering_system_profile(mq_create_or_update_host, db_get_host):
    host_to_create = minimal_host(
        system_profile={
            "number_of_cpus": 1,
            "number_of_gpus": 2,
            "disk_devices": [{"options": {"uid": "0"}, "mount_options": {"ro": True}}],
        }
    )
    created_host_from_event = mq_create_or_update_host(host_to_create)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {
        "number_of_cpus": 1,
        "disk_devices": [{"options": {"uid": "0"}}],
    }


def test_add_host_not_marshmallow_system_profile(mocker, mq_create_or_update_host):
    mock_deserialize_host = partial(mocker.Mock, wraps=deserialize_host)
    mock = mocker.patch("app.serialization.deserialize_host", new_callable=mock_deserialize_host)

    host_to_create = minimal_host(system_profile={"number_of_cpus": 1})
    mq_create_or_update_host(host_to_create)
    mock.assert_called_once_with(mocker.ANY, MqHostSchema, None)

    assert type(MqHostSchema._declared_fields["system_profile"]) is not marshmallow.fields.Nested


def test_add_host_externalized_system_profile(mq_create_or_update_host):
    orig_spec = system_profile_specification()
    mock_spec = deepcopy(orig_spec)
    mock_spec["$defs"]["SystemProfile"]["properties"]["number_of_cpus"]["minimum"] = 2

    with mock_system_profile_specification(mock_spec):
        host_to_create = minimal_host(system_profile={"number_of_cpus": 1})
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host_to_create)


def test_add_host_with_owner_id(event_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests that owner_id in the system profile is ingested properly
    """
    owner_id = generate_uuid()
    host = minimal_host(system_profile={"owner_id": owner_id})
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {"owner_id": owner_id}


def test_add_host_with_owner_incorrect_format(event_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests that owner_id in the system profile is rejected if it's in the wrong format
    """
    owner_id = "Mike Wazowski"
    host = minimal_host(system_profile={"owner_id": owner_id})
    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


def test_add_host_with_operating_system(event_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests that operating_system in the system profile is ingested properly
    """
    operating_system = {"major": 5, "minor": 1, "name": "RHEL"}
    host = minimal_host(system_profile={"operating_system": operating_system})
    created_host_from_event = mq_create_or_update_host(host)
    created_host_from_db = db_get_host(created_host_from_event.id)
    assert created_host_from_db.system_profile_facts == {"operating_system": operating_system}


def test_add_host_with_operating_system_incorrect_format(event_datetime_mock, mq_create_or_update_host, db_get_host):
    """
    Tests that operating_system in the system profile is rejected if it's in the wrong format
    """
    operating_system_list = [
        {"major": "bananas", "minor": 1, "name": "RHEL"},
        {"major": 1, "minor": "oranges", "name": "RHEL"},
        {"major": 1, "minor": 1, "name": "UBUNTU"},
    ]
    for operating_system in operating_system_list:
        host = minimal_host(system_profile={"operating_system": operating_system})
        with pytest.raises(ValidationException):
            mq_create_or_update_host(host)


@pytest.mark.parametrize(
    "facts",
    (
        [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
    ),
)
def test_add_host_empty_keys_facts(facts, mq_create_or_update_host):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, facts=facts)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


@pytest.mark.parametrize("stale_timestamp", ("invalid", datetime.now().isoformat()))
def test_add_host_with_invalid_stale_timestamp(stale_timestamp, mq_create_or_update_host):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, stale_timestamp=stale_timestamp)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


def test_add_host_with_sap_system(event_datetime_mock, mq_create_or_update_host):
    expected_insights_id = generate_uuid()
    timestamp_iso = event_datetime_mock.isoformat()

    system_profile = valid_system_profile()
    system_profile["sap_system"] = True

    host = minimal_host(insights_id=expected_insights_id, system_profile=system_profile)

    expected_results = {
        "host": {**host.data()},
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.parametrize("tags", ({}, {"tags": None}, {"tags": []}, {"tags": {}}))
def test_add_host_with_no_tags(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}


def test_add_host_with_tag_list(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = [
        {"namespace": "satellite", "key": "key 1", "value": "value 1"},
        {"namespace": "satellite", "key": "key 2", "value": None},
        {"namespace": "insights-client", "key": "key 1", "value": None},
        {"namespace": "insights-client", "key": "key 1", "value": ""},
        {"namespace": "insights-client", "key": "key 1", "value": "value 2"},
    ]

    host = minimal_host(insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {"satellite": {"key 1": ["value 1"], "key 2": []}, "insights-client": {"key 1": ["value 2"]}}


def test_add_host_with_tag_dict(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = {
        "satellite": {"key 1": ["value 1"], "key 2": [], "key 3": None, "key 4": ["value 2", "", None]},
        "insights-client": None,
    }
    host = minimal_host(insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {"satellite": {"key 1": ["value 1"], "key 2": [], "key 3": [], "key 4": ["value 2"]}}


@pytest.mark.parametrize(
    "tags",
    (
        "string",
        123,
        123.4,
        [["namespace", "key", "value"]],
        [{"namespace": {"key": ["value"]}}],
        {"namespace": ["key", ["value"]]},
        {"namespace": [["key", "value"]]},
        {"namespace": ["key", "value"]},
        {"namespace": "key"},
        {"namespace": {"key": "value"}},
        {"namespace": {"key": {"value": "eulav"}}},
        {"namespace": {"key": [["value"]]}},
        {"namespace": {"key": [{"value": "eulav"}]}},
        {"namespace": {"key": [123]}},
        {"namespace": {"key": [123.4]}},
        {"namespace": {"": ["value"]}},
    ),
)
def test_add_host_with_invalid_tags_2(tags, mq_create_or_update_host):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, tags=tags)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host)


def test_update_display_name(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()

    host = minimal_host(display_name="test_host", insights_id=insights_id)
    mq_create_or_update_host(host)

    host = minimal_host(display_name="better_test_host", insights_id=insights_id)
    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.display_name == "better_test_host"


@pytest.mark.parametrize("reporter", ["yupana", "rhsm-conduit"])
def test_display_name_ignored_for_blacklisted_reporters(
    reporter, mq_create_or_update_host, db_get_host_by_insights_id
):
    """
    Tests the workaround for https://projects.engineering.redhat.com/browse/RHCLOUD-5954
    """
    insights_id = generate_uuid()
    host = minimal_host(display_name="test_host", insights_id=insights_id, reporter="puptoo")
    mq_create_or_update_host(host)

    host = minimal_host(display_name="yupana_test_host", insights_id=insights_id, reporter=reporter)
    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert record.display_name == "test_host"
    assert record.reporter == reporter


def test_add_tags_to_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        ([{"namespace": "satellite", "key": "key 1", "value": "value 1"}], {"satellite": {"key 1": ["value 1"]}}),
        (
            [{"namespace": "insights-client", "key": "key 1", "value": "value 2"}],
            {"satellite": {"key 1": ["value 1"]}, "insights-client": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_add_tags_to_host_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        ({"satellite": {"key 1": ["value 1"]}}, {"satellite": {"key 1": ["value 1"]}}),
        (
            {"insights-client": {"key 1": ["value 2"]}},
            {"satellite": {"key 1": ["value 1"]}, "insights-client": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("empty", (None, null()))
def test_add_tags_to_hosts_with_null_tags(empty, mq_create_or_update_host, db_get_host_by_insights_id, flask_app):
    # FIXME: Remove this test after migration to NOT NULL.
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id)
    mq_create_or_update_host(host)

    created_host = db_get_host_by_insights_id(insights_id)
    created_host.tags = empty

    db.session.add(created_host)
    db.session.commit()

    new_host = mq_create_or_update_host(host)
    assert [] == new_host.tags

    updated_host = db_get_host_by_insights_id(insights_id)
    assert {} == updated_host.tags


def test_replace_tags_of_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        (
            [
                {"namespace": "satellite", "key": "key 1", "value": "value 1"},
                {"namespace": "insights-client", "key": "key 2", "value": "value 2"},
            ],
            {"satellite": {"key 1": ["value 1"]}, "insights-client": {"key 2": ["value 2"]}},
        ),
        (
            [{"namespace": "satellite", "key": "key 4", "value": "value 4"}],
            {"satellite": {"key 4": ["value 4"]}, "insights-client": {"key 2": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_replace_host_tags_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {"satellite": {"key 1": ["value 1"]}, "insights-client": {"key 2": ["value 2"]}},
            {"satellite": {"key 1": ["value 1"]}, "insights-client": {"key 2": ["value 2"]}},
        ),
        (
            {"satellite": {"key 4": ["value 4"]}},
            {"satellite": {"key 4": ["value 4"]}, "insights-client": {"key 2": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_keep_host_tags_by_empty(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({"tags": {"satellite": {"key 1": ["value 1"]}}}, {"satellite": {"key 1": ["value 1"]}}),
        ({}, {"satellite": {"key 1": ["value 1"]}}),
        ({"tags": None}, {"satellite": {"key 1": ["value 1"]}}),
        ({"tags": []}, {"satellite": {"key 1": ["value 1"]}}),
        ({"tags": {}}, {"satellite": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, **message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("tags", ({}, {"tags": None}, {"tags": []}, {"tags": {}}))
def test_add_host_default_empty_dict(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, **tags)

    mq_create_or_update_host(host)

    record = db_get_host_by_insights_id(insights_id)

    assert {} == record.tags


def test_delete_host_tags(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {"satellite": {"key 1": ["val1"], "key 2": ["val2"]}, "insights-client": {"key 3": ["val3"]}},
            {"satellite": {"key 1": ["val1"], "key 2": ["val2"]}, "insights-client": {"key 3": ["val3"]}},
        ),
        ({"insights-client": None}, {"satellite": {"key 1": ["val1"], "key 2": ["val2"]}}),
        ({"satellite": {}}, {}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host)

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_add_host_stale_timestamp(event_datetime_mock, mq_create_or_update_host):
    """
    Tests to see if the host is successfully created with both reporter
    and stale_timestamp set.
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = event_datetime_mock.isoformat()
    stale_timestamp = now()

    host = minimal_host(insights_id=expected_insights_id, stale_timestamp=stale_timestamp.isoformat())

    expected_results = {
        "host": {
            **host.data(),
            "stale_warning_timestamp": (stale_timestamp + timedelta(weeks=1)).isoformat(),
            "culled_timestamp": (stale_timestamp + timedelta(weeks=2)).isoformat(),
        },
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }

    host_keys_to_check = ["reporter", "stale_timestamp", "culled_timestamp"]

    key, event, headers = mq_create_or_update_host(host, return_all_data=True)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@pytest.mark.parametrize("field_to_remove", ["stale_timestamp", "reporter"])
def test_add_host_stale_timestamp_missing_culling_fields(field_to_remove, mq_create_or_update_host):
    """
    tests to check the API will reject a host if it doesn’t have both
    culling fields. This should raise InventoryException.
    """
    host = minimal_host()
    delattr(host, field_to_remove)

    with pytest.raises(InventoryException):
        mq_create_or_update_host(host)


@pytest.mark.parametrize(
    "additional_data",
    (
        {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": ""},
        {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": None},
        {"stale_timestamp": "not a timestamp", "reporter": "puptoo"},
        {"stale_timestamp": "", "reporter": "puptoo"},
        {"stale_timestamp": None, "reporter": "puptoo"},
    ),
)
def test_add_host_stale_timestamp_invalid_culling_fields(additional_data, mq_create_or_update_host):
    """
    tests to check the API will reject a host if it doesn’t have both
    culling fields. This should raise InventoryException.
    """
    host = minimal_host(**additional_data)

    with pytest.raises(InventoryException):
        mq_create_or_update_host(host)


def test_valid_string_is_ok():
    _validate_json_object_for_utf8("naïve fiancé 👰🏻")
    assert True


def test_invalid_string_raises_exception():
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8("hello\udce2\udce2")


def test_dicts_are_traversed(mocker):
    mock = mocker.patch("app.queue.queue._validate_json_object_for_utf8")

    _validate_json_object_for_utf8({"first": "item", "second": "value"})

    mock.assert_has_calls(
        (mocker.call("first"), mocker.call("item"), mocker.call("second"), mocker.call("value")), any_order=True
    )


def test_lists_are_traversed(mocker):
    mock = mocker.patch("app.queue.queue._validate_json_object_for_utf8")

    _validate_json_object_for_utf8(["first", "second"])

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
        _validate_json_object_for_utf8(obj)


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
        _validate_json_object_for_utf8(obj)


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
        _validate_json_object_for_utf8(obj)


@pytest.mark.parametrize("value", (1.23, 0, 123, -123, True, False, None))
def test_other_values_are_ignored(value):
    _validate_json_object_for_utf8(value)
    assert True


def test_handle_message_with_different_account(mocker, flask_app, subtests):
    mocker.patch("app.queue.queue.build_event")
    add_host = mocker.patch("app.queue.queue.add_host", return_value=(mocker.MagicMock(), None, None, None))

    operation_raw = "🧜🏿‍♂️"
    messages = (
        f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_raw}", "account": "dummy"}}}}',
    )

    identity = Identity(SYSTEM_IDENTITY)
    identity.account_number = "dummy"

    for message in messages:
        with subtests.test(message=message):
            host_id = generate_uuid()
            add_host.reset_mock()
            add_host.return_value = ({"id": host_id}, host_id, None, AddHostResult.updated)
            handle_message(message, mocker.Mock())
            add_host.assert_called_once_with(
                {"display_name": f"{operation_raw}{operation_raw}", "account": "dummy"}, identity
            )


def test_host_account_using_mq(mq_create_or_update_host, api_get, db_get_host, db_get_hosts):
    host = minimal_host(fqdn="d44533.foo.redhat.co")
    host.account = "dummy"

    created_host = mq_create_or_update_host(host)
    assert db_get_host(created_host.id).account == "dummy"

    first_batch = db_get_hosts([created_host.id])

    # verify that the two hosts vars are pointing to the same resource.
    same_host = mq_create_or_update_host(host)

    second_batch = db_get_hosts([created_host.id, same_host.id])

    # update_existing_host() resturns the same host but with updated timestamp.
    created_host.updated = same_host.updated

    assert created_host.__dict__ == same_host.__dict__
    assert len(first_batch.all()) == len(second_batch.all())


def test_handle_message_side_effect(mocker, flask_app):
    fake_add_host = mocker.patch(
        "lib.host_repository.add_host", side_effect=OperationalError("DB Problem", "fake_param", "fake_orig")
    )

    expected_insights_id = generate_uuid()
    host = minimal_host(insights_id=expected_insights_id)

    fake_add_host.reset_mock()
    message = json.dumps(wrap_message(host.data()))

    with pytest.raises(expected_exception=OperationalError):
        handle_message(message, mocker.MagicMock())
