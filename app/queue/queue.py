import base64
import json
import sys
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from functools import partial
from uuid import UUID

from marshmallow import fields
from marshmallow import Schema
from marshmallow import validates_schema
from marshmallow import ValidationError
from sqlalchemy.exc import OperationalError

from api.cache import delete_keys
from api.staleness_query import get_staleness_obj
from app.auth.identity import create_mock_identity_with_org_id
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.common import inventory_config
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
from app.models import db
from app.models import Host
from app.models import LimitedHostSchema
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.queue import metrics
from app.queue.event_producer import EventProducer
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.queue.events import operation_results_to_event_type
from app.queue.export_service import create_export
from app.queue.notifications import NotificationType
from app.queue.notifications import send_notification
from app.serialization import deserialize_host
from app.serialization import serialize_host
from lib import host_repository
from lib.db import session_guard

logger = get_logger(__name__)

CONSUMER_POLL_TIMEOUT_SECONDS = 1
SYSTEM_IDENTITY = {"auth_type": "cert-auth", "system": {"cert_type": "system"}, "type": "System"}
EXPORT_EVENT_SOURCE = "urn:redhat:source:console:app:export-service"
EXPORT_SERVICE_APPLICATION = "host-inventory"


class OperationSchema(Schema):
    operation = fields.Str(required=True)
    operation_args = fields.Dict()
    platform_metadata = fields.Dict()
    data = fields.Dict(required=True)


# Helper class to facilitate batch operations
class OperationResult:
    def __init__(self, hr, pm, st, so, et, sl):
        self.host_row = hr
        self.platform_metadata = pm
        self.staleness_timestamps = st
        self.staleness_object = so
        self.event_type = et
        self.success_logger = sl


class ExportResourceRequest(Schema):
    application = fields.Str(required=True)
    export_request_uuid = fields.UUID(required=True)
    filters = fields.Dict()
    format = fields.Str(required=True)
    resource = fields.Str(required=True)
    uuid = fields.Str(required=True)
    x_rh_identity = fields.Str(required=True, data_key="x-rh-identity")

    @validates_schema
    def check_application_name(self, data, **kwargs):
        if data["application"] != EXPORT_SERVICE_APPLICATION:
            raise ValidationError('application field must be "host-inventory"')


class ExportDataSchema(Schema):
    resource_request = fields.Nested(ExportResourceRequest)


class ExportEventSchema(Schema):
    id = fields.UUID(required=True)
    schema = fields.Str(data_key="$schema")
    source = fields.Str(required=True)
    subject = fields.Str(required=True)
    specversion = fields.Str(required=True)
    type = fields.Str(required=True)
    time = fields.DateTime(required=True)
    redhatorgid = fields.Str(required=True)
    dataschema = fields.Str(required=True)
    data = fields.Nested(ExportDataSchema, required=True)


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
        reporter = host.get("reporter")
        if (reporter == "rhsm-conduit" or reporter == "rhsm-system-profile-bridge") and host.get(
            "subscription_manager_id"
        ):
            identity = deepcopy(SYSTEM_IDENTITY)
            if "account" in host:
                identity["account_number"] = host["account"]
            identity["org_id"] = host.get("org_id")
            identity["system"]["cn"] = _formatted_uuid(host.get("subscription_manager_id"))
        elif metadata:
            raise ValidationException(
                "When identity is not provided, reporter MUST be rhsm-conduit or rhsm-system-profile-bridge,"
                " with a subscription_manager_id.\n"
                f"Host Data: {host}"
            )
        else:
            raise ValidationException("platform_metadata is mandatory")

    if not host.get("org_id"):
        raise ValidationException("org_id must be provided")
    elif host.get("org_id") != identity["org_id"]:
        raise ValidationException("The org_id in the identity does not match the org_id in the host.")
    try:
        identity = Identity(identity)
    except ValueError as e:
        raise ValidationException(str(e))
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
        reporter = host.get("reporter")
        if (reporter == "rhsm-conduit" or reporter == "rhsm-system-profile-bridge") and host.get(
            "subscription_manager_id"
        ):
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


@metrics.common_message_parsing_time.time()
def common_message_parser(message):
    try:
        # Due to RHCLOUD-3610 we're receiving messages with invalid unicode code points (invalid surrogate pairs)
        # Python pretty much ignores that but it is not possible to store such strings in the database (db INSERTS
        # blow up)
        parsed_message = json.loads(message)
        return parsed_message
    except json.decoder.JSONDecodeError:
        # The "extra" dict cannot have a key named "msg" or "message"
        # otherwise an exception in thrown in the logging code
        logger.exception("Unable to parse json message from message queue", extra={"incoming_message": message})
        metrics.common_message_parsing_failure.labels("invalid").inc()
        raise


