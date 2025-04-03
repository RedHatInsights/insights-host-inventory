from __future__ import annotations

import base64
import json
import sys
from copy import deepcopy
from functools import partial
from uuid import UUID

from confluent_kafka import Consumer
from flask.app import Flask
from marshmallow import Schema
from marshmallow import ValidationError
from marshmallow import fields
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from api.cache import delete_cached_system_keys
from api.cache import set_cached_system
from api.cache_key import make_system_cache_key
from api.staleness_query import get_staleness_obj
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.auth.identity import create_mock_identity_with_org_id
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
from app.models import Host
from app.models import HostGroupAssoc
from app.models import LimitedHostSchema
from app.models import db
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.payload_tracker import get_payload_tracker
from app.queue import metrics
from app.queue.event_producer import EventProducer
from app.queue.events import HOST_EVENT_TYPE_CREATED
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.queue.events import operation_results_to_event_type
from app.queue.mq_common import common_message_parser
from app.queue.notifications import NotificationType
from app.queue.notifications import send_notification
from app.serialization import deserialize_host
from app.serialization import remove_null_canonical_facts
from app.serialization import serialize_group
from app.serialization import serialize_host
from lib import group_repository
from lib import host_repository
from lib.db import session_guard
from lib.feature_flags import FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION
from lib.feature_flags import FLAG_INVENTORY_USE_CACHED_INSIGHTS_CLIENT_SYSTEM
from lib.feature_flags import get_flag_value
from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity
from utils.system_profile_log import extract_host_dict_sp_to_log

logger = get_logger(__name__)

CONSUMER_POLL_TIMEOUT_SECONDS = 0.5
SYSTEM_IDENTITY = {"auth_type": "cert-auth", "system": {"cert_type": "system"}, "type": "System"}


class HostOperationSchema(Schema):
    operation = fields.Str(required=True)
    operation_args = fields.Dict()
    platform_metadata = fields.Dict()
    data = fields.Dict(required=True)


class WorkspaceSchema(Schema):
    id = fields.UUID(required=True)
    name = fields.Str(required=True)
    type = fields.Str()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class WorkspaceOperationSchema(Schema):
    operation = fields.Str(required=True)
    org_id = fields.Str(required=True)
    workspace = fields.Nested(WorkspaceSchema)


# Helper class to facilitate batch operations
class OperationResult:
    def __init__(self, hr, pm, st, so, et, sl):
        self.host_row = hr
        self.platform_metadata = pm
        self.staleness_timestamps = st
        self.staleness_object = so
        self.event_type = et
        self.success_logger = sl


class HBIMessageConsumerBase:
    def __init__(
        self,
        consumer: Consumer,
        flask_app: Flask,
        event_producer: EventProducer,
        notification_event_producer: EventProducer,
    ) -> None:
        self.consumer = consumer
        self.flask_app = flask_app
        self.event_producer = event_producer
        self.notification_event_producer = notification_event_producer

    def process_message(self, *args, **kwargs):
        raise NotImplementedError("Not implemented in the HBIMessageConsumerBase class")

    @metrics.ingress_message_handler_time.time()
    def handle_message(self, *args, **kwargs) -> OperationResult | None:
        raise NotImplementedError("Not implemented in the HBIMessageConsumerBase class")

    def post_process_rows(self, processed_rows: list[OperationResult]):
        pass  # No action is taken by default

    def event_loop(self, interrupt):
        with self.flask_app.app.app_context():
            while not interrupt():
                processed_rows: list[OperationResult] = []
                with session_guard(db.session), db.session.no_autoflush:
                    messages = self.consumer.consume(
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

                            try:
                                processed_rows.append(self.handle_message(msg.value()))
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

                    self.post_process_rows(processed_rows)


class WorkspaceMessageConsumer(HBIMessageConsumerBase):
    @metrics.ingress_message_handler_time.time()
    def handle_message(self, message):
        validated_operation_msg = parse_operation_message(message, WorkspaceOperationSchema)
        initialize_thread_local_storage(None)  # No request_id for workspace MQ
        operation = validated_operation_msg["operation"]
        org_id = validated_operation_msg["org_id"]
        workspace = validated_operation_msg["workspace"]
        identity = create_mock_identity_with_org_id(org_id)

        if operation == "create":
            group_repository.add_group(
                group_name=workspace["name"],
                org_id=org_id,
                group_id=workspace["id"],
                ungrouped=(validated_operation_msg["workspace"]["type"] == "ungrouped-hosts"),
            )
        elif operation == "update":
            group_to_update = group_repository.get_group_by_id_from_db(str(workspace["id"]), org_id)
            group_repository.patch_group(
                group=group_to_update,
                patch_data=workspace,
                identity=identity,
                event_producer=self.event_producer,
            )
        elif operation == "delete":
            group_repository.delete_group_list(
                group_id_list=[str(workspace["id"])],
                identity=identity,
                event_producer=self.event_producer,
            )
        else:
            raise ValidationError("Operation must be 'create', 'update', or 'delete'.")


class HostMessageConsumer(HBIMessageConsumerBase):
    @metrics.ingress_message_handler_time.time()
    def handle_message(self, message) -> OperationResult:
        validated_operation_msg = parse_operation_message(message, HostOperationSchema)
        platform_metadata = validated_operation_msg.get("platform_metadata", {})

        request_id = platform_metadata.get("request_id")
        initialize_thread_local_storage(request_id)

        payload_tracker = get_payload_tracker(request_id=request_id)

        with PayloadTrackerContext(
            payload_tracker, received_status_message="message received", current_operation="handle_message"
        ):
            try:
                host = validated_operation_msg["data"]
                host_row, operation_result, identity, success_logger = self.process_message(
                    host, platform_metadata, validated_operation_msg.get("operation_args", {})
                )
                staleness_timestamps = Timestamps.from_config(inventory_config())
                event_type = operation_results_to_event_type(operation_result)

                return OperationResult(
                    host_row,
                    platform_metadata,
                    staleness_timestamps,
                    get_staleness_obj(identity.org_id),
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
                    self.notification_event_producer,
                    notification_type=NotificationType.validation_error,
                    host=host,
                    detail=str(ve.detail),
                )
                raise
            except InventoryException as ie:
                send_notification(
                    self.notification_event_producer,
                    notification_type=NotificationType.validation_error,
                    host=host,
                    detail=str(ie.detail),
                )
                raise

    def post_process_rows(self, processed_rows: list[OperationResult]) -> None:
        try:
            if len(processed_rows) > 0:
                db.session.commit()
                # The above session is automatically committed or rolled back.
                # Now we need to send out messages for the batch of hosts we just processed.
                write_message_batch(self.event_producer, self.notification_event_producer, processed_rows)

        except StaleDataError as exc:
            metrics.ingress_message_handler_failure.inc(amount=len(processed_rows))
            logger.error(
                f"Session data is stale; failed to commit data from {len(processed_rows)} payloads.",
                exc_info=exc,
            )
            db.session.rollback()


class IngressMessageConsumer(HostMessageConsumer):
    def process_message(self, host_data, platform_metadata, operation_args=None):
        if operation_args is None:
            operation_args = {}

        sp_fields_to_log = extract_host_dict_sp_to_log(host_data)
        try:
            identity = _get_identity(host_data, platform_metadata)
            input_host = deserialize_host(host_data)

            # basic-auth does not need owner_id
            if identity.identity_type == IdentityType.SYSTEM:
                input_host = _set_owner(input_host, identity)

            log_add_host_attempt(logger, input_host, sp_fields_to_log, identity)
            host_row, add_result = host_repository.add_host(input_host, identity, operation_args=operation_args)

            # If this is a new host, assign it to the "ungrouped hosts" group/workspace
            if add_result == host_repository.AddHostResult.created and get_flag_value(
                FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION
            ):
                # Get org's "ungrouped hosts" group (create if not exists) and assign host to it
                group = get_or_create_ungrouped_hosts_group_for_identity(identity)
                assoc = HostGroupAssoc(host_row.id, group.id)
                db.session.add(assoc)
                host_row.groups = [serialize_group(group, identity.org_id)]
                db.session.flush()

            success_logger = partial(log_add_update_host_succeeded, logger, add_result, sp_fields_to_log)

            return host_row, add_result, identity, success_logger
        except ValidationException:
            metrics.add_host_failure.labels("ValidationException", host_data.get("reporter", "null")).inc()
            raise
        except InventoryException as ie:
            log_add_host_failure(logger, str(ie.detail), host_data, sp_fields_to_log)
            raise
        except OperationalError as oe:
            log_db_access_failure(logger, f"Could not access DB {str(oe)}", host_data)
            raise oe
        except Exception:
            logger.exception("Error while adding host", extra={"host": host_data, "system_profile": sp_fields_to_log})
            metrics.add_host_failure.labels("Exception", host_data.get("reporter", "null")).inc()
            raise


class SystemProfileMessageConsumer(HostMessageConsumer):
    def process_message(self, host_data, platform_metadata, operation_args=None):  # noqa: ARG002, required by process_message
        if operation_args is None:
            operation_args = {}

        sp_fields_to_log = extract_host_dict_sp_to_log(host_data)

        try:
            input_host = deserialize_host(host_data, schema=LimitedHostSchema)
            input_host.id = host_data.get("id")
            identity = create_mock_identity_with_org_id(input_host.org_id)
            output_host, update_result = host_repository.update_system_profile(input_host, identity)
            success_logger = partial(log_update_system_profile_success, logger, sp_fields_to_log)
            return output_host, update_result, identity, success_logger
        except ValidationException:
            metrics.update_system_profile_failure.labels("ValidationException").inc()
            raise
        except InventoryException:
            log_update_system_profile_failure(logger, host_data, sp_fields_to_log)
            raise
        except OperationalError as oe:
            log_db_access_failure(logger, f"Could not access DB {str(oe)}", host_data)
            raise oe
        except Exception:
            logger.exception(
                "Error while updating host system profile",
                extra={"host": host_data, "system_profile": sp_fields_to_log},
            )
            metrics.update_system_profile_failure.labels("Exception").inc()
            raise


# input is a base64 encoded utf-8 string. b64decode returns bytes, which
# again needs decoding using ascii to get human readable dictionary
def _decode_id(encoded_id):
    id = base64.b64decode(encoded_id)
    decoded_id = json.loads(id)
    return decoded_id.get("identity")


# receives an uuid string w/o dashes and outputs an uuid string with dashes
def _formatted_uuid(uuid_string):
    return str(UUID(uuid_string))


def _get_identity(host, metadata) -> Identity:
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
        raise ValidationException(str(e)) from e
    return identity


# When identity_type is System, set owner_id if missing from the host system_profile
def _set_owner(host: Host, identity: Identity) -> Host:
    cn = identity.system.get("cn")
    if host.system_profile_facts is None:
        host.system_profile_facts = {}
        host.system_profile_facts["owner_id"] = cn
    elif not host.system_profile_facts.get("owner_id"):
        host.system_profile_facts["owner_id"] = cn
    else:
        reporter = host.reporter
        if (
            reporter in ["rhsm-conduit", "rhsm-system-profile-bridge"]
            and "subscription_manager_id" in host.canonical_facts
        ):
            host.system_profile_facts["owner_id"] = _formatted_uuid(host.canonical_facts["subscription_manager_id"])
        else:
            if host.system_profile_facts["owner_id"] != cn:
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
def parse_operation_message(message, schema: Schema):
    parsed_message = common_message_parser(message)

    try:
        _validate_json_object_for_utf8(parsed_message)
    except UnicodeEncodeError:
        logger.exception("Invalid Unicode sequence in message from message queue", extra={"incoming_message": message})
        metrics.ingress_message_parsing_failure.labels("invalid").inc()
        raise

    try:
        parsed_operation = schema().load(parsed_message)
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


def write_delete_event_message(event_producer: EventProducer, result: OperationResult, initiated_by_frontend: bool):
    event = build_event(
        EventType.delete,
        result.host_row,
        platform_metadata=result.platform_metadata,
        initiated_by_frontend=initiated_by_frontend,
    )
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
        # Notifications are expected to omit null canonical facts
        remove_null_canonical_facts(output_host)
        send_notification(
            notification_event_producer,
            notification_type=NotificationType.new_system_registered,
            host=output_host,
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
    processed_rows: list[OperationResult],
):
    for result in processed_rows:
        if result is not None:
            try:
                write_add_update_event_message(event_producer, notification_event_producer, result)
            except Exception as exc:
                metrics.ingress_message_handler_failure.inc()
                logger.exception("Error while producing message", exc_info=exc)


def initialize_thread_local_storage(request_id: str, org_id: str | None = None, account: str | None = None):
    threadctx.request_id = request_id
    if org_id:
        threadctx.org_id = org_id
    if account:
        threadctx.account = account
