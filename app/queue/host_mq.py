import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import partial
from typing import List
from uuid import UUID

from marshmallow import fields
from marshmallow import Schema
from marshmallow import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from api.cache import delete_cached_system_keys
from api.cache import set_cached_system
from api.cache_key import make_system_cache_key
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
from app.instrumentation import log_message_consumed
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
from app.queue.events import HOST_EVENT_TYPE_CREATED
from app.queue.events import message_headers
from app.queue.events import operation_results_to_event_type
from app.queue.mq_common import common_message_parser
from app.queue.notifications import NotificationType
from app.queue.notifications import send_notification
from app.serialization import deserialize_host
from app.serialization import serialize_host
from lib import host_repository
from lib.db import session_guard
from lib.feature_flags import FLAG_INVENTORY_USE_CACHED_INSIGHTS_CLIENT_SYSTEM
from lib.feature_flags import get_flag_value

logger = get_logger(__name__)

CONSUMER_POLL_TIMEOUT_SECONDS = 0.5
SYSTEM_IDENTITY = {"auth_type": "cert-auth", "system": {"cert_type": "system"}, "type": "System"}


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
                str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
            )
            # add back "wait=True", if needed.
            event_producer.write_event(event, host.id, headers, wait=True)

    return


def update_system_profile(host_data, platform_metadata, notification_event_producer=None, operation_args={}):
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


def add_host(host_data, platform_metadata, notification_event_producer, operation_args={}):
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
                host, platform_metadata, notification_event_producer, validated_operation_msg.get("operation_args", {})
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


def write_delete_event_message(event_producer: EventProducer, result: OperationResult):
    event = build_event(EventType.delete, result.host_row, platform_metadata=result.platform_metadata)
    headers = message_headers(
        EventType.delete,
        result.host_row.canonical_facts.get("insights_id"),
        result.host_row.reporter,
        result.host_row.system_profile_facts.get("host_type"),
        result.host_row.system_profile_facts.get("operating_system", {}).get("name"),
        str(result.host_row.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
    )
    event_producer.write_event(event, str(result.host_row.id), headers, wait=True)
    insights_id = result.host_row.canonical_facts.get("insights_id")
    owner_id = result.host_row.system_profile_facts.get("owner_id")
    if insights_id and owner_id:
        delete_cached_system_keys(
            insights_id=insights_id, org_id=result.host_row.org_id, owner_id=owner_id, spawn=True
        )
    result.success_logger()


def write_add_update_event_message(
    event_producer: EventProducer, notification_event_producer: EventProducer, result: OperationResult
):
    # The request ID in the headers is fetched from threadctx.request_id
    request_id = result.platform_metadata.get("request_id")
    initialize_thread_local_storage(request_id, result.host_row.org_id, result.host_row.account)
    payload_tracker = get_payload_tracker(request_id=request_id)

    with PayloadTrackerProcessingContext(
        payload_tracker,
        processing_status_message="host operation complete",
        current_operation="write_message_batch",
        inventory_id=result.host_row.id,
    ):
        output_host = serialize_host(result.host_row, result.staleness_timestamps, staleness=result.staleness_object)
        insights_id = result.host_row.canonical_facts.get("insights_id")
        event = build_event(result.event_type, output_host, platform_metadata=result.platform_metadata)

        headers = message_headers(
            result.event_type,
            insights_id,
            output_host.get("reporter"),
            output_host.get("system_profile", {}).get("host_type"),
            output_host.get("system_profile", {}).get("operating_system", {}).get("name"),
            str(output_host.get("system_profile", {}).get("bootc_status", {}).get("booted") is not None),
        )

    event_producer.write_event(event, str(result.host_row.id), headers, wait=True)

    if result.event_type.name == HOST_EVENT_TYPE_CREATED:
        send_notification(
            notification_event_producer,
            notification_type=NotificationType.new_system_registered,
            host=serialize_host(
                result.host_row,
                staleness_timestamps=result.staleness_timestamps,
                staleness=result.staleness_object,
                omit_null_facts=True,
            ),
        )
    result.success_logger(output_host)

    org_id = output_host.get("org_id")
    if get_flag_value(FLAG_INVENTORY_USE_CACHED_INSIGHTS_CLIENT_SYSTEM):
        try:
            owner_id = output_host.get("system_profile", {}).get("owner_id")
            if owner_id and insights_id and org_id:
                system_key = make_system_cache_key(insights_id, org_id, owner_id)
                if "tags" in output_host:
                    del output_host["tags"]
                if "system_profile" in output_host:
                    del output_host["system_profile"]
                set_cached_system(system_key, output_host, inventory_config())
        except Exception as ex:
            logger.error("Error during set cache", ex)


def write_message_batch(
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    processed_rows: List[OperationResult],
    app,
):
    with app.app_context():
        print(">>> WRITING MESSAGE BATCH")
        logger.info(">>> WRITING MESSAGE BATCH")
        for result in processed_rows:
            if result is not None:
                try:
                    write_add_update_event_message(event_producer, notification_event_producer, result)
                except Exception as exc:
                    metrics.ingress_message_handler_failure.inc()
                    logger.exception("Error while producing message", exc_info=exc)

    return True


def event_loop(consumer, flask_app, event_producer, notification_event_producer, handler, interrupt):
    with flask_app.app_context(), ThreadPoolExecutor(max_workers=4) as executor:
        while not interrupt():
            processed_rows = []
            with session_guard(db.session), db.session.no_autoflush:
                messages = consumer.consume(
                    num_messages=inventory_config().mq_db_batch_max_messages,
                    timeout=inventory_config().mq_db_batch_max_seconds,
                )

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
                        log_message_consumed(logger, msg)

                        try:
                            # TODO: Check whether the incoming host payload would match to any of the records
                            # we've already processed in the batch.
                            # Reuse logic from host_repository.find_existing_host? This one will be hard

                            # TODO: Check whether the host ID for the record we just processed
                            # already exists in the current batch

                            # We might be able to prevent this issue if we turn System Profile into a table
                            # instead of jsonb. After we do that, we should be able to update specific columns
                            # on the row rather than replacing it wholesale

                            processed_rows.append(
                                handler(
                                    msg.value(),
                                    notification_event_producer=notification_event_producer,
                                )
                            )
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

                try:
                    if len(processed_rows) > 0:
                        db.session.commit()
                        # The above session is automatically committed or rolled back.
                        # Now we need to send out messages for the batch of hosts we just processed.
                        logger.info("Submitting message batch")
                        future = executor.submit(
                            partial(
                                write_message_batch,
                                event_producer,
                                notification_event_producer,
                                processed_rows,
                                flask_app,
                            )
                        )

                        logger.info("After write message batch")
                        print(f">>> future result: {future.result()}")

                except StaleDataError as exc:
                    metrics.ingress_message_handler_failure.inc(amount=len(messages))
                    logger.error(
                        f"Session data is stale; failed to commit data from {len(messages)} payloads.", exc_info=exc
                    )
                    db.session.rollback()


def initialize_thread_local_storage(request_id: str, org_id: str = None, account: str = None):
    threadctx.request_id = request_id
    if org_id:
        threadctx.org_id = org_id
    if account:
        threadctx.account = account