@metrics.ingress_message_parsing_time.time()
def parse_operation_message(message):
    parsed_message = common_message_parser(message)

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


@metrics.export_service_message_parsing_time.time()
def parse_export_service_message(message):
    parsed_message = common_message_parser(message)
    try:
        parsed_operation = ExportEventSchema().load(parsed_message)
    except ValidationError as e:
        logger.error(
            "Input validation error while parsing export event message:%s", e, extra={"operation": parsed_message}
        )  # logger.error is used to avoid printing out the same traceback twice

        metrics.export_service_message_parsing_failure.labels("invalid").inc()
        raise
    except Exception:
        logger.exception("Error parsing export event message", extra={"operation": parsed_message})

        metrics.export_service_message_parsing_failure.labels("error").inc()
        raise

    if (
        "source" in parsed_message
        and parsed_message["source"] == EXPORT_EVENT_SOURCE
        and parsed_message["data"]["resource_request"]["application"] == EXPORT_SERVICE_APPLICATION
    ):
        logger.info("Consuming export-service event message")

        logger.debug("parsed_message: %s", parsed_operation)
        return parsed_operation
    else:
        logger.debug("Message not related to host-inventory found and not processed")


def sync_event_message(message, session, event_producer):
    if message["type"] != EventType.delete.name:
        host_id = message["host"]["id"]
        query = session.query(Host).filter((Host.org_id == message["host"]["org_id"]) & (Host.id == UUID(host_id)))
        # If the host doesn't exist in the DB, produce a Delete event.
        if not query.count():
            host = deserialize_host({k: v for k, v in message["host"].items() if v}, schema=LimitedHostSchema)
            host.id = host_id
            event = build_event(EventType.delete, host)
            headers = message_headers(
                EventType.delete,
                host.canonical_facts.get("insights_id"),
                message["host"].get("reporter"),
                host.system_profile_facts.get("host_type"),
                host.system_profile_facts.get("operating_system", {}).get("name"),
            )
            # add back "wait=True", if needed.
            event_producer.write_event(event, host.id, headers, wait=True)

    return


def update_system_profile(host_data, platform_metadata, operation_args={}):
    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker,
        processing_status_message="updating host system profile",
        current_operation="updating host system profile",
    ):
        try:
            input_host = deserialize_host(host_data, schema=LimitedHostSchema)
            input_host.id = host_data.get("id")
            identity = create_mock_identity_with_org_id(input_host.org_id)
            output_host, update_result = host_repository.update_system_profile(input_host, identity)
            success_logger = partial(log_update_system_profile_success, logger)
            return output_host, update_result, identity, success_logger
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


def add_host(host_data, platform_metadata, operation_args={}):
    payload_tracker = get_payload_tracker(request_id=threadctx.request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker, processing_status_message="adding/updating host", current_operation="adding/updating host"
    ):
        try:
            identity = _get_identity(host_data, platform_metadata)
            # basic-auth does not need owner_id
            if identity.identity_type == IdentityType.SYSTEM:
                host_data = _set_owner(host_data, identity)

            input_host = deserialize_host(host_data)
            log_add_host_attempt(logger, input_host)
            host_row, add_result = host_repository.add_host(input_host, identity, operation_args=operation_args)
            success_logger = partial(log_add_update_host_succeeded, logger, add_result)

            return host_row, add_result, identity, success_logger
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
def handle_message(message, notification_event_producer, message_operation=add_host):
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
            host_row, operation_result, identity, success_logger = message_operation(
                host, platform_metadata, validated_operation_msg.get("operation_args", {})
            )
            staleness_timestamps = Timestamps.from_config(inventory_config())
            event_type = operation_results_to_event_type(operation_result)
            return OperationResult(
                host_row,
                platform_metadata,
                staleness_timestamps,
                get_staleness_obj(identity),
                event_type,
                success_logger,
            )

        except ValidationException as ve:
            logger.error(
                "Validation error while adding or updating host: %s",
                ve,
                extra={"host": {"reporter": host.get("reporter")}},
            )
            send_notification(
                notification_event_producer,
                notification_type=NotificationType.validation_error,
                host=host,
                detail=str(ve.detail),
            )
            raise
        except InventoryException as ie:
            send_notification(
                notification_event_producer,
                notification_type=NotificationType.validation_error,
                host=host,
                detail=str(ie.detail),
            )
            raise


