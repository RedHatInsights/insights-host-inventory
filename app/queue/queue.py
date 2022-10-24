import base64
import json
import sys
import uuid
from copy import deepcopy
from uuid import UUID

from marshmallow import fields
from marshmallow import Schema
from marshmallow import ValidationError
from sqlalchemy.exc import OperationalError

from app import inventory_config
from app.auth.identity import create_mock_identity_with_org_id
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.culling import Timestamps
from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.instrumentation import log_add_host_attempt
from app.instrumentation import log_add_host_failure
from app.instrumentation import log_add_update_host_succeeded
from app.instrumentation import log_db_access_failure
from app.instrumentation import log_update_system_profile_failure
from app.instrumentation import log_update_system_profile_success
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import LimitedHostSchema
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.queue import metrics
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.queue.events import operation_results_to_event_type
from app.queue.notifications import build_notification_event
from app.queue.notifications import notification_message_headers
from app.queue.notifications import NotificationType
from app.serialization import DEFAULT_FIELDS
from app.serialization import deserialize_canonical_facts
from app.serialization import deserialize_host
from lib import host_repository


logger = get_logger(__name__)

EGRESS_HOST_FIELDS = DEFAULT_FIELDS + ("tags", "system_profile")
CONSUMER_POLL_TIMEOUT_SECONDS = 1
SYSTEM_IDENTITY = {"auth_type": "cert-auth", "system": {"cert_type": "system"}, "type": "System"}


class OperationSchema(Schema):
    operation = fields.Str(required=True)
    platform_metadata = fields.Dict()
    data = fields.Dict(required=True)


# input is a base64 encoded utf-8 string. b64decode returns bytes, which
# again needs decoding using ascii to get human readable dictionary
def _decode_id(encoded_id):
    id = base64.b64decode(encoded_id)
    decoded_id = json.loads(id)
    return decoded_id.get("identity")


# receives an uuid string w/o dashes and outputs an uuid string with dashes
def _formatted_uuid(uuid_string):
    return str(UUID(uuid_string))


def _get_identity(host, metadata):
    # rhsm reporter does not provide identity.  Set identity type to system for access the host in future.
    if metadata and "b64_identity" in metadata:
        identity = _decode_id(metadata["b64_identity"])
    else:
        if host.get("reporter") == "rhsm-conduit" and host.get("subscription_manager_id"):
            identity = deepcopy(SYSTEM_IDENTITY)
            if "account" in host:
                identity["account_number"] = host["account"]
            identity["org_id"] = host.get("org_id")
            identity["system"]["cn"] = _formatted_uuid(host.get("subscription_manager_id"))
        elif metadata:
            raise ValueError(
                "When identity is not provided, reporter MUST be rhsm-conduit with a subscription_manager_id.\n"
                f"Host Data: {host}"
            )
        else:
            raise ValidationException("platform_metadata is mandatory")

    if host.get("org_id") != identity["org_id"]:
        raise ValidationException("The org_id in the identity does not match the org_id in the host.")

    identity = Identity(identity)
    return identity


# When identity_type is System, set owner_id if missing from the host system_profile
def _set_owner(host, identity):
    cn = identity.system.get("cn")
    if "system_profile" not in host:
        host["system_profile"] = {}
        host["system_profile"]["owner_id"] = cn
    elif not host["system_profile"].get("owner_id"):
        host["system_profile"]["owner_id"] = cn
    else:
        if host.get("reporter") == "rhsm-conduit" and host.get("subscription_manager_id"):
            host["system_profile"]["owner_id"] = _formatted_uuid(host.get("subscription_manager_id"))
        else:
            if host["system_profile"]["owner_id"] != cn:
                raise ValidationException("The owner in host does not match the owner in identity")
    return host


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


def _build_minimal_host_info(host_data):
    return {
        "account_id": host_data.get("account"),
        "org_id": host_data.get("org_id"),
        "display_name": host_data.get("display_name"),
        "id": host_data.get("host_id"),
        "canonical_facts": deserialize_canonical_facts(host_data, all=True),
    }


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
        parsed_operation = OperationSchema().load(parsed_message)
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


def sync_event_message(message, session, event_producer):
    host_id = message["host"]["id"]
    if message["type"] != EventType.delete.name:
        query = session.query(Host).filter((Host.org_id == message["host"]["org_id"]) & (Host.id == UUID(host_id)))
        # If the host doesn't exist in the DB, produce a Delete event.
        if not query.count():
            host = deserialize_host({k: v for k, v in message["host"].items() if v}, schema=LimitedHostSchema)
            host.id = host_id
            event = build_event(EventType.delete, host)
            insights_id = host.canonical_facts.get("insights_id")
            headers = message_headers(EventType.delete, insights_id)
            event_producer.write_event(event, host.id, headers)
            logger.info(f"{host_id}: Latest event is not a delete, and host not found in DB; DELETE event produced.")
        else:
            logger.info(f"{host_id}: Latest event is not a delete, but host found in DB.")
    else:
        logger.info(f"{host_id}: Latest event is a delete.")

    return


