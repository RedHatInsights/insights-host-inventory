import json
import unittest
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import marshmallow
import pytest
from sqlalchemy import null

from app import db
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.queue.queue import _validate_json_object_for_utf8
from app.queue.queue import event_loop
from app.queue.queue import handle_message
from lib.host_repository import AddHostResult
from tests.test_utils import assert_mq_host_data
from tests.test_utils import generate_uuid
from tests.test_utils import minimal_host
from tests.test_utils import valid_system_profile


def test_event_loop_exception_handling(flask_app):
    """
    Test to ensure that an exception in message handler method does not cause the
    event loop to stop processing messages
    """
    fake_consumer = Mock()
    fake_consumer.poll.return_value = {"poll1": [Mock(), Mock(), Mock()]}

    fake_event_producer = None
    handle_message_mock = Mock(side_effect=[None, KeyError("blah"), None])
    event_loop(
        fake_consumer,
        flask_app,
        fake_event_producer,
        handler=handle_message_mock,
        shutdown_handler=Mock(**{"shut_down.side_effect": (False, True)}),
    )
    assert handle_message_mock.call_count == 3


def test_handle_message_failure_invalid_json_message():
    invalid_message = "failure {} "

    mock_event_producer = Mock()

    with pytest.raises(json.decoder.JSONDecodeError):
        handle_message(invalid_message, mock_event_producer)

    mock_event_producer.assert_not_called()


def test_handle_message_failure_invalid_message_format():
    invalid_message = json.dumps({"operation": "add_host", "NOTdata": {}})  # Missing data field

    mock_event_producer = Mock()

    with pytest.raises(marshmallow.exceptions.ValidationError):
        handle_message(invalid_message, mock_event_producer)

    mock_event_producer.assert_not_called()


@patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
def test_handle_message_happy_path(datetime_mock, handle_msg):
    expected_insights_id = generate_uuid()
    host_id = generate_uuid()
    timestamp_iso = datetime_mock.now.return_value.isoformat()
    message = {
        "operation": "add_host",
        "data": {
            "insights_id": expected_insights_id,
            "account": "0000001",
            "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
            "reporter": "test",
        },
    }

    with unittest.mock.patch("app.queue.queue.add_host") as m:
        m.return_value = ({"id": host_id, "insights_id": None}, AddHostResult.created)
        mock_event_producer = Mock()
        handle_msg(message, mock_event_producer)

        mock_event_producer.write_event.assert_called_once()

        assert json.loads(mock_event_producer.write_event.call_args[0][0]) == {
            "timestamp": timestamp_iso,
            "type": "created",
            "host": {"id": str(host_id), "insights_id": None},
            "platform_metadata": {},
            "metadata": {"request_id": "-1"},
        }


def test_shutdown_handler(flask_app):
    fake_consumer = Mock()
    fake_consumer.poll.return_value = {"poll1": [Mock(), Mock()]}

    fake_event_producer = None
    handle_message_mock = Mock(side_effect=[None, None])
    event_loop(
        fake_consumer,
        flask_app,
        fake_event_producer,
        handler=handle_message_mock,
        shutdown_handler=Mock(**{"shut_down.side_effect": (False, True)}),
    )
    fake_consumer.poll.assert_called_once()

    assert handle_message_mock.call_count == 2


# Leaving this in as a reminder that we need to impliment this test eventually
# when the problem that it is supposed to test is fixed
# https://projects.engineering.redhat.com/browse/RHCLOUD-3503
# def test_handle_message_verify_threadctx_request_id_set_and_cleared(self):
#     # set the threadctx.request_id
#     # and clear it
#     pass


@patch("app.queue.queue.build_event")
@patch("app.queue.queue.add_host", return_value=(MagicMock(), None))
@pytest.mark.parametrize("display_name", ("\udce2\udce2", "\\udce2\\udce2", "\udce2\udce2\\udce2\\udce2"))
def test_handle_message_failure_invalid_surrogates(add_host, build_event, display_name):
    invalid_message = f'{{"operation": "", "data": {{"display_name": "hello{display_name}"}}}}'

    with pytest.raises(UnicodeError):
        handle_message(invalid_message, Mock())

    add_host.assert_not_called()