def write_add_update_event_message(event_producer: EventProducer, result: OperationResult):
    output_host = serialize_host(result.host_row, result.staleness_timestamps, staleness=result.staleness_object)
    insights_id = result.host_row.canonical_facts.get("insights_id")
    event = build_event(result.event_type, output_host, platform_metadata=result.platform_metadata)

    org_id = output_host["org_id"]
    headers = message_headers(
        result.event_type,
        insights_id,
        output_host.get("reporter"),
        output_host.get("system_profile", {}).get("host_type"),
        output_host.get("system_profile", {}).get("operating_system", {}).get("name"),
    )
    event_producer.write_event(event, str(result.host_row.id), headers, wait=True)
    delete_keys(org_id)
    result.success_logger(output_host)


def write_message_batch(event_producer, processed_rows):
    for result in processed_rows:
        if result is not None:
            request_id = result.platform_metadata.get("request_id")
            payload_tracker = get_payload_tracker(request_id=request_id)

            with PayloadTrackerContext(
                payload_tracker,
                received_status_message="host operation complete",
                current_operation="write_message_batch",
            ) as payload_tracker_processing_ctx:
                payload_tracker_processing_ctx.inventory_id = result.host_row.id
                write_add_update_event_message(event_producer, result)


@metrics.export_service_message_handler_time.time()
def handle_export_message(message):
    validated_msg = parse_export_service_message(message)
    if validated_msg and validated_msg["data"]["resource_request"]["application"] == EXPORT_SERVICE_APPLICATION:
        logger.info("Found host-inventory application export message")
        org_id = validated_msg["redhatorgid"]
        if create_export(validated_msg, org_id):
            metrics.export_service_message_handler_success.inc()
            return True
        else:
            metrics.export_service_message_handler_failure.inc()
            return False
    else:
        logger.debug("Found export message not related to host-inventory")
        pass


def export_service_event_loop(consumer, flask_app, interrupt):
    with flask_app.app_context():
        while not interrupt():
            messages = consumer.consume(timeout=CONSUMER_POLL_TIMEOUT_SECONDS)
            for msg in messages:
                if msg is None:
                    continue
                elif msg.error():
                    logger.error(f"Message received but has an error, which is {str(msg.error())}")
                    metrics.ingress_message_handler_failure.inc()
                else:
                    logger.debug("Message received")
                    try:
                        handle_export_message(msg.value())
                        metrics.consumed_message_size.observe(len(str(msg).encode("utf-8")))
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


def event_loop(consumer, flask_app, event_producer, notification_event_producer, handler, interrupt):
    with flask_app.app_context():
        while not interrupt():
            processed_rows = []
            start_time = datetime.now()
            with session_guard(db.session), db.session.no_autoflush:
                while (
                    not interrupt()
                    and (len(processed_rows) < inventory_config().mq_db_batch_max_messages)
                    and (start_time + timedelta(seconds=inventory_config().mq_db_batch_max_seconds) > datetime.now())
                ):
                    messages = consumer.consume(timeout=CONSUMER_POLL_TIMEOUT_SECONDS)

                    commit_batch_early = True
                    for msg in messages:
                        if msg is None:
                            continue
                        elif msg.error():
                            # This error is raised by the first consumer.consume() on a newly started Kafka.
                            # msg.error() produces:
                            # KafkaError{code=UNKNOWN_TOPIC_OR_PART,val=3,str="Subscribed topic not available:
                            #   platform.inventory.host-ingress: Broker: Unknown topic or partition"}
                            logger.error(f"Message received but has an error, which is {str(msg.error())}")
                            metrics.ingress_message_handler_failure.inc()
                        else:
                            logger.debug("Message received")

                            try:
                                processed_rows.append(
                                    handler(
                                        msg.value(),
                                        notification_event_producer=notification_event_producer,
                                    )
                                )
                                commit_batch_early = False
                                metrics.consumed_message_size.observe(len(str(msg).encode("utf-8")))
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

                    # If no messages were consumed, go ahead and commit so we're not waiting for no reason
                    if commit_batch_early:
                        break

                db.session.commit()
                # The above session is automatically committed or rolled back.
                # Now we need to send out messages for the batch of hosts we just processed.
                write_message_batch(event_producer, processed_rows)


def initialize_thread_local_storage(request_id):
    threadctx.request_id = request_id
