from http import HTTPStatus
from threading import Thread

import sqlalchemy as sa
from flask import Flask
from flask import abort
from flask import current_app
from marshmallow import ValidationError
from sqlalchemy import orm
from sqlalchemy.engine.base import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapper
from sqlalchemy.orm.exc import NoResultFound

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.cache import delete_cached_system_keys
from api.host_query import staleness_timestamps
from api.staleness_query import get_staleness_obj
from app import KesselResourceTypes, RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.instrumentation import log_create_staleness_failed
from app.instrumentation import log_create_staleness_succeeded
from app.instrumentation import log_patch_staleness_succeeded
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import Staleness
from app.models import StalenessSchema
from app.queue.events import EventType
from app.queue.events import build_event
from app.queue.events import message_headers
from app.serialization import serialize_host
from app.serialization import serialize_staleness_response
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness_api
from lib.db import session_guard
from lib.host_repository import host_query
from lib.middleware import access
from lib.staleness import add_staleness
from lib.staleness import patch_staleness
from lib.staleness import remove_staleness

logger = get_logger(__name__)


def _validate_input_data(body):
    # Validate account staleness input data
    try:
        identity = get_current_identity()
        staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity.org_id))
        validated_data = StalenessSchema().load({**staleness_obj, **body})

        return validated_data

    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        abort(HTTPStatus.BAD_REQUEST, f"Validation Error: {str(e.messages)}")


@sa.event.listens_for(Host, "before_update")
def receive_before_host_update(mapper: Mapper, connection: Connection, host: Host):  # noqa: ARG001
    """Prevent host modified_on update during staleness updates.

    This SQLAlchemy event listener, triggered before any host update,
    prevents the ``modified_on`` timestamp from being updated when only
    the ``per_reporter_staleness`` field is changed.  This avoids
    unnecessary updates as ``modified_on`` is automatically updated for
    every change to a Host object, which can lead to confusion to the user.

    For more details on SQLAlchemy event listeners, see:
    https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_update

    :param mapper: The SQLAlchemy mapper.
    :param connection: The database connection.
    :param host: The Host object being updated.
    """
    host_details = sa.inspect(host)
    prs_changed, _, _ = host_details.attrs.per_reporter_staleness.history
    staleness_changed, _, _ = host_details.attrs.deletion_timestamp.history
    if prs_changed or staleness_changed:
        orm.attributes.flag_modified(host, "modified_on")


def _update_hosts_staleness_async(identity: Identity, app: Flask, staleness: Staleness, request_id):
    with app.app_context():
        threadctx.request_id = request_id
        logger.debug("Starting host staleness update thread")
        try:
            logger.debug(f"Querying hosts for org_id: {identity.org_id}")
            hosts_query = host_query(identity.org_id)
            num_hosts = hosts_query.count()
            st = staleness_timestamps()
            staleness_dict = serialize_staleness_to_dict(staleness)
            if num_hosts > 0:
                logger.debug(f"Found {num_hosts} hosts for org_id: {identity.org_id}")

                # Process hosts in batches to avoid memory issues with large datasets
                processed_hosts = 0

                while processed_hosts < num_hosts:
                    list_of_events_params = []

                    # Get a batch of hosts
                    batch_hosts = hosts_query.offset(processed_hosts).limit(500).all()
                    if not batch_hosts:
                        break

                    with session_guard(hosts_query.session):
                        for host in batch_hosts:
                            host._update_all_per_reporter_staleness(staleness_dict, st)
                            host._update_staleness_timestamps()
                            serialized_host = serialize_host(
                                host, for_mq=True, staleness_timestamps=st, staleness=staleness_dict
                            )

                            # Create host update event and append it to an array
                            event, headers = _build_host_updated_event_params(serialized_host, host, identity)
                            list_of_events_params.append((event, headers, str(host.id)))

                        processed_hosts += len(batch_hosts)
                        logger.debug(f"Updated staleness asynchronously for {processed_hosts}/{num_hosts} hosts")

                    # After a successful commit to the db
                    # call all the events in the list
                    for event, headers, host_id in list_of_events_params:
                        app.event_producer.write_event(event, host_id, headers, wait=True)

                delete_cached_system_keys(org_id=identity.org_id, spawn=True)
            logger.debug("Leaving host staleness update thread")
        except Exception as e:
            raise e


