from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from unittest import mock

import pytest
from connexion import FlaskApp
from psycopg2.errors import DeadlockDetected
from psycopg2.errors import UniqueViolation
from pytest_mock import MockerFixture
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.queue.event_producer import EventProducer
from app.queue.host_mq import MAX_RETRIES
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import WorkspaceMessageConsumer
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


@mock.patch.object(
    IngressMessageConsumer,
    "handle_message",
    return_value=None,
    side_effect=(
        None,
        KeyError("blah"),
        None,
    ),
)
def test_event_loop_exception_handling(handle_message_mock, mocker, event_producer, flask_app):
    """
    Test to ensure that an exception in message handler method does not cause the
    event loop to stop processing messages
    """
    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage()]

    fake_notification_event_producer = None
    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, fake_notification_event_producer)
    consumer.event_loop(mocker.Mock(side_effect=(False, False, False, True)))

    assert handle_message_mock.call_count == 3


@mock.patch.object(IngressMessageConsumer, "handle_message", return_value=None, side_effect=None)
def test_event_loop_with_error_message_handling(handle_message_mock, mocker, event_producer, flask_app):
    """
    Test to ensure that event loop does not stop processing messages when
    consumer.poll() gets an error in message handler method.
    """
    fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage()], [FakeMessage("oops")], [FakeMessage()]]})
    fake_notification_event_producer = None

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, fake_notification_event_producer)
    consumer.event_loop(mocker.Mock(side_effect=(False, False, False, True)))

    assert handle_message_mock.call_count == 2


@pytest.mark.parametrize(
    "error_factory",
    [
        pytest.param(InvalidRequestError, id="InvalidRequestError"),
        pytest.param(StaleDataError, id="StaleDataError"),
        pytest.param(UniqueViolation, id="UniqueViolation"),
        pytest.param(lambda msg: IntegrityError(None, None, Exception(msg)), id="IntegrityError"),
        pytest.param(lambda msg: OperationalError(msg, None, DeadlockDetected()), id="DeadlockDetected"),
    ],
)
def test_event_loop_handles_invalid_request_error_gracefully(
    mocker: MockerFixture,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    flask_app: FlaskApp,
    error_factory: Callable[[str], BaseException],
):
    """
    Test to ensure that InvalidRequestErrors and StaleDataErrors during
    session commit are handled gracefully with retry logic and do not cause the pod to crash.
    The batch should be retried up to MAX_RETRIES times before giving up and moving to the next batch.
    """
    # Create a fake consumer that returns messages for:
    # - 1 consume for first batch (retries replay the same messages)
    # - 1 consume for second batch
    # - empty list to exit
    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage()],  # First batch
                [FakeMessage()],  # Second batch
                [],  # Exit
            ]
        }
    )
    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, notification_event_producer)

    # Mock handle_message to return None (successful processing) to avoid validation errors
    # that would add extra metric increments
    mocker.patch.object(consumer, "handle_message", return_value=None)

    # Mock the session commit to raise error MAX_RETRIES times for first batch (all retries fail),
    # then succeed on second batch, with extra None values for potential teardown calls
    commit_mock = mocker.patch(
        "app.queue.host_mq.db.session.commit",
        side_effect=[
            # First batch: fail MAX_RETRIES times (all retries exhausted)
            *[error_factory("This Session's transaction has been rolled back") for _ in range(MAX_RETRIES)],
            # Second batch: succeed
            None,
            # Extra None values for potential additional calls (teardown, etc.)
            None,
            None,
            None,
        ],
    )
    rollback_mock = mocker.patch("app.queue.host_mq.db.session.rollback")

    # Mock the metrics to verify it's called
    metrics_mock = mocker.patch("app.queue.host_mq.metrics.ingress_message_handler_failure.inc")

    # Run the event loop for 3 iterations (first batch fails all retries, second succeeds, third exits)
    consumer.event_loop(mocker.Mock(side_effect=[False, False, False, True]))

    # Verify that the failure metric was incremented 5 times for the 5 failed attempts
    assert metrics_mock.call_count == 5
    # Verify that rollback was called at least once for each failed attempt
    # (may be called multiple times per attempt due to session_guard also calling rollback)
    assert rollback_mock.call_count >= 5
    # Verify that the event loop continued and processed the second batch successfully
    # (5 failed commits + at least 1 successful commit from second batch)
    assert commit_mock.call_count >= 6
    # First batch consumed once (retries replay in memory); second batch + empty exit poll.
    assert fake_consumer.consume.call_count == 3


