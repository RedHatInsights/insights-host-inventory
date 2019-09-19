import json
import uuid
from datetime import datetime
from unittest import main
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

from app.config import Config
from app.payload_tracker import _UNKNOWN_PAYLOAD_ID
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import init_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext


def method_to_raise_exception():
    raise ValueError("something bad happened!")


@patch("app.payload_tracker.datetime", **{"utcnow.return_value": datetime.utcnow()})
class PayloadTrackerTestCase(TestCase):

    DEFAULT_TOPIC = "platform.payload-status"

    @patch("app.payload_tracker.NullProducer")
    @patch("app.payload_tracker.KafkaProducer")
    def test_payload_tracker_is_disabled_using_env_var(self, kafka_producer, null_producer, datetime_mock):
        with patch.dict("os.environ", {"PAYLOAD_TRACKER_ENABLED": "False"}):

            tracker = self._get_tracker(payload_id="123456")

            self._verify_payload_tracker_is_disabled(tracker, kafka_producer, null_producer)

    @patch("app.payload_tracker.NullProducer")
    @patch("app.payload_tracker.KafkaProducer")
    def test_payload_tracker_is_disabled_by_invalid_payload_id(self, kafka_producer, null_producer, datetime_mock):
        for invalid_payload_id in [None, _UNKNOWN_PAYLOAD_ID]:
            with self.subTest(invalid_payload_id=invalid_payload_id):
                tracker = self._get_tracker(payload_id=invalid_payload_id)

                self._verify_payload_tracker_is_disabled(tracker, kafka_producer, null_producer)

    def test_payload_tracker_configure_topic(self, datetime_mock):
        expected_topic = "ima.kafka.topic"
        expected_payload_id = "13579"

        expected_msg = self._build_expected_message(
            status="received", payload_id=expected_payload_id, datetime_mock=datetime_mock
        )

        with patch.dict("os.environ", {"PAYLOAD_TRACKER_KAFKA_TOPIC": expected_topic}):
            producer = Mock()
            tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

            # FIXME: test other methods
            tracker.payload_received()

            self._verify_mock_send_call(producer, expected_topic, expected_msg)

    def test_payload_tracker_producer_raises_exception(self, datetime_mock):
        # Test that an exception in the producer does not get propagated
        producer_mock = Mock()
        producer_mock.send.side_effect = Exception("Producer send exception!")

        tracker = self._get_tracker(payload_id="expected_payload_id", producer=producer_mock)

        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for (method_to_test, _) in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                # This method should NOT raise an exception...even though
                # the producer is causing an exception
                method_to_test(status_message="expected_status_msg")

    @patch("app.payload_tracker.json.dumps")
    def test_payload_tracker_json_raises_exception(self, json_dumps_mock, datetime_mock):
        # Test that an exception in the creation of the message does not get propagated
        json_dumps_mock.side_effect = Exception("json.dumps exception!")

        tracker = self._get_tracker(payload_id="expected_payload_id", producer=Mock())

        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for (method_to_test, _) in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                # This method should NOT raise an exception...even though
                # the producer is causing an exception
                method_to_test()

    def test_payload_tracker_account_is_None(self, datetime_mock):
        expected_payload_id = "1234567890"
        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for (method_to_test, expected_status) in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                method_to_test()

                expected_msg = self._build_expected_message(
                    status=expected_status, payload_id=expected_payload_id, datetime_mock=datetime_mock
                )

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_pass_status_message(self, datetime_mock):
        expected_status_msg = "ima status message!"
        expected_payload_id = "1234567890"
        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for method_to_test, expected_status in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                method_to_test(status_message=expected_status_msg)

                expected_msg = self._build_expected_message(
                    status=expected_status,
                    status_msg=expected_status_msg,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_set_account_and_payload_id(self, datetime_mock):
        expected_account = "789"
        expected_payload_id = "1234567890"
        producer = Mock()

        tracker = self._get_tracker(account=expected_account, payload_id=expected_payload_id, producer=producer)

        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for method_to_test, expected_status in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                method_to_test()

                expected_msg = self._build_expected_message(
                    account=expected_account,
                    status=expected_status,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_context_error(self, datetime_mock):
        expected_payload_id = "REQUEST_ID"
        expected_received_status_msg = "ima received msg"

        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        error_status_msgs = [None, "ima error status msg"]

        for error_status_msg in error_status_msgs:
            with self.subTest(error_status_msg=error_status_msg):

                with self.assertRaises(ValueError):
                    with PayloadTrackerContext(
                        payload_tracker=tracker,
                        received_status_message=expected_received_status_msg,
                        error_status_message=error_status_msg,
                    ):

                        expected_msg = self._build_expected_message(
                            status="received",
                            status_msg=expected_received_status_msg,
                            payload_id=expected_payload_id,
                            datetime_mock=datetime_mock,
                        )

                        self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)
                        producer.reset_mock()
                        method_to_raise_exception()

                expected_msg = self._build_expected_message(
                    status="error",
                    status_msg=error_status_msg,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_context_success(self, datetime_mock):
        expected_payload_id = "REQUEST_ID"
        expected_received_status_msg = "ima received msg"

        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        success_status_msgs = [None, "ima success status msg"]

        for success_status_msg in success_status_msgs:
            with self.subTest(success_status_msg=success_status_msg):

                with PayloadTrackerContext(
                    payload_tracker=tracker,
                    received_status_message=expected_received_status_msg,
                    success_status_message=success_status_msg,
                ):

                    expected_msg = self._build_expected_message(
                        status="received",
                        status_msg=expected_received_status_msg,
                        payload_id=expected_payload_id,
                        datetime_mock=datetime_mock,
                    )

                    self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                    producer.reset_mock()

                expected_msg = self._build_expected_message(
                    status="success",
                    status_msg=success_status_msg,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_processing_context_error(self, datetime_mock):
        expected_payload_id = "REQUEST_ID"
        expected_processing_status = "processing"
        expected_processing_status_msg = "ima processing msg"
        expected_inventory_id = uuid.uuid4()

        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        error_status_msgs = [None, "ima error status msg"]

        for error_status_msg in error_status_msgs:
            with self.subTest(error_status_msg=error_status_msg):

                with self.assertRaises(ValueError):
                    with PayloadTrackerProcessingContext(
                        payload_tracker=tracker,
                        processing_status_message=expected_processing_status_msg,
                        error_status_message=error_status_msg,
                    ) as processing_context:

                        expected_msg = self._build_expected_message(
                            status=expected_processing_status,
                            status_msg=expected_processing_status_msg,
                            payload_id=expected_payload_id,
                            datetime_mock=datetime_mock,
                        )

                        self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)
                        producer.reset_mock()
                        processing_context.inventory_id = expected_inventory_id
                        method_to_raise_exception()

                expected_msg = self._build_expected_message(
                    status="processing_error",
                    status_msg=error_status_msg,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                expected_msg["inventory_id"] = str(expected_inventory_id)

                self.assertIsNone(tracker.inventory_id)

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def test_payload_tracker_processing_context_success(self, datetime_mock):
        expected_payload_id = "REQUEST_ID"
        expected_processing_status = "processing"
        expected_processing_status_msg = "ima processing msg"
        expected_inventory_id = uuid.uuid4()

        producer = Mock()

        tracker = self._get_tracker(payload_id=expected_payload_id, producer=producer)

        success_status_msgs = [None, "ima success status msg"]

        for success_status_msg in success_status_msgs:
            with self.subTest(success_status_msg=success_status_msg):

                with PayloadTrackerProcessingContext(
                    payload_tracker=tracker,
                    processing_status_message=expected_processing_status_msg,
                    success_status_message=success_status_msg,
                ) as processing_context:

                    expected_msg = self._build_expected_message(
                        status=expected_processing_status,
                        status_msg=expected_processing_status_msg,
                        payload_id=expected_payload_id,
                        datetime_mock=datetime_mock,
                    )

                    self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                    processing_context.inventory_id = expected_inventory_id

                    producer.reset_mock()

                expected_msg = self._build_expected_message(
                    status="processing_success",
                    status_msg=success_status_msg,
                    payload_id=expected_payload_id,
                    datetime_mock=datetime_mock,
                )

                expected_msg["inventory_id"] = str(expected_inventory_id)

                self.assertIsNone(tracker.inventory_id)

                self._verify_mock_send_call(producer, self.DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

    def _get_tracker(self, account=None, payload_id=None, producer=None):
        config = Config()
        init_payload_tracker(config, producer=producer)
        return get_payload_tracker(account=account, payload_id=payload_id)

    def _verify_mock_send_call(self, mock_producer, expected_topic, expected_msg):
        mock_producer.send.assert_called()
        args, kwargs = mock_producer.send.call_args
        actual_topic, actual_msg = args
        self.assertEqual(actual_topic, expected_topic)
        self.assertEqual(json.loads(actual_msg), expected_msg)

    def _get_payload_tracker_methods_to_test(self, tracker):
        return [
            (tracker.payload_received, "received"),
            (tracker.payload_success, "success"),
            (tracker.payload_error, "error"),
            (tracker.processing, "processing"),
            (tracker.processing_success, "processing_success"),
            (tracker.processing_error, "processing_error"),
        ]

    def _verify_payload_tracker_is_disabled(self, tracker, kafka_producer, null_producer):
        methods_to_test = self._get_payload_tracker_methods_to_test(tracker)

        for (method_to_test, _) in methods_to_test:
            with self.subTest(method_to_test=method_to_test):
                method_to_test(status_message="expected_status_msg")

                # Verify that the KafkaProducer object is not called and that the NullProducer is called
                kafka_producer.return_value.send.assert_not_called()
                null_producer.return_value.send.assert_not_called()

                null_producer.reset_mock()

    def _build_expected_message(
        self, status="received", status_msg=None, payload_id="1357924680", account=None, datetime_mock=None
    ):
        expected_msg = {
            "service": "inventory",
            "payload_id": payload_id,
            "status": status,
            "date": datetime_mock.utcnow.return_value.isoformat(),
        }

        if status_msg:
            expected_msg["status_msg"] = status_msg

        if account:
            expected_msg["account"] = account

        return expected_msg


if __name__ == "__main__":
    main()
