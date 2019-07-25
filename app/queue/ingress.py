import json
from marshmallow import Schema, fields, ValidationError
from app.logging import get_logger, threadctx
from app.exceptions import InventoryException, ValidationException
from app.queue import metrics
from lib import host_repository


logger = get_logger(__name__)


class OperationSchema(Schema):
    operation = fields.Str()
    metadata = fields.Dict()
    # FIXME:  Remove this field
    request_id = fields.Str()
    data = fields.Dict()


@metrics.ingress_message_parsing_time.time()
def parse_operation_message(message):
    try:
        parsed_message = json.loads(message.value)
    except Exception as e:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue",
                         extra={"incoming_message": message.value})
        metrics.ingress_message_parsing_failure.inc()
        raise

    try:
        parsed_operation = OperationSchema(strict=True).load(parsed_message).data
    except ValidationError as e:
        logger.error("Input validation error while parsing operation message", extra={"operation": parsed_message})  # logger.error is used to avoid printing out the same traceback twice
        metrics.ingress_message_parsing_failure.inc()
        raise
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": parsed_message})
        metrics.ingress_message_parsing_failure.inc()
        raise
    
    return parsed_operation


def add_host(host_data):
    try:
        logger.info("Attempting to add host...")
        host_repository.add_host(host_data)
        metrics.add_host_success.inc()
        logger.info("Host added") # This definitely needs to be more specific (added vs updated?)
    except InventoryException as e:
        logger.exception("Error adding host ", extra={"host": host_data})
        metrics.add_host_failure.inc()
    except Exception as e:
        logger.exception("Error while adding host", extra={"host": host_data})
        metrics.add_host_failure.inc()


def handle_message(message):
    validated_operation_msg = parse_operation_message(message)
    metadata = validated_operation_msg.get("metadata") or {}
    initialize_thread_local_storage(metadata)
    # FIXME: verify operation type
    add_host(validated_operation_msg["data"])


def event_loop(consumer, flask_app, handler=handle_message):
    with flask_app.app_context():
        logger.debug("Waiting for message")
        for msg in consumer:
            logger.debug("Message received")
            try:
                handler(msg)
                metrics.ingress_message_handler_success.inc()
            except Exception:
                metrics.ingress_message_handler_failure.inc()
                logger.exception("Unable to process message")


def initialize_thread_local_storage(metadata):
    threadctx.request_id = metadata.get("request_id", "-1")
