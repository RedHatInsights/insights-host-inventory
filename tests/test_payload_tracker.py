import uuid
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from tests.helpers.tracker_utils import assert_mock_produce_call
from tests.helpers.tracker_utils import assert_payload_tracker_is_disabled
from tests.helpers.tracker_utils import build_expected_tracker_message
from tests.helpers.tracker_utils import build_payload_tracker_context_error_message
from tests.helpers.tracker_utils import DEFAULT_TOPIC
from tests.helpers.tracker_utils import get_payload_tracker_methods
from tests.helpers.tracker_utils import method_to_raise_exception


def test_payload_tracker_is_disabled_using_env_var(mocker, payload_tracker, tracker_datetime_mock, subtests):
    kafka_producer_mock = mocker.patch("app.payload_tracker.KafkaProducer")
    null_producer_mock = mocker.patch("app.payload_tracker.NullProducer")

    with patch.dict("os.environ", {"PAYLOAD_TRACKER_ENABLED": "False"}):
        tracker = payload_tracker(request_id="123456")

        assert_payload_tracker_is_disabled(tracker, kafka_producer_mock, null_producer_mock, subtests)


def test_payload_tracker_is_disabled_by_invalid_request_id(mocker, payload_tracker, tracker_datetime_mock, subtests):
    kafka_producer_mock = mocker.patch("app.payload_tracker.KafkaProducer")
    null_producer_mock = mocker.patch("app.payload_tracker.NullProducer")

    tracker = payload_tracker(request_id=None)

    assert_payload_tracker_is_disabled(tracker, kafka_producer_mock, null_producer_mock, subtests)


def test_payload_tracker_configure_topic(payload_tracker, tracker_datetime_mock):
    expected_topic = "ima.kafka.topic"
    expected_request_id = "13579"

    expected_msg = build_expected_tracker_message(
        status="received", request_id=expected_request_id, datetime_mock=tracker_datetime_mock
    )

    with patch.dict("os.environ", {"PAYLOAD_TRACKER_KAFKA_TOPIC": expected_topic}):
        producer = Mock()
        tracker = payload_tracker(request_id=expected_request_id, producer=producer)

        # FIXME: test other methods
        tracker.payload_received()

        assert_mock_produce_call(producer, expected_topic, expected_msg)


def test_payload_tracker_producer_raises_exception(payload_tracker, tracker_datetime_mock, subtests):
    # Test that an exception in the producer does not get propagated
    producer_mock = Mock()
    producer_mock.send.side_effect = Exception("Producer send exception!")

    tracker = payload_tracker(request_id="expected_request_id", producer=producer_mock)

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, _ in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            # This method should NOT raise an exception...even though
            # the producer is causing an exception
            method_to_test(status_message="expected_status_msg")


def test_payload_tracker_json_raises_exception(mocker, payload_tracker, tracker_datetime_mock, subtests):
    json_dumps_mock = mocker.patch("app.payload_tracker.json.dumps")

    # Test that an exception in the creation of the message does not get propagated
    json_dumps_mock.side_effect = Exception("json.dumps exception!")

    tracker = payload_tracker(request_id="expected_request_id", producer=Mock())

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, _ in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            # This method should NOT raise an exception...even though
            # the producer is causing an exception
            method_to_test()


