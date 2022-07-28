import json

DEFAULT_TOPIC = "platform.payload-status"


def build_expected_tracker_message(
    status="received", status_msg=None, request_id="1357924680", account=None, org_id=None, datetime_mock=None
):
    expected_msg = {
        "service": "inventory",
        "request_id": request_id,
        "status": status,
        "date": datetime_mock.utcnow.return_value.isoformat(),
    }

    if status_msg:
        expected_msg["status_msg"] = status_msg

    if account:
        expected_msg["account"] = account

    if org_id:
        expected_msg["org_id"] = org_id

    return expected_msg


def build_payload_tracker_context_error_message(exception_name, current_operation, exception_value):
    return f"{exception_name} encountered in ({current_operation}): {exception_value}"


def get_payload_tracker_methods(tracker):
    return [
        (tracker.payload_received, "received"),
        (tracker.payload_success, "success"),
        (tracker.payload_error, "error"),
        (tracker.processing, "processing"),
        (tracker.processing_success, "processing_success"),
        (tracker.processing_error, "processing_error"),
    ]


def method_to_raise_exception():
    raise ValueError("something bad happened!")


def assert_payload_tracker_is_disabled(tracker, kafka_producer, null_producer, subtests):
    methods_to_test = get_payload_tracker_methods(tracker)

    for (method_to_test, _) in methods_to_test:
        with subtests.test(method_to_test=method_to_test):
            method_to_test(status_message="expected_status_msg")

            # Verify that the KafkaProducer object is not called and that the NullProducer is called
            kafka_producer.return_value.send.assert_not_called()
            null_producer.return_value.send.assert_not_called()

            null_producer.reset_mock()


def assert_mock_produce_call(mock_producer, expected_topic, expected_msg):
    mock_producer.produce.assert_called()
    args, kwargs = mock_producer.produce.call_args
    actual_topic, actual_msg = args

    assert actual_topic == expected_topic
    assert json.loads(actual_msg) == expected_msg