@pytest.mark.parametrize("error_type", (InvalidRequestError, StaleDataError))
def test_event_loop_retries_and_succeeds_on_session_error(
    mocker: MockerFixture,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    flask_app: FlaskApp,
    error_type: type[BaseException],
):
    """
    Test to ensure that the retry logic works when a database session error occurs
    but succeeds on a subsequent retry attempt (before max retries is reached).
    """
    # Create a fake consumer that returns messages for:
    # - 1 consume for first batch (retries replay the same messages)
    # - 1 consume for second batch
    # - empty list to exit
    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage()],  # First batch
                [FakeMessage()],  # Second batch
                [],  # Exit
            ]
        }
    )
    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, notification_event_producer)

    # Mock handle_message to return None (successful processing) to avoid validation errors
    # that would add extra metric increments
    mocker.patch.object(consumer, "handle_message", return_value=None)

    # Mock the session commit to raise error 2 times for first batch, then succeed on 3rd attempt,
    # with extra None values for potential teardown calls
    commit_mock = mocker.patch(
        "app.queue.host_mq.db.session.commit",
        side_effect=[
            # First batch: fail twice, succeed on third attempt
            error_type("This Session's transaction has been rolled back"),
            error_type("This Session's transaction has been rolled back"),
            None,  # Success on retry
            # Second batch: succeed immediately
            None,
            # Extra None values for potential additional calls (teardown, etc.)
            None,
            None,
        ],
    )
    rollback_mock = mocker.patch("app.queue.host_mq.db.session.rollback")

    # Mock the metrics to verify it's called
    metrics_mock = mocker.patch("app.queue.host_mq.metrics.ingress_message_handler_failure.inc")

    # Run the event loop for 3 iterations
    consumer.event_loop(mocker.Mock(side_effect=[False, False, False, True]))

    # Verify that the failure metric was incremented 2 times for the 2 failed attempts
    assert metrics_mock.call_count == 2
    # Verify that rollback was called at least once for each failed attempt
    # (may be called multiple times per attempt due to session_guard also calling rollback)
    assert rollback_mock.call_count >= 2
    # Verify that commit was called at least 4 times total:
    # - 2 failed attempts + 1 successful retry for first batch
    # - at least 1 successful commit for second batch
    assert commit_mock.call_count >= 4
    # First batch consumed once (retries replay in memory); second batch + empty exit poll.
    assert fake_consumer.consume.call_count == 3


def test_event_loop_replays_failed_batch_without_reconsuming(
    mocker: MockerFixture,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    flask_app: FlaskApp,
):
    """Failed batches must be replayed in-memory; retries should not call consume() again."""
    batch_msg_1 = FakeMessage(message='{"msg": 1}')
    batch_msg_2 = FakeMessage(message='{"msg": 2}')
    batch = [batch_msg_1, batch_msg_2]

    fake_consumer = mocker.Mock(**{"consume.side_effect": [batch, []]})
    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, notification_event_producer)

    handle_calls: list[str] = []

    def handle_message_side_effect(message, headers=None):  # noqa: ARG001
        handle_calls.append(message)
        if len(handle_calls) == 2:
            raise OperationalError("deadlock detected", None, DeadlockDetected())
        return None

    mocker.patch.object(consumer, "handle_message", side_effect=handle_message_side_effect)

    consumer.event_loop(mocker.Mock(side_effect=[False, True]))

    assert fake_consumer.consume.call_count == 1
    assert handle_calls == ['{"msg": 1}', '{"msg": 2}', '{"msg": 1}', '{"msg": 2}']


@pytest.mark.parametrize(
    "additional_fields",
    (
        {"account_number": SYSTEM_IDENTITY["account_number"]},
        {},
    ),
)
@mock.patch.object(WorkspaceMessageConsumer, "handle_message")
@mock.patch.object(WorkspaceMessageConsumer, "post_process_rows")
def test_workspace_mq_event_loop(handle_message_mock, post_process_rows_mock, flask_app, mocker, additional_fields):
    message = {
        "operation": "create",
        "org_id": SYSTEM_IDENTITY["org_id"],
        "workspace": {
            "id": str(generate_uuid()),
            "name": "test",
            "type": "standard",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
        **additional_fields,
    }

    fake_consumer = mocker.Mock()
    fake_consumer.consume.return_value = [FakeMessage(message=json.dumps(message))]

    consumer = WorkspaceMessageConsumer(fake_consumer, flask_app, mocker.Mock(), mocker.Mock())

    # Make sure it properly calls handle_message, and does not error out
    consumer.event_loop(interrupt=mocker.Mock(side_effect=(False, True)))
    handle_message_mock.assert_called_once()
    post_process_rows_mock.assert_called_once()
