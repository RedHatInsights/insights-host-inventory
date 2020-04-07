import json
import unittest
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest import main
from unittest import TestCase
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import marshmallow

from app import create_app
from app import db
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.queue.ingress import _validate_json_object_for_utf8
from app.queue.ingress import event_loop
from app.queue.ingress import handle_message
from lib.host_repository import AddHostResults
from test_utils import rename_host_table_and_indexes
from test_utils import valid_system_profile


class FakeKafkaMessage:
    value = None

    def __init__(self, message):
        self.value = message


class MockEventProducer:
    def __init__(self):
        self.event = None
        self.key = None

    def write_event(self, event, key):
        self.event = event
        self.key = key


class MQServiceBaseTestCase(TestCase):
    def setUp(self):
        """
        Creates the application and a test client to make requests.
        """
        self.app = create_app(config_name="testing")


class MQServiceTestCase(MQServiceBaseTestCase):
    def test_event_loop_exception_handling(self):
        """
        Test to ensure that an exception in message handler method does not cause the
        event loop to stop processing messages
        """
        # fake_consumer = [FakeKafkaMessage("blah"), FakeKafkaMessage("fred"), FakeKafkaMessage("ugh")]
        fake_consumer = [Mock(), Mock(), Mock()]
        fake_event_producer = None

        handle_message_mock = Mock(side_effect=[None, KeyError("blah"), None])
        event_loop(fake_consumer, self.app, fake_event_producer, handler=handle_message_mock)

        self.assertEqual(handle_message_mock.call_count, 3)

    def test_handle_message_failure_invalid_json_message(self):
        invalid_message = "failure {} "
        mock_event_producer = Mock()

        with self.assertRaises(json.decoder.JSONDecodeError):
            handle_message(invalid_message, mock_event_producer)

        mock_event_producer.assert_not_called()

    def test_handle_message_failure_invalid_message_format(self):
        invalid_message = json.dumps({"operation": "add_host", "NOTdata": {}})  # Missing data field

        mock_event_producer = Mock()

        with self.assertRaises(marshmallow.exceptions.ValidationError):
            handle_message(invalid_message, mock_event_producer)

        mock_event_producer.assert_not_called()

    @patch("app.queue.egress.datetime", **{"now.return_value": datetime.now()})
    def test_handle_message_happy_path(self, datetime_mock):
        expected_insights_id = str(uuid.uuid4())
        host_id = uuid.uuid4()
        timestamp_iso = datetime_mock.now.return_value.replace(tzinfo=timezone.utc).isoformat()
        message = {
            "operation": "add_host",
            "data": {
                "insights_id": expected_insights_id,
                "account": "0000001",
                "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
                "reporter": "test",
            },
        }
        with self.app.app_context():
            with unittest.mock.patch("app.queue.ingress.host_repository.add_host") as m:
                m.return_value = ({"id": host_id, "insights_id": None}, AddHostResults.created)
                mock_event_producer = Mock()
                handle_message(json.dumps(message), mock_event_producer)

                mock_event_producer.write_event.assert_called_once()

                self.assertEquals(
                    json.loads(mock_event_producer.write_event.call_args[0][0]),
                    {
                        "host": {"id": str(host_id), "insights_id": None},
                        "metadata": {},
                        "platform_metadata": {},
                        "timestamp": timestamp_iso,
                        "type": "created",
                    },
                )

    # Leaving this in as a reminder that we need to impliment this test eventually
    # when the problem that it is supposed to test is fixed
    # https://projects.engineering.redhat.com/browse/RHCLOUD-3503
    # def test_handle_message_verify_threadctx_request_id_set_and_cleared(self):
    #     # set the threadctx.request_id
    #     # and clear it
    #     pass