@patch("app.queue.queue.build_event")
@patch("app.queue.queue.add_host", return_value=(MagicMock(), None))
def test_handle_message_unicode_not_damaged(add_host, build_event, flask_app, subtests):
    operation_raw = "🧜🏿‍♂️"
    operation_escaped = json.dumps(operation_raw)[1:-1]

    messages = (
        f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_raw}"}}}}',
        f'{{"operation": "", "data": {{"display_name": "{operation_escaped}{operation_escaped}"}}}}',
        f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_escaped}"}}}}',
    )
    for message in messages:
        with subtests.test(message=message):
            add_host.reset_mock()
            add_host.return_value = ({"id": generate_uuid()}, AddHostResult.updated)
            handle_message(message, Mock())
            add_host.assert_called_once_with({"display_name": f"{operation_raw}{operation_raw}"})


def test_handle_message_verify_metadata_pass_through(mq_create_or_update_host):
    host = minimal_host()
    metadata = {"request_id": generate_uuid(), "archive_url": "https://some.url"}

    key, event, headers = mq_create_or_update_host(host_data=host.data(), platform_metadata=metadata)

    assert event["platform_metadata"] == metadata


@patch("app.queue.queue.add_host")
def test_handle_message_verify_message_key_and_metadata_not_required(add_host, mq_create_or_update_host):
    host = minimal_host(id=generate_uuid())
    host_data = host.data()

    add_host.return_value = (host_data, AddHostResult.created)

    key, event, headers = mq_create_or_update_host(host_data=host.data())

    assert key == host_data["id"]
    assert event["host"] == host_data


@patch("app.queue.queue.add_host")
@pytest.mark.parametrize("add_host_result", AddHostResult)
def test_handle_message_verify_message_headers(add_host, add_host_result, mq_create_or_update_host):
    host = minimal_host(id=generate_uuid())

    add_host.return_value = (host.data(), add_host_result)

    key, event, headers = mq_create_or_update_host(host_data=host.data())

    assert headers == {"event_type": add_host_result.name}


@patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
def test_add_host_simple(datetime_mock, mq_create_or_update_host):
    """
    Tests adding a host with some simple data
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = datetime_mock.now.return_value.isoformat()

    host_data = {
        "display_name": "test_host",
        "insights_id": expected_insights_id,
        "account": "0000001",
        "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
        "reporter": "test",
    }

    expected_results = {"host": {**host_data}, "platform_metadata": {}, "timestamp": timestamp_iso, "type": "created"}

    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host_data)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
def test_add_host_with_system_profile(datetime_mock, mq_create_or_update_host):
    """
     Tests adding a host with message containing system profile
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = datetime_mock.now.return_value.isoformat()

    host_data = {
        "display_name": "test_host",
        "insights_id": expected_insights_id,
        "account": "0000001",
        "system_profile": valid_system_profile(),
        "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
        "reporter": "test",
    }

    expected_results = {"host": {**host_data}, "platform_metadata": {}, "timestamp": timestamp_iso, "type": "created"}

    host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

    key, event, headers = mq_create_or_update_host(host_data)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)


@patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
def test_add_host_with_tags(datetime_mock, mq_create_or_update_host):
    """
     Tests adding a host with message containing tags
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = datetime_mock.now.return_value.isoformat()

    host_data = {
        "display_name": "test_host",
        "insights_id": expected_insights_id,
        "account": "0000001",
        "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
        "reporter": "test",
        "tags": [
            {"namespace": "NS1", "key": "key3", "value": "val3"},
            {"namespace": "NS3", "key": "key2", "value": "val2"},
            {"namespace": "Sat", "key": "prod", "value": None},
            {"namespace": "Sat", "key": "dev", "value": ""},
            {"namespace": "Sat", "key": "test"},
            {"namespace": None, "key": "key", "value": "val1"},
            {"namespace": "", "key": "key", "value": "val4"},
            {"namespace": "null", "key": "key", "value": "val5"},
            {"namespace": None, "key": "only_key", "value": None},
            {"key": "just_key"},
            {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
        ],
    }

    expected_results = {"host": {**host_data}, "platform_metadata": {}, "timestamp": timestamp_iso, "type": "created"}
    host_keys_to_check = ["display_name", "insights_id", "account"]

    key, event, headers = mq_create_or_update_host(host_data)

    assert_mq_host_data(key, event, expected_results, host_keys_to_check)

    expected_tags = [
        {"namespace": "NS1", "key": "key3", "value": "val3"},
        {"namespace": "NS3", "key": "key2", "value": "val2"},
        {"namespace": "Sat", "key": "prod", "value": None},
        {"namespace": "Sat", "key": "dev", "value": None},
        {"namespace": "Sat", "key": "test", "value": None},
        {"namespace": None, "key": "key", "value": "val1"},
        {"namespace": None, "key": "key", "value": "val4"},
        {"namespace": None, "key": "key", "value": "val5"},
        {"namespace": None, "key": "only_key", "value": None},
        {"namespace": None, "key": "just_key", "value": None},
        {"namespace": " \t\n\r\f\v", "key": " \t\n\r\f\v", "value": " \t\n\r\f\v"},
    ]

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
        mq_create_or_update_host(host_data=host.data())


@patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
def test_add_host_empty_keys_system_profile(datetime_mock, mq_create_or_update_host):
    insights_id = generate_uuid()
    system_profile = {"disk_devices": [{"options": {"": "invalid"}}]}
    host = minimal_host(insights_id=insights_id, system_profile=system_profile)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host_data=host.data())


@patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
@pytest.mark.parametrize(
    "facts",
    (
        [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
        [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
    ),
)
def test_add_host_empty_keys_facts(datetime_mock, facts, mq_create_or_update_host):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, facts=facts)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host_data=host.data())


@patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
@pytest.mark.parametrize("stale_timestamp", ("invalid", datetime.now().isoformat()))
def test_add_host_with_invalid_stale_timestmap(datetime_mock, stale_timestamp, mq_create_or_update_host):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, stale_timestamp=stale_timestamp)

    with pytest.raises(ValidationException):
        mq_create_or_update_host(host_data=host.data())


@pytest.mark.parametrize("tags", ({}, {"tags": None}, {"tags": []}, {"tags": {}}))
def test_add_host_with_no_tags(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, **tags)

    mq_create_or_update_host(host_data=host.data())

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {}


def test_add_host_with_tag_list(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = [
        {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
        {"namespace": "namespace 1", "key": "key 2", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": None},
        {"namespace": "namespace 2", "key": "key 1", "value": ""},
        {"namespace": "namespace 2", "key": "key 1", "value": "value 2"},
        {"namespace": "", "key": "key 3", "value": "value 3"},
        {"namespace": None, "key": "key 3", "value": "value 4"},
        {"namespace": "null", "key": "key 3", "value": "value 5"},
    ]

    host = minimal_host(insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host_data=host.data())

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 3": ["value 3", "value 4", "value 5"]},
    }


def test_add_host_with_tag_dict(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    tags = {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": None},
        "namespace 2": {"key 1": ["value 2", "", None]},
        "namespace 3": None,
        "namespace 4": {},
        "null": {"key 4": ["value 3"]},
        "": {"key 4": ["value 4"]},
    }
    host = minimal_host(insights_id=insights_id, tags=tags)

    mq_create_or_update_host(host_data=host.data())

    record = db_get_host_by_insights_id(insights_id)

    assert record.tags == {
        "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": []},
        "namespace 2": {"key 1": ["value 2"]},
        "null": {"key 4": ["value 3", "value 4"]},
    }


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
        mq_create_or_update_host(host_data=host.data())


def test_update_display_name(mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()

    host = minimal_host(display_name="test_host", insights_id=insights_id)
    mq_create_or_update_host(host_data=host.data())

    host = minimal_host(display_name="better_test_host", insights_id=insights_id)
    mq_create_or_update_host(host_data=host.data())

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
    mq_create_or_update_host(host_data=host.data())

    host = minimal_host(display_name="yupana_test_host", insights_id=insights_id, reporter=reporter)
    mq_create_or_update_host(host_data=host.data())

    record = db_get_host_by_insights_id(insights_id)

    assert record.display_name == "test_host"
    assert record.reporter == reporter


def test_add_tags_to_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        ([{"namespace": "namespace 1", "key": "key 1", "value": "value 1"}], {"namespace 1": {"key 1": ["value 1"]}}),
        (
            [{"namespace": "namespace 2", "key": "key 1", "value": "value 2"}],
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_add_tags_to_host_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        ({"namespace 1": {"key 1": ["value 1"]}}, {"namespace 1": {"key 1": ["value 1"]}}),
        (
            {"namespace 2": {"key 1": ["value 2"]}},
            {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("empty", (None, null()))
def test_add_tags_to_hosts_with_null_tags(empty, mq_create_or_update_host, db_get_host_by_insights_id, flask_app):
    # FIXME: Remove this test after migration to NOT NULL.
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id)
    mq_create_or_update_host(host_data=host.data())

    created_host = db_get_host_by_insights_id(insights_id)
    created_host.tags = empty

    with flask_app.app_context():
        db.session.add(created_host)
        db.session.commit()

    key, event, headers = mq_create_or_update_host(host_data=host.data())
    assert [] == event["host"]["tags"]

    updated_host = db_get_host_by_insights_id(insights_id)
    assert {} == updated_host.tags


def test_replace_tags_of_host_by_list(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ([], {}),
        (
            [
                {"namespace": "namespace 1", "key": "key 1", "value": "value 1"},
                {"namespace": "namespace 2", "key": "key 2", "value": "value 2"},
                {"namespace": "null", "key": "key 3", "value": "value 3"},
            ],
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"namespace": "namespace 1", "key": "key 4", "value": "value 4"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            [{"key": "key 5", "value": "value 5"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
        (
            [{"namespace": None, "key": "key 6", "value": "value 6"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 6": ["value 6"]},
            },
        ),
        (
            [{"namespace": "", "key": "key 7", "value": "value 7"}],
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 7": ["value 7"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_replace_host_tags_by_dict(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"namespace 1": {"key 4": ["value 4"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 3": ["value 3"]},
            },
        ),
        (
            {"": {"key 5": ["value 5"]}},
            {
                "namespace 1": {"key 4": ["value 4"]},
                "namespace 2": {"key 2": ["value 2"]},
                "null": {"key 5": ["value 5"]},
            },
        ),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


def test_keep_host_tags_by_empty(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({"tags": {"namespace 1": {"key 1": ["value 1"]}}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": None}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": []}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"tags": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, **message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@pytest.mark.parametrize("tags", ({}, {"tags": None}, {"tags": []}, {"tags": {}}))
def test_add_host_default_empty_dict(tags, mq_create_or_update_host, db_get_host_by_insights_id):
    insights_id = generate_uuid()
    host = minimal_host(insights_id=insights_id, **tags)

    mq_create_or_update_host(host_data=host.data())

    record = db_get_host_by_insights_id(insights_id)

    assert {} == record.tags


def test_delete_host_tags(mq_create_or_update_host, db_get_host_by_insights_id, subtests):
    insights_id = generate_uuid()

    # Can't use parametrize here due to the data cleanup on each test run
    for message_tags, expected_tags in (
        ({}, {}),
        (
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
            {
                "namespace 1": {"key 1": ["value 1"]},
                "namespace 2": {"key 2": ["value 2"]},
                "namespace 3": {"key 3": ["value 3"]},
                "null": {"key 4": ["value 4"]},
            },
        ),
        (
            {"namespace 2": None, "namespace 3": {}},
            {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 4": ["value 4"]}},
        ),
        ({"null": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ({"null": {"key 5": ["value 5"]}}, {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 5": ["value 5"]}}),
        ({"": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
    ):
        with subtests.test(tags=message_tags):
            host = minimal_host(insights_id=insights_id, tags=message_tags)
            mq_create_or_update_host(host_data=host.data())

            record = db_get_host_by_insights_id(insights_id)

            assert expected_tags == record.tags


@patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
def test_add_host_stale_timestamp(datetime_mock, mq_create_or_update_host):
    """
    Tests to see if the host is succesfully created with both reporter
    and stale_timestamp set.
    """
    expected_insights_id = generate_uuid()
    timestamp_iso = datetime_mock.now.return_value.isoformat()
    stale_timestamp = datetime.now(timezone.utc)

    host_data = {
        "display_name": "test_host",
        "insights_id": expected_insights_id,
        "account": "0000001",
        "stale_timestamp": stale_timestamp.isoformat(),
        "reporter": "puptoo",
    }

    expected_results = {
        "host": {
            **host_data,
            "stale_warning_timestamp": (stale_timestamp + timedelta(weeks=1)).isoformat(),
            "culled_timestamp": (stale_timestamp + timedelta(weeks=2)).isoformat(),
        },
        "platform_metadata": {},
        "timestamp": timestamp_iso,
        "type": "created",
    }

    host_keys_to_check = ["reporter", "stale_timestamp", "culled_timestamp"]

    key, event, headers = mq_create_or_update_host(host_data)

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
        mq_create_or_update_host(host_data=host.data())


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
        mq_create_or_update_host(host_data=host.data())


def test_valid_string_is_ok():
    _validate_json_object_for_utf8("naïve fiancé 👰🏻")
    assert True


def test_invalid_string_raises_exception():
    with pytest.raises(UnicodeEncodeError):
        _validate_json_object_for_utf8("hello\udce2\udce2")


@patch("app.queue.queue._validate_json_object_for_utf8")
def test_dicts_are_traversed(mock):
    _validate_json_object_for_utf8({"first": "item", "second": "value"})
    mock.assert_has_calls((call("first"), call("item"), call("second"), call("value")), any_order=True)


@patch("app.queue.queue._validate_json_object_for_utf8")
def test_lists_are_traversed(mock):
    _validate_json_object_for_utf8(["first", "second"])
    mock.assert_has_calls((call("first"), call("second")), any_order=True)


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