def update_system_profile(host_data, platform_metadata):
    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker,
        processing_status_message="updating host system profile",
        current_operation="updating host system profile",
    ) as payload_tracker_processing_ctx:

        try:
            input_host = deserialize_host(host_data, schema=LimitedHostSchema)
            input_host.id = host_data.get("id")
            staleness_timestamps = Timestamps.from_config(inventory_config())
            identity = create_mock_identity_with_org_id(input_host.org_id)
            output_host, host_id, insights_id, update_result = host_repository.update_system_profile(
                input_host, identity, staleness_timestamps, EGRESS_HOST_FIELDS
            )
            log_update_system_profile_success(logger, output_host)
            payload_tracker_processing_ctx.inventory_id = output_host["id"]
            return output_host, host_id, insights_id, update_result
        except ValidationException:
            metrics.update_system_profile_failure.labels("ValidationException").inc()
            raise
        except InventoryException:
            log_update_system_profile_failure(logger, host_data)
            raise
        except OperationalError as oe:
            log_db_access_failure(logger, f"Could not access DB {str(oe)}", host_data)
            raise oe
        except Exception:
            logger.exception("Error while updating host system profile", extra={"host": host_data})
            metrics.update_system_profile_failure.labels("Exception").inc()
            raise


def add_host(host_data, platform_metadata):
    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker, processing_status_message="adding/updating host", current_operation="adding/updating host"
    ) as payload_tracker_processing_ctx:

        try:
            identity = _get_identity(host_data, platform_metadata)
            # basic-auth does not need owner_id
            if identity.identity_type == IdentityType.SYSTEM:
                host_data = _set_owner(host_data, identity)

            input_host = deserialize_host(host_data)
            staleness_timestamps = Timestamps.from_config(inventory_config())
            log_add_host_attempt(logger, input_host)
            output_host, host_id, insights_id, add_result = host_repository.add_host(
                input_host, identity, staleness_timestamps, fields=EGRESS_HOST_FIELDS
            )
            log_add_update_host_succeeded(logger, add_result, host_data, output_host)
            payload_tracker_processing_ctx.inventory_id = output_host["id"]
            return output_host, host_id, insights_id, add_result
        except ValidationException:
            metrics.add_host_failure.labels("ValidationException", host_data.get("reporter", "null")).inc()
            raise
        except InventoryException as ie:
            log_add_host_failure(logger, str(ie.detail), host_data)
            raise
        except OperationalError as oe:
            log_db_access_failure(logger, f"Could not access DB {str(oe)}", host_data)
            raise oe
        except Exception:
            logger.exception("Error while adding host", extra={"host": host_data})
            metrics.add_host_failure.labels("Exception", host_data.get("reporter", "null")).inc()
            raise


@metrics.ingress_message_handler_time.time()
def handle_message(message, event_producer, notification_event_producer, message_operation=add_host):
    validated_operation_msg = parse_operation_message(message)
    platform_metadata = validated_operation_msg.get("platform_metadata", {})

    request_id = platform_metadata.get("request_id")
    initialize_thread_local_storage(request_id)

    payload_tracker = get_payload_tracker(request_id=request_id)

    with PayloadTrackerContext(
        payload_tracker, received_status_message="message received", current_operation="handle_message"
    ):
        try:
            host = validated_operation_msg["data"]

            output_host, host_id, insights_id, operation_result = message_operation(host, platform_metadata)
            event_type = operation_results_to_event_type(operation_result)
            event = build_event(event_type, output_host, platform_metadata=platform_metadata)

            headers = message_headers(operation_result, insights_id)
            event_producer.write_event(event, str(host_id), headers)
        except ValidationException as ve:
            logger.error(
                "Validation error while adding or updating host: %s",
                ve,
                extra={"host": {"reporter": host.get("reporter")}},
            )
            send_kafka_error_message(notification_event_producer, host=host, detail=str(ve.detail))
            raise
        except ValueError as ve:
            logger.error("Value error while adding or updating host: %s", ve, extra={"reporter": host.get("reporter")})
            raise


def event_loop(consumer, flask_app, event_producer, notification_event_producer, handler, interrupt):
    with flask_app.app_context():
        while not interrupt():
            messages = consumer.consume(
                num_messages=inventory_config().max_poll_records, timeout=CONSUMER_POLL_TIMEOUT_SECONDS
            )
            for msg in messages:
                if msg is None:
                    continue
                elif msg.error():
                    # This error is returned by the very first of consumer.consume() against a newly started Kafka.
                    # msg.error() produces:
                    # KafkaError{code=UNKNOWN_TOPIC_OR_PART,val=3,str="Subscribed topic not available:
                    #   platform.inventory.host-ingress: Broker: Unknown topic or partition"}
                    logger.error(f"Message received but has an error, which is {str(msg.error())}")
                    metrics.ingress_message_handler_failure.inc()
                else:
                    logger.debug("Message received")
                    try:
                        handler(msg.value(), event_producer, notification_event_producer=notification_event_producer)
                        metrics.ingress_message_handler_success.inc()
                    except OperationalError as oe:
                        """sqlalchemy.exc.OperationalError: This error occurs when an
                        authentication failure occurs or the DB is not accessible.
                        Exit the process to restart the pod
                        """
                        logger.error(f"Could not access DB {str(oe)}")
                        sys.exit(3)
                    except Exception:
                        metrics.ingress_message_handler_failure.inc()
                        logger.exception("Unable to process message", extra={"incoming_message": msg.value()})


def initialize_thread_local_storage(request_id):
    threadctx.request_id = request_id


def send_kafka_error_message(notification_event_producer, host, detail):
    message_id = str(uuid.uuid4())
    minimal_host = _build_minimal_host_info(host)
    event = build_notification_event(NotificationType.validation_error, message_id, minimal_host, detail)
    rh_message_id = bytearray(message_id.encode())  # ensures the correct processing of the message
    headers = notification_message_headers(
        NotificationType.validation_error,
        rh_message_id=rh_message_id,
    )
    key = minimal_host.get("canonical_facts" or {}).get("insights_id")
    notification_event_producer.write_event(event, key, headers)
