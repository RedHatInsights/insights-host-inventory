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
from sqlalchemy import null

from app import create_app
from app import db
from app.environment import RuntimeEnvironment
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.models import Host
from app.queue.queue import _validate_json_object_for_utf8
from app.queue.queue import event_loop
from app.queue.queue import handle_message
from lib.host_repository import AddHostResult
from tests.test_utils import MockEventProducer, valid_system_profile


class MQServiceBaseTestCase(TestCase):
    def setUp(self):
        """
        Creates the application and a test client to make requests.
        """
        self.app = create_app(RuntimeEnvironment.TEST)


class MQServiceTestCase(MQServiceBaseTestCase):
    def test_event_loop_exception_handling(self):
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
            self.app,
            fake_event_producer,
            handler=handle_message_mock,
            shutdown_handler=Mock(**{"shut_down.side_effect": (False, True)}),
        )
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

    @patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
    def test_handle_message_happy_path(self, datetime_mock):
        expected_insights_id = str(uuid.uuid4())
        host_id = uuid.uuid4()
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
        with self.app.app_context():
            with unittest.mock.patch("app.queue.queue.add_host") as m:
                m.return_value = ({"id": host_id, "insights_id": None}, AddHostResult.created)
                mock_event_producer = Mock()
                handle_message(json.dumps(message), mock_event_producer)

                mock_event_producer.write_event.assert_called_once()

                self.assertEqual(
                    json.loads(mock_event_producer.write_event.call_args[0][0]),
                    {
                        "timestamp": timestamp_iso,
                        "type": "created",
                        "host": {"id": str(host_id), "insights_id": None},
                        "platform_metadata": {},
                        "metadata": {"request_id": "-1"},
                    },
                )

    def test_shutdown_handler(self):
        fake_consumer = Mock()
        fake_consumer.poll.return_value = {"poll1": [Mock(), Mock()]}

        fake_event_producer = None
        handle_message_mock = Mock(side_effect=[None, None])
        event_loop(
            fake_consumer,
            self.app,
            fake_event_producer,
            handler=handle_message_mock,
            shutdown_handler=Mock(**{"shut_down.side_effect": (False, True)}),
        )
        fake_consumer.poll.assert_called_once()
        self.assertEqual(handle_message_mock.call_count, 2)

    # Leaving this in as a reminder that we need to impliment this test eventually
    # when the problem that it is supposed to test is fixed
    # https://projects.engineering.redhat.com/browse/RHCLOUD-3503
    # def test_handle_message_verify_threadctx_request_id_set_and_cleared(self):
    #     # set the threadctx.request_id
    #     # and clear it
    #     pass


@patch("app.queue.queue.build_event")
@patch("app.queue.queue.add_host", return_value=(MagicMock(), None))
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
                add_host.return_value = ({"id": "d7d92ccd-c281-49b9-b203-190565c45e1b"}, AddHostResult.updated)
                handle_message(message, Mock())
                add_host.assert_called_once_with({"display_name": f"{operation_raw}{operation_raw}"})


class MQAddHostBaseClass(MQServiceBaseTestCase):
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

    def _handle_message(self, host_data):
        message = {"operation": "add_host", "data": host_data}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)

        return mock_event_producer

    def _base_add_host_test(self, host_data, expected_results, host_keys_to_check):
        mock_event_producer = self._handle_message(host_data)

        event = json.loads(mock_event_producer.event)
        self.assertEqual(event["host"]["id"], mock_event_producer.key)

        for key in host_keys_to_check:
            self.assertEqual(event["host"][key], expected_results["host"][key])

        return event


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

    @patch("app.queue.queue.add_host")
    def test_handle_message_verify_message_key_and_metadata_not_required(self, add_host):
        host_data = self._host_data()
        add_host.return_value = (host_data, AddHostResult.created)

        message = {"operation": "add_host", "data": host_data}

        mock_event_producer = MockEventProducer()
        with self.app.app_context():
            handle_message(json.dumps(message), mock_event_producer)
            self.assertEqual(mock_event_producer.key, host_data["id"])

        event = json.loads(mock_event_producer.event)
        self.assertEqual(event["host"], host_data)

    @patch("app.queue.queue.add_host")
    def test_handle_message_verify_message_headers(self, add_host):
        host_data = self._host_data()

        message = {"operation": "add_host", "data": host_data}

        for add_host_result in AddHostResult:
            with self.subTest(add_host_result=add_host_result):
                add_host.reset_mock()
                add_host.return_value = (host_data, add_host_result)

                mock_event_producer = MockEventProducer()
                with self.app.app_context():
                    handle_message(json.dumps(message), mock_event_producer)

                self.assertEqual(mock_event_producer.headers, {"event_type": add_host_result.name})