def test_payload_tracker_account_is_none(payload_tracker, tracker_datetime_mock, subtests):
    expected_request_id = "1234567890"
    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, expected_status in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            method_to_test()

            expected_msg = build_expected_tracker_message(
                status=expected_status, request_id=expected_request_id, datetime_mock=tracker_datetime_mock
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_pass_status_message(payload_tracker, tracker_datetime_mock, subtests):
    expected_status_msg = "ima status message!"
    expected_request_id = "1234567890"
    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, expected_status in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            method_to_test(status_message=expected_status_msg)

            expected_msg = build_expected_tracker_message(
                status=expected_status,
                status_msg=expected_status_msg,
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_set_account_and_request_id(payload_tracker, tracker_datetime_mock, subtests):
    expected_account = "789"
    expected_request_id = "1234567890"
    producer = Mock()

    tracker = payload_tracker(account=expected_account, request_id=expected_request_id, producer=producer)

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, expected_status in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            method_to_test()

            expected_msg = build_expected_tracker_message(
                account=expected_account,
                status=expected_status,
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_set_org_id_and_request_id(payload_tracker, tracker_datetime_mock, subtests):
    expected_org_id = "789"
    expected_request_id = "1234567890"
    producer = Mock()

    tracker = payload_tracker(org_id=expected_org_id, request_id=expected_request_id, producer=producer)

    methods_to_test = get_payload_tracker_methods(tracker)

    for method_to_test, expected_status in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            method_to_test()

            expected_msg = build_expected_tracker_message(
                org_id=expected_org_id,
                status=expected_status,
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_context_error(payload_tracker, tracker_datetime_mock, subtests):
    expected_request_id = "REQUEST_ID"
    expected_received_status_msg = "ima received msg"

    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    operations = [None, "test operation"]

    for current_operation in operations:
        with subtests.test(current_operation=current_operation):
            with pytest.raises(ValueError):
                with PayloadTrackerContext(
                    payload_tracker=tracker,
                    received_status_message=expected_received_status_msg,
                    current_operation=current_operation,
                ):
                    expected_msg = build_expected_tracker_message(
                        status="received",
                        status_msg=expected_received_status_msg,
                        request_id=expected_request_id,
                        datetime_mock=tracker_datetime_mock,
                    )

                    assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)
                    producer.reset_mock()
                    method_to_raise_exception()

            expected_msg = build_expected_tracker_message(
                status="error",
                status_msg=build_payload_tracker_context_error_message(
                    "ValueError", current_operation, "something bad happened!"
                ),
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_context_success(payload_tracker, tracker_datetime_mock, subtests):
    expected_request_id = "REQUEST_ID"
    expected_received_status_msg = "ima received msg"

    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    success_status_msgs = [None, "ima success status msg"]

    for success_status_msg in success_status_msgs:
        with subtests.test(success_status_msg=success_status_msg):
            with PayloadTrackerContext(
                payload_tracker=tracker,
                received_status_message=expected_received_status_msg,
                success_status_message=success_status_msg,
            ):
                expected_msg = build_expected_tracker_message(
                    status="received",
                    status_msg=expected_received_status_msg,
                    request_id=expected_request_id,
                    datetime_mock=tracker_datetime_mock,
                )

                assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

                producer.reset_mock()

            expected_msg = build_expected_tracker_message(
                status="success",
                status_msg=success_status_msg,
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_processing_context_error(payload_tracker, tracker_datetime_mock, subtests):
    expected_request_id = "REQUEST_ID"
    expected_processing_status = "processing"
    expected_processing_status_msg = "ima processing msg"
    expected_inventory_id = uuid.uuid4()

    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    operations = [None, "test operation"]

    for current_operation in operations:
        with subtests.test(current_operation=current_operation):
            with pytest.raises(ValueError):
                with PayloadTrackerProcessingContext(
                    payload_tracker=tracker,
                    processing_status_message=expected_processing_status_msg,
                    current_operation=current_operation,
                ) as processing_context:
                    expected_msg = build_expected_tracker_message(
                        status=expected_processing_status,
                        status_msg=expected_processing_status_msg,
                        request_id=expected_request_id,
                        datetime_mock=tracker_datetime_mock,
                    )

                    assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)
                    producer.reset_mock()
                    processing_context.inventory_id = expected_inventory_id
                    method_to_raise_exception()

            expected_msg = build_expected_tracker_message(
                status="processing_error",
                status_msg=build_payload_tracker_context_error_message(
                    "ValueError", current_operation, "something bad happened!"
                ),
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            expected_msg["inventory_id"] = str(expected_inventory_id)

            assert tracker.inventory_id is None

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()


def test_payload_tracker_processing_context_success(payload_tracker, tracker_datetime_mock, subtests):
    expected_request_id = "REQUEST_ID"
    expected_processing_status = "processing"
    expected_processing_status_msg = "ima processing msg"
    expected_inventory_id = uuid.uuid4()

    producer = Mock()

    tracker = payload_tracker(request_id=expected_request_id, producer=producer)

    success_status_msgs = [None, "ima success status msg"]

    for success_status_msg in success_status_msgs:
        with subtests.test(success_status_msg=success_status_msg):
            with PayloadTrackerProcessingContext(
                payload_tracker=tracker,
                processing_status_message=expected_processing_status_msg,
                success_status_message=success_status_msg,
            ) as processing_context:
                expected_msg = build_expected_tracker_message(
                    status=expected_processing_status,
                    status_msg=expected_processing_status_msg,
                    request_id=expected_request_id,
                    datetime_mock=tracker_datetime_mock,
                )

                assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

                processing_context.inventory_id = expected_inventory_id

                producer.reset_mock()

            expected_msg = build_expected_tracker_message(
                status="processing_success",
                status_msg=success_status_msg,
                request_id=expected_request_id,
                datetime_mock=tracker_datetime_mock,
            )

            expected_msg["inventory_id"] = str(expected_inventory_id)

            assert tracker.inventory_id is None

            assert_mock_produce_call(producer, DEFAULT_TOPIC, expected_msg)

            producer.reset_mock()
