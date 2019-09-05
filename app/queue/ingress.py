import json

from marshmallow import fields
from marshmallow import Schema
from marshmallow import ValidationError

from app.exceptions import InventoryException
from app.logging import get_logger
from app.logging import threadctx
from app.queue import metrics
from app.queue.egress import build_event
from lib import host_repository


logger = get_logger(__name__)


class OperationSchema(Schema):
    operation = fields.Str(required=True)
    platform_metadata = fields.Dict()
    data = fields.Dict(required=True)


@metrics.ingress_message_parsing_time.time()
def parse_operation_message(message):
    try:
        parsed_message = json.loads(message)
    except Exception:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue", extra={"incoming_message": message})
        metrics.ingress_message_parsing_failure.inc()
        raise

    try:
        parsed_operation = OperationSchema(strict=True).load(parsed_message).data
    except ValidationError as e:
        logger.error(
            "Input validation error while parsing operation message:%s", e, extra={"operation": parsed_message}
        )  # logger.error is used to avoid printing out the same traceback twice
        metrics.ingress_message_parsing_failure.inc()
        raise
    except Exception:
        logger.exception("Error parsing operation message", extra={"operation": parsed_message})
        metrics.ingress_message_parsing_failure.inc()
        raise

    return parsed_operation


def add_host(host_data):
    try:
        logger.info("Attempting to add host...")
        (output_host, add_results) = host_repository.add_host(host_data)
        metrics.add_host_success.inc()
        logger.info("Host added")  # This definitely needs to be more specific (added vs updated?)
        return (output_host, add_results)
    except InventoryException:
        logger.exception("Error adding host ", extra={"host": host_data})
        metrics.add_host_failure.inc()
        raise
    except Exception:
        logger.exception("Error while adding host", extra={"host": host_data})
        metrics.add_host_failure.inc()
        raise


@metrics.ingress_message_handler_time.time()
def handle_message(message, event_producer):
    validated_operation_msg = parse_operation_message(message)
    metadata = validated_operation_msg.get("platform_metadata") or {}
    initialize_thread_local_storage(metadata)
    # FIXME: verify operation type
    (output_host, add_results) = add_host(validated_operation_msg["data"])

    if add_results == host_repository.AddHostResults.created:
        event_type = "created"
    else:
        event_type = "updated"

    event = build_event(event_type, output_host, metadata)

    event_producer.write_event(event)


def event_loop(consumer, flask_app, event_producer, handler=handle_message):
    with flask_app.app_context():
        logger.debug("Waiting for message")
        for msg in consumer:
            logger.debug("Message received")
            try:
                handler(msg.value, event_producer)
                metrics.ingress_message_handler_success.inc()
            except Exception:
                metrics.ingress_message_handler_failure.inc()
                logger.exception("Unable to process message")


def initialize_thread_local_storage(metadata):
    threadctx.request_id = metadata.get("request_id", "-1")
