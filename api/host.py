from enum import Enum

import connexion
import flask
from flask import current_app
from flask_api import status
from marshmallow import ValidationError

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.host_query import build_paginated_host_list_response
from api.host_query import staleness_timestamps
from api.host_query_db import get_host_list as get_host_list_db
from api.host_query_db import params_to_order_by
from api.host_query_xjoin import get_host_list as get_host_list_xjoin
from app import db
from app import inventory_config
from app import Permission
from app.auth import current_identity
from app.config import BulkQuerySource
from app.exceptions import InventoryException
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import PatchHostSchema
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.queue.event_producer import Topic
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.queue.queue import EGRESS_HOST_FIELDS
from app.serialization import deserialize_canonical_facts
from app.serialization import serialize_host
from app.serialization import serialize_host_system_profile
from app.utils import Tag
from lib.host_delete import delete_hosts
from lib.host_repository import add_host
from lib.host_repository import AddHostResult
from lib.host_repository import find_existing_host
from lib.host_repository import find_non_culled_hosts
from lib.middleware import rbac


FactOperations = Enum("FactOperations", ("merge", "replace"))
TAG_OPERATIONS = ("apply", "remove")
GET_HOST_LIST_FUNCTIONS = {BulkQuerySource.db: get_host_list_db, BulkQuerySource.xjoin: get_host_list_xjoin}
XJOIN_HEADER = "x-rh-cloud-bulk-query-source"  # will be xjoin or db
REFERAL_HEADER = "referer"

logger = get_logger(__name__)


def _convert_host_results_to_http_status(result):
    if result == AddHostResult.created:
        return 201
    else:
        return 200


def _add_host(input_host):
    if not current_identity.is_trusted_system and current_identity.account_number != input_host.account:
        raise InventoryException(
            title="Invalid request",
            detail="The account number associated with the user does not match the account number associated with the "
            "host",
        )

    return add_host(input_host, staleness_timestamps(), update_system_profile=False)


def get_bulk_query_source():
    if XJOIN_HEADER in connexion.request.headers:
        if connexion.request.headers[XJOIN_HEADER].lower() == "xjoin":
            return BulkQuerySource.xjoin
        elif connexion.request.headers[XJOIN_HEADER].lower() == "db":
            return BulkQuerySource.db
    if REFERAL_HEADER in connexion.request.headers:
        if "/beta" in connexion.request.headers[REFERAL_HEADER]:
            return inventory_config().bulk_query_source_beta
    return inventory_config().bulk_query_source


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_list(
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    tags=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    staleness=None,
    registered_with=None,
    filter=None,
):
    total = 0
    host_list = ()

    bulk_query_source = get_bulk_query_source()

    get_host_list = GET_HOST_LIST_FUNCTIONS[bulk_query_source]

    try:
        host_list, total = get_host_list(
            display_name,
            fqdn,
            hostname_or_id,
            insights_id,
            tags,
            page,
            per_page,
            order_by,
            order_how,
            staleness,
            registered_with,
            filter,
        )
    except ValueError as e:
        flask.abort(400, str(e))

    json_data = build_paginated_host_list_response(total, page, per_page, host_list)
    return flask_json_response(json_data)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def delete_by_id(host_id_list):
    payload_tracker = get_payload_tracker(account=current_identity.account_number, request_id=threadctx.request_id)

    with PayloadTrackerContext(
        payload_tracker, received_status_message="delete operation", current_operation="delete"
    ):
        query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

        if not query.count():
            flask.abort(status.HTTP_404_NOT_FOUND)

        for host_id, deleted in delete_hosts(
            query, current_app.event_producer, inventory_config().host_delete_chunk_size
        ):
            if deleted:
                logger.info("Deleted host: %s", host_id)
                tracker_message = "deleted host"
            else:
                logger.info("Host %s already deleted. Delete event not emitted.", host_id)
                tracker_message = "not deleted host"

            with PayloadTrackerProcessingContext(
                payload_tracker, processing_status_message=tracker_message
            ) as payload_tracker_processing_ctx:
                payload_tracker_processing_ctx.inventory_id = host_id

    return flask.Response(None, status.HTTP_200_OK)


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    logger.debug("Found hosts: %s", query_results.items)

    json_data = build_paginated_host_list_response(query_results.total, page, per_page, query_results.items)
    return flask_json_response(json_data)


def _get_host_list_by_id_list(account_number, host_id_list):
    return find_non_culled_hosts(Host.query.filter((Host.account == account_number) & Host.id.in_(host_id_list)))


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_system_profile_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    response_list = [serialize_host_system_profile(host) for host in query_results.items]
    json_output = build_collection_response(response_list, page, per_page, query_results.total)
    return flask_json_response(json_output)