@patch("app.queue.ingress.build_egress_topic_event")
@patch("app.queue.ingress.add_host", return_value=(MagicMock(), None))
class MQServiceParseMessageTestCase(MQServiceBaseTestCase):
    def _message(self, display_name):
        return f'{{"operation": "", "data": {{"display_name": "hello{display_name}"}}}}'

    def test_handle_message_failure_invalid_surrogates(self, add_host, build_event):
        raw = "\udce2\udce2"
        escaped = "\\udce2\\udce2"
        display_names = (f"{raw}", f"{escaped}", f"{raw}{escaped}")
        for display_name in display_names:
            with self.subTest(display_names=display_names):
                invalid_message = self._message(display_name)
                with self.assertRaises(UnicodeError):
                    handle_message(invalid_message, Mock())
                add_host.assert_not_called()

    def test_handle_message_unicode_not_damaged(self, add_host, build_event):
        operation_raw = "🧜🏿‍♂️"
        operation_escaped = json.dumps(operation_raw)[1:-1]

        messages = (
            f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_raw}"}}}}',
            f'{{"operation": "", "data": {{"display_name": "{operation_escaped}{operation_escaped}"}}}}',
            f'{{"operation": "", "data": {{"display_name": "{operation_raw}{operation_escaped}"}}}}',
        )
        for message in messages:
            with self.subTest(message=message):
                add_host.reset_mock()
                add_host.return_value = ({"id": "d7d92ccd-c281-49b9-b203-190565c45e1b"}, AddHostResults.updated)
                handle_message(message, Mock())
                add_host.assert_called_once_with({"display_name": f"{operation_raw}{operation_raw}"})


class MQAddHostBaseClass(MQServiceBaseTestCase):
    @classmethod
    def setUpClass(cls):
        """
        Temporarily rename the host table while the tests run.  This is done
        to make dropping the table at the end of the tests a bit safer.
        """
        rename_host_table_and_indexes()

    def setUp(self):
        """
        Initializes the database by creating all tables.
        """
        super().setUp()

        # binds the app to the current context
        with self.app.app_context():
            # create all tables
            db.create_all()

    def tearDown(self):
        """
        Cleans up the database by dropping all tables.
        """
        with self.app.app_context():
            # drop all tables
            db.session.remove()
            db.drop_all()

    def _base_add_host_test(self, host_data, expected_results, host_keys_to_check):
        message = {"operation": "add_host", "data": host_data}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)

        self.assertEqual(json.loads(mock_event_producer.event)["host"]["id"], mock_event_producer.key)

        for key in host_keys_to_check:
            self.assertEqual(json.loads(mock_event_producer.event)["host"][key], expected_results["host"][key])


class MQhandleMessageTestCase(MQAddHostBaseClass):
    def _host_data(self):
        return {
            "display_name": "test_host",
            "id": str(uuid.uuid4()),
            "insights_id": str(uuid.uuid4()),
            "account": "0000001",
            "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
            "reporter": "test",
        }

    def test_handle_message_verify_metadata_pass_through(self):
        metadata = {"request_id": str(uuid.uuid4()), "archive_url": "https://some.url"}

        message = {"operation": "add_host", "platform_metadata": metadata, "data": self._host_data()}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)

        event = json.loads(mock_event_producer.event)
        self.assertEqual(event["platform_metadata"], metadata)

    @patch("app.queue.ingress.host_repository.add_host")
    def test_handle_message_verify_message_key_and_metadata_not_required(self, add_host):
        host_data = self._host_data()
        add_host.return_value = (host_data, AddHostResults.created)

        message = {"operation": "add_host", "data": host_data}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)
            self.assertEqual(mock_event_producer.key, host_data["id"])

        event = json.loads(mock_event_producer.event)
        self.assertEqual(event["host"], host_data)


class MQAddHostTestCase(MQAddHostBaseClass):
    @patch("app.queue.egress.datetime", **{"now.return_value": datetime.now()})
    def test_add_host_simple(self, datetime_mock):
        """
        Tests adding a host with some simple data
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.replace(tzinfo=timezone.utc).isoformat()

        host_data = {
            "display_name": "test_host",
            "insights_id": expected_insights_id,
            "account": "0000001",
            "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
            "reporter": "test",
        }

        expected_results = {
            "host": {**host_data},
            "platform_metadata": {},
            "timestamp": timestamp_iso,
            "type": "created",
        }

        host_keys_to_check = ["display_name", "insights_id", "account"]

        self._base_add_host_test(host_data, expected_results, host_keys_to_check)

    @patch("app.queue.egress.datetime", **{"now.return_value": datetime.now()})
    def test_add_host_with_system_profile(self, datetime_mock):
        """
         Tests adding a host with message containing system profile
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.replace(tzinfo=timezone.utc).isoformat()

        host_data = {
            "display_name": "test_host",
            "insights_id": expected_insights_id,
            "account": "0000001",
            "system_profile": valid_system_profile(),
            "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
            "reporter": "test",
        }

        expected_results = {
            "host": {**host_data},
            "platform_metadata": {},
            "timestamp": timestamp_iso,
            "type": "created",
        }

        host_keys_to_check = ["display_name", "insights_id", "account", "system_profile"]

        self._base_add_host_test(host_data, expected_results, host_keys_to_check)

    @patch("app.queue.egress.datetime", **{"now.return_value": datetime.now()})
    def test_add_host_with_tags(self, datetime_mock):
        """
         Tests adding a host with message containing tags
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.replace(tzinfo=timezone.utc).isoformat()

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
                {"namespace": None, "key": "key", "value": "val"},
            ],
        }

        expected_results = {
            "host": {**host_data},
            "platform_metadata": {},
            "timestamp": timestamp_iso,
            "type": "created",
        }

        host_keys_to_check = ["display_name", "insights_id", "account", "tags"]

        self._base_add_host_test(host_data, expected_results, host_keys_to_check)

    @patch("app.queue.egress.datetime", **{"utcnow.return_value": datetime.utcnow()})
    def test_add_host_empty_keys_system_profile(self, datetime_mock):
        insights_id = str(uuid.uuid4())

        host_data = {
            "display_name": "test_host",
            "insights_id": insights_id,
            "account": "0000001",
            "stale_timestamp": datetime.now(timezone.utc).isoformat(),
            "reporter": "test",
            "system_profile": {"disk_devices": [{"options": {"": "invalid"}}]},
        }
        message = {"operation": "add_host", "data": host_data}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            with self.assertRaises(ValidationException):
                handle_message(json.dumps(message), mock_event_producer)

    @patch("app.queue.egress.datetime", **{"utcnow.return_value": datetime.utcnow()})
    def test_add_host_empty_keys_facts(self, datetime_mock):
        insights_id = str(uuid.uuid4())

        samples = (
            [{"facts": {"": "invalid"}, "namespace": "rhsm"}],
            [{"facts": {"metadata": {"": "invalid"}}, "namespace": "rhsm"}],
        )

        mock_event_producer = MockEventProducer()

        for facts in samples:
            with self.subTest(facts=facts):
                host_data = {
                    "display_name": "test_host",
                    "insights_id": insights_id,
                    "account": "0000001",
                    "stale_timestamp": datetime.now(timezone.utc).isoformat(),
                    "reporter": "test",
                    "facts": facts,
                }
                message = {"operation": "add_host", "data": host_data}

                with self.app.app_context():
                    with self.assertRaises(ValidationException):
                        handle_message(json.dumps(message), mock_event_producer)


class MQCullingTests(MQAddHostBaseClass):
    @patch("app.queue.egress.datetime", **{"now.return_value": datetime.now()})
    def test_add_host_stale_timestamp(self, datetime_mock):
        """
        Tests to see if the host is succesfully created with both reporter
        and stale_timestamp set.
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.isoformat() + "+00:00"
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

        self._base_add_host_test(host_data, expected_results, host_keys_to_check)

    def test_add_host_stale_timestamp_missing_culling_fields(self):
        """
        tests to check the API will reject a host if it doesn’t have both
        culling fields. This should raise InventoryException.
        """
        mock_event_producer = MockEventProducer()

        additional_host_data = ({"stale_timestamp": "2019-12-16T10:10:06.754201+00:00"}, {"reporter": "puptoo"}, {})
        for host_data in additional_host_data:
            with self.subTest(host_data=host_data):
                host_data = {
                    "display_name": "test_host",
                    "insights_id": str(uuid.uuid4()),
                    "account": "0000001",
                    **host_data,
                }
                message = {"operation": "add_host", "data": host_data}

                with self.app.app_context():
                    with self.assertRaises(InventoryException):
                        handle_message(json.dumps(message), mock_event_producer)

    def test_add_host_stale_timestamp_invalid_culling_fields(self):
        """
        tests to check the API will reject a host if it doesn’t have both
        culling fields. This should raise InventoryException.
        """
        mock_event_producer = MockEventProducer()

        additional_host_data = (
            {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": ""},
            {"stale_timestamp": "2019-12-16T10:10:06.754201+00:00", "reporter": None},
            {"stale_timestamp": "not a timestamp", "reporter": "puptoo"},
            {"stale_timestamp": "", "reporter": "puptoo"},
            {"stale_timestamp": None, "reporter": "puptoo"},
        )
        for host_data in additional_host_data:
            with self.subTest(host_data=host_data):
                host_data = {
                    "display_name": "test_host",
                    "insights_id": str(uuid.uuid4()),
                    "account": "0000001",
                    **host_data,
                }
                message = {"operation": "add_host", "data": host_data}

                with self.app.app_context():
                    with self.assertRaises(InventoryException):
                        handle_message(json.dumps(message), mock_event_producer)


class MQValidateJsonObjectForUtf8TestCase(TestCase):
    def test_valid_string_is_ok(self):
        _validate_json_object_for_utf8("naïve fiancé 👰🏻")
        self.assertTrue(True)

    def test_invalid_string_raises_exception(self):
        with self.assertRaises(UnicodeEncodeError):
            _validate_json_object_for_utf8("hello\udce2\udce2")

    @patch("app.queue.ingress._validate_json_object_for_utf8")
    def test_dicts_are_traversed(self, mock):
        _validate_json_object_for_utf8({"first": "item", "second": "value"})
        mock.assert_has_calls((call("first"), call("item"), call("second"), call("value")), any_order=True)

    @patch("app.queue.ingress._validate_json_object_for_utf8")
    def test_lists_are_traversed(self, mock):
        _validate_json_object_for_utf8(["first", "second"])
        mock.assert_has_calls((call("first"), call("second")), any_order=True)

    def test_invalid_string_is_found_in_dict_value(self):
        objects = (
            {"first": "naïve fiancé 👰🏻", "second": "hello\udce2\udce2"},
            {"first": {"subkey": "hello\udce2\udce2"}, "second": "🤷🏻‍♂️"},
            [{"first": "hello\udce2\udce2"}],
            {"deep": ["deeper", {"deepest": ["Mariana trench", {"Earth core": "hello\udce2\udce2"}]}]},
        )
        for obj in objects:
            with self.subTest(object=obj):
                with self.assertRaises(UnicodeEncodeError):
                    _validate_json_object_for_utf8(obj)

    def test_invalid_string_is_found_in_dict_key(self):
        objects = (
            {"naïve fiancé 👰🏻": "first", "hello\udce2\udce2": "second"},
            {"first": {"hello\udce2\udce2": "subvalue"}, "🤷🏻‍♂️": "second"},
            [{"hello\udce2\udce2": "first"}],
            {"deep": ["deeper", {"deepest": ["Mariana trench", {"hello\udce2\udce2": "Earth core"}]}]},
        )
        for obj in objects:
            with self.subTest(object=obj):
                with self.assertRaises(UnicodeEncodeError):
                    _validate_json_object_for_utf8(obj)

    def test_invalid_string_is_found_in_list_item(self):
        objects = (
            ["naïve fiancé 👰🏻", "hello\udce2\udce2"],
            {"first": ["hello\udce2\udce2"], "second": "🤷🏻‍♂️"},
            ["first", ["hello\udce2\udce2"]],
            ["deep", {"deeper": ["deepest", {"Mariana trench": ["Earth core", "hello\udce2\udce2"]}]}],
        )
        for obj in objects:
            with self.subTest(object=obj):
                with self.assertRaises(UnicodeEncodeError):
                    _validate_json_object_for_utf8(obj)

    def test_other_values_are_ignored(self):
        values = (1.23, 0, 123, -123, True, False, None)
        for value in values:
            with self.subTest(value=value):
                _validate_json_object_for_utf8(value)
                self.assertTrue(True)


if __name__ == "__main__":
    main()