class MQAddHostTestCase(MQAddHostBaseClass):
    @patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
    def test_add_host_simple(self, datetime_mock):
        """
        Tests adding a host with some simple data
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.isoformat()

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

    @patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
    def test_add_host_with_system_profile(self, datetime_mock):
        """
         Tests adding a host with message containing system profile
        """
        expected_insights_id = str(uuid.uuid4())
        timestamp_iso = datetime_mock.now.return_value.isoformat()

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

    @patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
    def test_add_host_with_tags(self, datetime_mock):
        """
         Tests adding a host with message containing tags
        """
        expected_insights_id = str(uuid.uuid4())
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

        expected_results = {
            "host": {**host_data},
            "platform_metadata": {},
            "timestamp": timestamp_iso,
            "type": "created",
        }
        host_keys_to_check = ["display_name", "insights_id", "account"]
        event = self._base_add_host_test(host_data, expected_results, host_keys_to_check)

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
        self.assertCountEqual(event["host"]["tags"], expected_tags)

    def test_add_host_with_invalid_tags(self):
        """
         Tests adding a host with message containing invalid tags
        """
        too_long = "a" * 256
        for tag in (
            {"namespace": "NS", "key": "", "value": "val"},
            {"namespace": too_long, "key": "key", "value": "val"},
            {"namespace": "NS", "key": too_long, "value": "val"},
            {"namespace": "NS", "key": "key", "value": too_long},
            {"namespace": "NS", "key": None, "value": too_long},
            {"namespace": "NS", "value": too_long},
        ):
            with self.subTest(tag=tag):
                host_data = {
                    "display_name": "test_host",
                    "insights_id": str(uuid.uuid4()),
                    "account": "0000001",
                    "stale_timestamp": "2019-12-16T10:10:06.754201+00:00",
                    "reporter": "test",
                    "tags": [tag],
                }
                with self.assertRaises(ValidationException):
                    self._handle_message(host_data)

    @patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
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

    @patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
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

    @patch("app.queue.events.datetime", **{"utcnow.return_value": datetime.utcnow()})
    def test_add_host_with_invalid_stale_timestmap(self, datetime_mock):
        mock_event_producer = MockEventProducer()

        for stale_timestamp in ("invalid", datetime.now().isoformat()):
            with self.subTest(stale_timestamp=stale_timestamp):
                host_data = {
                    "display_name": "test_host",
                    "insights_id": str(uuid.uuid4()),
                    "account": "0000001",
                    "stale_timestamp": stale_timestamp,
                    "reporter": "test",
                }
                message = {"operation": "add_host", "data": host_data}

                with self.app.app_context():
                    with self.assertRaises(ValidationException):
                        handle_message(json.dumps(message), mock_event_producer)


class MQGetFromDbBaseTestCase(MQServiceBaseTestCase):
    def _get_host_by_insights_id(self, insights_id):
        with self.app.app_context():
            return db.session.query(Host).filter(Host.canonical_facts["insights_id"].astext == insights_id).one()


class MQAddHostTagsTestCase(MQAddHostBaseClass, MQGetFromDbBaseTestCase):
    def _message(self, **additional_fields):
        return {
            "account": "0000001",
            "stale_timestamp": datetime.now(timezone.utc).isoformat(),
            "reporter": "test",
            **additional_fields,
        }

    def test_add_host_with_no_tags(self):
        for additional_fields in ({}, {"tags": None}, {"tags": []}, {"tags": {}}):
            with self.subTest(additional_fields=additional_fields):
                insights_id = str(uuid.uuid4())
                message = self._message(insights_id=insights_id, **additional_fields)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(host.tags, {})

    def test_add_host_with_tag_list(self):
        insights_id = str(uuid.uuid4())
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
        message = self._message(insights_id=insights_id, tags=tags)
        self._handle_message(message)
        host = self._get_host_by_insights_id(insights_id)
        self.assertEqual(
            host.tags,
            {
                "namespace 1": {"key 1": ["value 1"], "key 2": []},
                "namespace 2": {"key 1": ["value 2"]},
                "null": {"key 3": ["value 3", "value 4", "value 5"]},
            },
        )

    def test_add_host_with_tag_dict(self):
        insights_id = str(uuid.uuid4())
        tags = {
            "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": None},
            "namespace 2": {"key 1": ["value 2", "", None]},
            "namespace 3": None,
            "namespace 4": {},
            "null": {"key 4": ["value 3"]},
            "": {"key 4": ["value 4"]},
        }
        message = self._message(insights_id=insights_id, tags=tags)
        self._handle_message(message)
        host = self._get_host_by_insights_id(insights_id)
        self.assertEqual(
            host.tags,
            {
                "namespace 1": {"key 1": ["value 1"], "key 2": [], "key 3": []},
                "namespace 2": {"key 1": ["value 2"]},
                "null": {"key 4": ["value 3", "value 4"]},
            },
        )

    def test_add_host_with_invalid_tags(self):
        for tags in (
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
        ):
            with self.subTest(tags=tags):
                insights_id = str(uuid.uuid4())
                message = self._message(insights_id=insights_id, tags=tags)
                with self.assertRaises(ValidationException):
                    self._handle_message(message)


class MQUpdateHostTestCase(MQAddHostBaseClass, MQGetFromDbBaseTestCase):
    def test_update_display_name(self):
        insights_id = "6da26cbf-7084-4a4b-ba9a-a217b4ef9850"

        self._handle_message(
            {
                "display_name": "test_host",
                "insights_id": insights_id,
                "account": "0000001",
                "stale_timestamp": (datetime.now(timezone.utc) + timedelta(hours=26)).isoformat(),
                "reporter": "puptoo",
            }
        )

        self._handle_message(
            {
                "display_name": "better_test_host",
                "insights_id": insights_id,
                "account": "0000001",
                "stale_timestamp": (datetime.now(timezone.utc) + timedelta(hours=26)).isoformat(),
                "reporter": "puptoo",
            }
        )

        record = self._get_host_by_insights_id(insights_id)
        self.assertEqual(record.display_name, "better_test_host")

    # tests the workaround for https://projects.engineering.redhat.com/browse/RHCLOUD-5954
    def test_display_name_ignored_for_blacklisted_reporters(self):
        for reporter in ["yupana", "rhsm-conduit"]:
            with self.subTest(reporter=reporter):
                insights_id = str(uuid.uuid4())

                self._handle_message(
                    {
                        "display_name": "test_host",
                        "insights_id": insights_id,
                        "account": "0000001",
                        "stale_timestamp": (datetime.now(timezone.utc) + timedelta(hours=26)).isoformat(),
                        "reporter": "puptoo",
                    }
                )

                self._handle_message(
                    {
                        "display_name": "yupana_test_host",
                        "insights_id": insights_id,
                        "account": "0000001",
                        "stale_timestamp": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                        "reporter": reporter,
                    }
                )

                record = self._get_host_by_insights_id(insights_id)
                self.assertEqual(record.display_name, "test_host")
                self.assertEqual(record.reporter, reporter)


class MQUpdateHostTagsTestCase(MQAddHostBaseClass, MQGetFromDbBaseTestCase):
    def _message(self, **fields):
        return {
            "account": "0000001",
            "stale_timestamp": datetime.now(timezone.utc).isoformat(),
            "reporter": "test",
            **fields,
        }

    def test_add_tags_to_host_by_list(self):
        insights_id = str(uuid.uuid4())

        for message_tags, expected_tags in (
            ([], {}),
            (
                [{"namespace": "namespace 1", "key": "key 1", "value": "value 1"}],
                {"namespace 1": {"key 1": ["value 1"]}},
            ),
            (
                [{"namespace": "namespace 2", "key": "key 1", "value": "value 2"}],
                {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
            ),
        ):
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, tags=message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)

    def test_add_tags_to_host_by_dict(self):
        insights_id = str(uuid.uuid4())

        for message_tags, expected_tags in (
            ({}, {}),
            ({"namespace 1": {"key 1": ["value 1"]}}, {"namespace 1": {"key 1": ["value 1"]}}),
            (
                {"namespace 2": {"key 1": ["value 2"]}},
                {"namespace 1": {"key 1": ["value 1"]}, "namespace 2": {"key 1": ["value 2"]}},
            ),
        ):
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, tags=message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)

    def test_add_tags_to_hosts_with_null_tags(self):
        # FIXME: Remove this test after migration to NOT NULL.
        for empty in (None, null()):
            with self.subTest(tags=empty):
                insights_id = str(uuid.uuid4())
                message = self._message(insights_id=insights_id)
                self._handle_message(message)

                created_host = self._get_host_by_insights_id(insights_id)
                created_host.tags = empty

                with self.app.app_context():
                    db.session.add(created_host)
                    db.session.commit()

                mock_event_producer = self._handle_message(message)
                event = json.loads(mock_event_producer.event)
                self.assertEqual([], event["host"]["tags"])

                updated_host = self._get_host_by_insights_id(insights_id)
                self.assertEqual({}, updated_host.tags)

    def test_replace_tags_of_host_by_list(self):
        insights_id = str(uuid.uuid4())

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
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, tags=message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)

    def test_replace_host_tags_by_dict(self):
        insights_id = str(uuid.uuid4())

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
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, tags=message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)

    def test_keep_host_tags_by_empty(self):
        insights_id = str(uuid.uuid4())

        for message_tags, expected_tags in (
            ({"tags": {"namespace 1": {"key 1": ["value 1"]}}}, {"namespace 1": {"key 1": ["value 1"]}}),
            ({}, {"namespace 1": {"key 1": ["value 1"]}}),
            ({"tags": None}, {"namespace 1": {"key 1": ["value 1"]}}),
            ({"tags": []}, {"namespace 1": {"key 1": ["value 1"]}}),
            ({"tags": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ):
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, **message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)

    def test_add_host_default_empty_dict(self):
        for tags in ({}, {"tags": None}, {"tags": []}, {"tags": {}}):
            with self.subTest(tags=tags):
                insights_id = str(uuid.uuid4())
                message = self._message(insights_id=insights_id, **tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual({}, host.tags)

    def test_delete_host_tags(self):
        insights_id = str(uuid.uuid4())

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
            (
                {"null": {"key 5": ["value 5"]}},
                {"namespace 1": {"key 1": ["value 1"]}, "null": {"key 5": ["value 5"]}},
            ),
            ({"": {}}, {"namespace 1": {"key 1": ["value 1"]}}),
        ):
            with self.subTest(tags=message_tags):
                message = self._message(insights_id=insights_id, tags=message_tags)
                self._handle_message(message)
                host = self._get_host_by_insights_id(insights_id)
                self.assertEqual(expected_tags, host.tags)


class MQCullingTests(MQAddHostBaseClass):
    @patch("app.queue.events.datetime", **{"now.return_value": datetime.now(timezone.utc)})
    def test_add_host_stale_timestamp(self, datetime_mock):
        """
        Tests to see if the host is succesfully created with both reporter
        and stale_timestamp set.
        """
        expected_insights_id = str(uuid.uuid4())
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

    @patch("app.queue.queue._validate_json_object_for_utf8")
    def test_dicts_are_traversed(self, mock):
        _validate_json_object_for_utf8({"first": "item", "second": "value"})
        mock.assert_has_calls((call("first"), call("item"), call("second"), call("value")), any_order=True)

    @patch("app.queue.queue._validate_json_object_for_utf8")
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
