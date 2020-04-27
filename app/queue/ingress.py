import json
import signal

from marshmallow import fields
from marshmallow import Schema
from marshmallow import ValidationError

from app import inventory_config
from app.culling import Timestamps
from app.events import message_headers
from app.exceptions import InventoryException
from app.logging import get_logger
from app.logging import threadctx
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.queue import metrics
from app.queue.egress import build_egress_topic_event
from app.serialization import DEFAULT_FIELDS
from app.serialization import deserialize_host
from lib import host_repository

logger = get_logger(__name__)

EGRESS_HOST_FIELDS = DEFAULT_FIELDS + ("tags", "system_profile")
CONSUMER_POLL_TIMEOUT_MS = 1000


class OperationSchema(Schema):
    operation = fields.Str(required=True)
    platform_metadata = fields.Dict()
    data = fields.Dict(required=True)


# Due to RHCLOUD-3610 we're receiving messages with invalid unicode code points (invalid surrogate pairs)
# Python pretty much ignores that but it is not possible to store such strings in the database (db INSERTS blow up)
# This functions looks for such invalid sequences with the intention of marking such messages as invalid
def _validate_json_object_for_utf8(json_object):
    object_type = type(json_object)
    if object_type is str:
        json_object.encode()
    elif object_type is dict:
        for key, value in json_object.items():
            _validate_json_object_for_utf8(key)
            _validate_json_object_for_utf8(value)
    elif object_type is list:
        for item in json_object:
            _validate_json_object_for_utf8(item)
    else:
        pass


@metrics.ingress_message_parsing_time.time()
def parse_operation_message(message):
    try:
        # Due to RHCLOUD-3610 we're receiving messages with invalid unicode code points (invalid surrogate pairs)
        # Python pretty much ignores that but it is not possible to store such strings in the database (db INSERTS
        # blow up)
        parsed_message = json.loads(message)
    except json.decoder.JSONDecodeError:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue", extra={"incoming_message": message})
        metrics.ingress_message_parsing_failure.labels("invalid").inc()
        raise

    try:
        _validate_json_object_for_utf8(parsed_message)
    except UnicodeEncodeError:
        logger.exception("Invalid Unicode sequence in message from message queue", extra={"incoming_message": message})
        metrics.ingress_message_parsing_failure.labels("invalid").inc()
        raise

    try:
        parsed_operation = OperationSchema(strict=True).load(parsed_message).data
    except ValidationError as e:
        logger.error(
            "Input validation error while parsing operation message:%s", e, extra={"operation": parsed_message}
        )  # logger.error is used to avoid printing out the same traceback twice
        metrics.ingress_message_parsing_failure.labels("invalid").inc()
        raise
    except Exception:
        logger.exception("Error parsing operation message", extra={"operation": parsed_message})
        metrics.ingress_message_parsing_failure.labels("error").inc()
        raise

    logger.debug("parsed_message: %s", parsed_operation)
    return parsed_operation


def add_host(host_data):
    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker, processing_status_message="adding/updating host"
    ) as payload_tracker_processing_ctx:

        try:
            input_host = deserialize_host(host_data)
            staleness_timestamps = Timestamps.from_config(inventory_config())
            logger.info(
                "Attempting to add host",
                extra={
                    "input_host": {
                        "account": input_host.account,
                        "display_name": input_host.display_name,
                        "canonical_facts": input_host.canonical_facts,
                        "reporter": input_host.reporter,
                        "stale_timestamp": input_host.stale_timestamp.isoformat(),
                    }
                },
            )
            (output_host, add_results) = host_repository.add_host(
                input_host, staleness_timestamps, fields=EGRESS_HOST_FIELDS
            )
            metrics.add_host_success.labels(
                add_results.name, host_data.get("reporter", "null")
            ).inc()  # created vs updated
            # log all the incoming host data except facts and system_profile b/c they can be quite large
            logger.info(
                "Host %s",
                add_results.name,
                extra={"host": {i: output_host[i] for i in output_host if i not in ("facts", "system_profile")}},
            )
            payload_tracker_processing_ctx.inventory_id = output_host["id"]
            return (output_host, add_results)
        except InventoryException:
            logger.exception("Error adding host ", extra={"host": host_data})
            metrics.add_host_failure.labels("InventoryException", host_data.get("reporter", "null")).inc()
            raise
        except Exception:
            logger.exception("Error while adding host", extra={"host": host_data})
            metrics.add_host_failure.labels("Exception", host_data.get("reporter", "null")).inc()
            raise


@metrics.ingress_message_handler_time.time()
def handle_message(message, event_producer):
    validated_operation_msg = parse_operation_message(message)
    platform_metadata = validated_operation_msg.get("platform_metadata") or {}
    initialize_thread_local_storage(platform_metadata)

    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerContext(payload_tracker, received_status_message="message received"):
        (output_host, add_results) = add_host(validated_operation_msg["data"])
        event = build_egress_topic_event(add_results.name, output_host, platform_metadata)
        event_producer.write_event(event, output_host["id"], message_headers(add_results.name))


def event_loop(consumer, flask_app, event_producer, handler, shutdown_handler):
    with flask_app.app_context():

        signal.signal(signal.SIGTERM, shutdown_handler.signal_handler)  # For Openshift
        signal.signal(signal.SIGINT, shutdown_handler.signal_handler)  # For Ctrl+C
        while not shutdown_handler.shut_down():
            msgs = consumer.poll(timeout_ms=CONSUMER_POLL_TIMEOUT_MS)
            for topic_partition, messages in msgs.items():
                for message in messages:
                    logger.debug("Message received")
                    try:
                        handler(message.value, event_producer)
                        metrics.ingress_message_handler_success.inc()
                    except Exception:
                        metrics.ingress_message_handler_failure.inc()
                        logger.exception("Unable to process message")


def initialize_thread_local_storage(metadata):
    threadctx.request_id = metadata.get("request_id", "-1")