def _emit_patch_event(serialized_host, host_id, insights_id):
    headers = message_headers(EventType.updated, insights_id)
    event = build_event(EventType.updated, serialized_host)
    current_app.event_producer.write_event(event, str(host_id), headers, Topic.events)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def patch_by_id(host_id_list, body):
    try:
        validated_patch_host_data = PatchHostSchema(strict=True).load(body).data
    except ValidationError as e:
        logger.exception(f"Input validation error while patching host: {host_id_list} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    hosts_to_update = query.all()

    if not hosts_to_update:
        logger.debug("Failed to find hosts during patch operation - hosts: %s", host_id_list)
        return flask.abort(status.HTTP_404_NOT_FOUND)

    for host in hosts_to_update:
        host.patch(validated_patch_host_data)

        if db.session.is_modified(host):
            serialized_host = serialize_host(host, staleness_timestamps(), EGRESS_HOST_FIELDS)
            db.session.commit()
            _emit_patch_event(serialized_host, host.id, host.canonical_facts.get("insights_id"))

    return 200


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def replace_facts(host_id_list, namespace, body):
    return update_facts_by_namespace(FactOperations.replace, host_id_list, namespace, body)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def merge_facts(host_id_list, namespace, body):
    if not body:
        error_msg = "ERROR: Invalid request.  Merging empty facts into existing facts is a no-op."
        logger.debug(error_msg)
        return error_msg, 400

    return update_facts_by_namespace(FactOperations.merge, host_id_list, namespace, body)


def update_facts_by_namespace(operation, host_id_list, namespace, fact_dict):
    hosts_to_update = find_non_culled_hosts(
        Host.query.filter(
            (Host.account == current_identity.account_number)
            & Host.id.in_(host_id_list)
            & Host.facts.has_key(namespace)  # noqa: W601 JSONB query filter, not a dict
        )
    ).all()

    logger.debug("hosts_to_update:%s", hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = (
            "ERROR: The number of hosts requested does not match the number of hosts found in the host database.  "
            "This could happen if the namespace does not exist or the account number associated with the call does "
            "not match the account number associated with one or more the hosts.  Rejecting the fact change request."
        )
        logger.debug(error_msg)
        return error_msg, 400

    for host in hosts_to_update:
        if operation is FactOperations.replace:
            host.replace_facts_in_namespace(namespace, fact_dict)
        else:
            host.merge_facts_in_namespace(namespace, fact_dict)

    db.session.commit()

    logger.debug("hosts_to_update:%s", hosts_to_update)

    return 200


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_tag_count(host_id_list, page=1, per_page=100, order_by=None, order_how=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query = query.paginate(page, per_page, True)

    counts = _count_tags(query.items)

    return _build_paginated_host_tags_response(query.total, page, per_page, counts)


# returns counts in format [{id: count}, {id: count}]
def _count_tags(host_list):
    counts = {}

    for host in host_list:
        host_tag_count = 0
        if host.tags is not None:  # fixme: Host tags should never be None, in DB neither NULL nor 'null'
            for namespace in host.tags:
                for tag in host.tags[namespace]:
                    if len(host.tags[namespace][tag]) == 0:
                        host_tag_count += 1  # for tags with no value
                    else:
                        host_tag_count += len(host.tags[namespace][tag])
        counts[str(host.id)] = host_tag_count

    return counts


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_tags(host_id_list, page=1, per_page=100, order_by=None, order_how=None, search=None):
    query = _get_host_list_by_id_list(current_identity.account_number, host_id_list)

    try:
        order_by = params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)

    query = query.paginate(page, per_page, True)

    tags = _build_serialized_tags(query.items, search)

    return _build_paginated_host_tags_response(query.total, page, per_page, tags)


def _build_serialized_tags(host_list, search):
    response_tags = {}

    for host in host_list:
        if search is None:
            tags = Tag.create_tags_from_nested(host.tags)
        else:
            tags = Tag.filter_tags(Tag.create_tags_from_nested(host.tags), search)
        tag_dictionaries = []
        for tag in tags:
            tag_dictionaries.append(tag.data())

        response_tags[str(host.id)] = tag_dictionaries

    return response_tags


def _build_paginated_host_tags_response(total, page, per_page, tags_list):
    json_output = build_collection_response(tags_list, page, per_page, total)
    return flask_json_response(json_output)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def host_checkin(body):
    canonical_facts = deserialize_canonical_facts(body)
    existing_host = find_existing_host(current_identity.account_number, canonical_facts)

    if existing_host:
        existing_host._update_modified_date()
        db.session.commit()
        serialized_host = serialize_host(existing_host, staleness_timestamps(), EGRESS_HOST_FIELDS)
        _emit_patch_event(serialized_host, existing_host.id, existing_host.canonical_facts.get("insights_id"))
        return flask_json_response(serialized_host, 201)
    else:
        flask.abort(404, "No hosts match the provided canonical facts.")