def _build_host_updated_event_params(serialized_host: dict, host: Host, identity: Identity):
    headers = message_headers(
        EventType.updated,
        host.canonical_facts.get("insights_id"),
        host.reporter,
        host.system_profile_facts.get("host_type"),
        host.system_profile_facts.get("operating_system", {}).get("name"),
        str(host.system_profile_facts.get("bootc_status", {}).get("booted") is not None),
    )
    metadata = {"b64_identity": to_auth_header(identity)}
    event = build_event(EventType.updated, serialized_host, platform_metadata=metadata)
    return event, headers


def _async_update_host_staleness(identity: Identity, created_staleness: Staleness, request_id):
    """
    This method starts a new thread to update the host staleness.
    """
    update_hosts_thread = Thread(
        target=_update_hosts_staleness_async,
        daemon=True,
        args=(
            identity,
            current_app._get_current_object(),
            created_staleness,
            request_id,
        ),
    )
    update_hosts_thread.start()


@api_operation
@access(KesselResourceTypes.STALENESS.view)
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_staleness(rbac_filter=None):  # noqa: ARG001, 'rbac_filter' is required for all API endpoints
    try:
        staleness = get_staleness_obj(get_current_identity().org_id)
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@access(KesselResourceTypes.STALENESS.view)
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_default_staleness(rbac_filter=None):  # noqa: ARG001, 'rbac_filter' is required for all API endpoints
    try:
        identity = get_current_identity()
        staleness = get_sys_default_staleness_api(identity)
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@access(KesselResourceTypes.STALENESS.update, writeOperation=True)
@access(KesselResourceTypes.HOST.update, writeOperation=True)
@metrics.api_request_time.time()
def create_staleness(body):
    # Validate account staleness input data
    identity = get_current_identity()
    org_id = identity.org_id
    request_id = threadctx.request_id
    try:
        validated_data = _validate_input_data(body)
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    try:
        # Create account staleness with validated data
        created_staleness = add_staleness(validated_data)
        _async_update_host_staleness(identity, created_staleness, request_id)
        log_create_staleness_succeeded(logger, created_staleness.id)
    except IntegrityError:
        error_message = f"Staleness record for org_id {org_id} already exists."

        log_create_staleness_failed(logger, org_id)
        logger.exception(error_message)
        return json_error_response("Integrity error", error_message, HTTPStatus.BAD_REQUEST)

    return flask_json_response(serialize_staleness_response(created_staleness), HTTPStatus.CREATED)


@api_operation
@access(KesselResourceTypes.STALENESS.update, writeOperation=True)
@access(KesselResourceTypes.HOST.update, writeOperation=True)
@metrics.api_request_time.time()
def delete_staleness():
    identity = get_current_identity()
    org_id = identity.org_id
    request_id = threadctx.request_id
    try:
        remove_staleness()
        staleness = get_sys_default_staleness_api(identity)
        _async_update_host_staleness(identity, staleness, request_id)
        return flask_json_response(None, HTTPStatus.NO_CONTENT)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )


@api_operation
@access(KesselResourceTypes.STALENESS.update, writeOperation=True)
@access(KesselResourceTypes.HOST.update, writeOperation=True)
@metrics.api_request_time.time()
def update_staleness(body):
    # Validate account staleness input data
    try:
        validated_data = _validate_input_data(body)
        request_id = threadctx.request_id
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    identity = get_current_identity()
    org_id = identity.org_id
    try:
        updated_staleness = patch_staleness(validated_data)
        if updated_staleness is None:
            # since update only return None with no record instead of exception.
            raise NoResultFound

        _async_update_host_staleness(identity, updated_staleness, request_id)

        log_patch_staleness_succeeded(logger, updated_staleness.id)

        return flask_json_response(serialize_staleness_response(updated_staleness), HTTPStatus.OK)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )
