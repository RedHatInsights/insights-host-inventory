from enum import Enum
from http import HTTPStatus

import flask
from confluent_kafka.error import KafkaError
from flask import current_app
from httpx import InvalidURL
from marshmallow import ValidationError

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.cache import CACHE
from api.cache import delete_keys
from api.cache_key import make_key
from api.host_query import build_paginated_host_list_response
from api.host_query import staleness_timestamps
from api.host_query_db import get_all_hosts
from api.host_query_db import get_host_ids_list as get_host_ids_list_postgres
from api.host_query_db import get_host_list as get_host_list_postgres
from api.host_query_db import get_host_list_by_id_list as get_host_list_by_id_list_postgres
from api.host_query_db import get_host_tags_list_by_id_list as get_host_tags_list_by_id_list_postgres
from api.host_query_db import get_sparse_system_profile as get_sparse_system_profile_postgres
from api.host_query_xjoin import get_host_ids_list as get_host_ids_list_xjoin
from api.host_query_xjoin import get_host_list as get_host_list_xjoin
from api.host_query_xjoin import get_host_list_by_id_list as get_host_list_by_id_list_xjoin
from api.host_query_xjoin import get_host_tags_list_by_id_list
from api.sparse_host_list_system_profile import get_sparse_system_profile
from api.staleness_query import get_staleness_obj
from app import db
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.auth.identity import to_auth_header
from app.common import inventory_config
from app.exceptions import InventoryException, ValidationException
from app.instrumentation import get_control_rule
from app.instrumentation import log_get_host_list_failed
from app.instrumentation import log_get_host_list_succeeded
from app.instrumentation import log_patch_host_failed
from app.instrumentation import log_patch_host_success
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import HostGroupAssoc
from app.models import PatchHostSchema
from app.payload_tracker import get_payload_tracker
from app.payload_tracker import PayloadTrackerContext
from app.payload_tracker import PayloadTrackerProcessingContext
from app.queue.events import build_event
from app.queue.events import EventType
from app.queue.events import message_headers
from app.serialization import deserialize_canonical_facts
from app.serialization import serialize_host
from app.utils import Tag
from app.xjoin import pagination_params
from lib.feature_flags import FLAG_INVENTORY_DISABLE_XJOIN
from lib.feature_flags import get_flag_value
from lib.host_delete import delete_hosts
from lib.host_repository import find_existing_host
from lib.host_repository import find_non_culled_hosts
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.host_repository import update_query_for_owner_id
from lib.middleware import ensure_org_data_integrity
from lib.middleware import rbac
from lib.middleware import throttled_response


FactOperations = Enum("FactOperations", ("merge", "replace"))
TAG_OPERATIONS = ("apply", "remove")

logger = get_logger(__name__)


@api_operation
@CACHE.cached(key_prefix=make_key)
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@ensure_org_data_integrity()
@throttled_response()
@metrics.api_request_time.time()
def get_host_list(
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    group_name=None,
    tags=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    staleness=None,
    registered_with=None,
    filter=None,
    fields=None,
    rbac_filter=None,
):
    total = 0
    host_list = ()
    current_identity = get_current_identity()
    is_bootc = filter.get("system_profile", {}).get("bootc_status")

    try:
        if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}) or is_bootc:
            logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
            host_list, total, additional_fields, system_profile_fields = get_host_list_postgres(
                display_name,
                fqdn,
                hostname_or_id,
                insights_id,
                provider_id,
                provider_type,
                updated_start,
                updated_end,
                group_name,
                tags,
                page,
                per_page,
                order_by,
                order_how,
                staleness,
                registered_with,
                filter,
                fields,
                rbac_filter,
            )
        else:
            host_list, total, additional_fields, system_profile_fields = get_host_list_xjoin(
                display_name,
                fqdn,
                hostname_or_id,
                insights_id,
                provider_id,
                provider_type,
                updated_start,
                updated_end,
                group_name,
                tags,
                page,
                per_page,
                order_by,
                order_how,
                staleness,
                registered_with,
                filter,
                fields,
                rbac_filter,
            )
    except (InvalidURL, ValidationException, ValueError) as e:
        log_get_host_list_failed(logger)
        flask.abort(400, str(e))

    json_data = build_paginated_host_list_response(
        total, page, per_page, host_list, additional_fields, system_profile_fields
    )
    return flask_json_response(json_data)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def delete_hosts_by_filter(
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    group_name=None,
    registered_with=None,
    staleness=None,
    tags=None,
    filter=None,
    rbac_filter=None,
):
    if not any(
        [
            display_name,
            fqdn,
            hostname_or_id,
            insights_id,
            provider_id,
            provider_type,
            updated_start,
            updated_end,
            group_name,
            registered_with,
            staleness,
            tags,
            filter,
        ]
    ):
        logger.error("bulk-delete operation needs at least one input property to filter on.")
        flask.abort(400, "bulk-delete operation needs at least one input property to filter on.")

    try:
        current_identity = get_current_identity()
        is_bootc = filter.get("system_profile", {}).get("bootc_status")
        if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}) or is_bootc:
            logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
            ids_list = get_host_ids_list_postgres(
                display_name,
                fqdn,
                hostname_or_id,
                insights_id,
                provider_id,
                provider_type,
                updated_start,
                updated_end,
                group_name,
                registered_with,
                staleness,
                tags,
                filter,
                rbac_filter,
            )
        else:
            ids_list = get_host_ids_list_xjoin(
                display_name,
                fqdn,
                hostname_or_id,
                insights_id,
                provider_id,
                provider_type,
                updated_start,
                updated_end,
                group_name,
                registered_with,
                staleness,
                tags,
                filter,
                rbac_filter,
            )
    except ValueError as err:
        log_get_host_list_failed(logger)
        flask.abort(400, str(err))
    except ConnectionError:
        logger.error("xjoin-search not accessible")
        flask.abort(503)

    try:
        delete_count = _delete_host_list(ids_list, rbac_filter) if ids_list else 0
    except KafkaError:
        logger.error("Kafka server not available")
        flask.abort(503)

    json_data = {"hosts_found": len(ids_list), "hosts_deleted": delete_count}

    return flask_json_response(json_data, HTTPStatus.ACCEPTED)


def _delete_host_list(host_id_list, rbac_filter):
    current_identity = get_current_identity()
    payload_tracker = get_payload_tracker(
        account=current_identity.account_number, org_id=current_identity.org_id, request_id=threadctx.request_id
    )

    with PayloadTrackerContext(
        payload_tracker, received_status_message="delete operation", current_operation="delete"
    ):
        query = get_host_list_by_id_list_from_db(host_id_list, rbac_filter)

        result_list = delete_hosts(
            query,
            current_app.event_producer,
            current_app.notification_event_producer,
            inventory_config().host_delete_chunk_size,
            identity=current_identity,
            control_rule=get_control_rule(),
        )

        deleted_id_list = [str(r.host_row.id) for r in result_list]

        for host_id in host_id_list:
            if host_id in deleted_id_list:
                tracker_message = "deleted host"
            else:
                tracker_message = "not deleted host"

            with PayloadTrackerProcessingContext(
                payload_tracker, processing_status_message=tracker_message
            ) as payload_tracker_processing_ctx:
                payload_tracker_processing_ctx.inventory_id = host_id

    delete_keys(current_identity.org_id)
    return len(deleted_id_list)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_all_hosts(confirm_delete_all=None, rbac_filter=None):
    if not confirm_delete_all:
        logger.error("To delete all hosts, provide confirm_delete_all=true in the request.")
        flask.abort(400, "To delete all hosts, provide confirm_delete_all=true in the request.")

    try:
        # get all hosts from the DB; bypasses xjoin-search, which limits the number hosts to 10 by default.
        ids_list = get_all_hosts()
    except ValueError as err:
        log_get_host_list_failed(logger)
        flask.abort(400, str(err))
    except ConnectionError:
        logger.error("xjoin-search not accessible")
        flask.abort(503)

    try:
        delete_count = _delete_host_list(ids_list, rbac_filter)
    except KafkaError:
        logger.error("Kafka server not available")
        flask.abort(503)

    json_data = {"hosts_found": len(ids_list), "hosts_deleted": delete_count}

    return flask_json_response(json_data, HTTPStatus.ACCEPTED)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def delete_host_by_id(host_id_list, rbac_filter=None):
    delete_count = _delete_host_list(host_id_list, rbac_filter)

    if not delete_count:
        flask.abort(HTTPStatus.NOT_FOUND, "No hosts found for deletion.")

    return flask.Response(None, HTTPStatus.OK)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def get_host_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None, fields=None, rbac_filter=None):
    current_identity = get_current_identity()
    try:
        if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
            logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
            host_list, total, additional_fields, system_profile_fields = get_host_list_by_id_list_postgres(
                host_id_list, page, per_page, order_by, order_how, fields, rbac_filter
            )
        else:
            host_list, total, additional_fields, system_profile_fields = get_host_list_by_id_list_xjoin(
                host_id_list, page, per_page, order_by, order_how, fields, rbac_filter
            )
    except ValueError as e:
        log_get_host_list_failed(logger)
        flask.abort(400, str(e))

    log_get_host_list_succeeded(logger, host_list)

    json_data = build_paginated_host_list_response(
        total, page, per_page, host_list, additional_fields, system_profile_fields
    )
    return flask_json_response(json_data)


@api_operation
@CACHE.cached(key_prefix=make_key)
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def get_host_system_profile_by_id(
    host_id_list, page=1, per_page=100, order_by=None, order_how=None, fields=None, rbac_filter=None
):
    current_identity = get_current_identity()
    try:
        if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
            logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
            total, host_list = get_sparse_system_profile_postgres(
                host_id_list, page, per_page, order_by, order_how, fields, rbac_filter
            )
        else:
            total, host_list = get_sparse_system_profile(
                host_id_list, page, per_page, order_by, order_how, fields, rbac_filter
            )
    except (ValidationException, ValueError, Exception) as e:
        log_get_host_list_failed(logger)
        flask.abort(400, str(e))

    json_output = build_collection_response(host_list, page, per_page, total)
    return flask_json_response(json_output)


def _emit_patch_event(serialized_host, host):
    headers = message_headers(
        EventType.updated,
        host.canonical_facts.get("insights_id"),
        host.reporter,
        host.system_profile_facts.get("host_type"),
        host.system_profile_facts.get("operating_system", {}).get("name"),
    )
    metadata = {"b64_identity": to_auth_header(get_current_identity())}
    event = build_event(EventType.updated, serialized_host, platform_metadata=metadata)
    current_app.event_producer.write_event(event, str(host.id), headers, wait=True)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def patch_host_by_id(host_id_list, body, rbac_filter=None):
    try:
        validated_patch_host_data = PatchHostSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching host: {host_id_list} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    query = get_host_list_by_id_list_from_db(host_id_list, rbac_filter)
    hosts_to_update = query.all()

    if not hosts_to_update:
        log_patch_host_failed(logger, host_id_list)
        return flask.abort(HTTPStatus.NOT_FOUND, "Requested host not found.")

    current_identity = get_current_identity()
    staleness = get_staleness_obj(current_identity)

    try:
        for host in hosts_to_update:
            host.patch(validated_patch_host_data)

            if db.session.is_modified(host):
                db.session.commit()
                serialized_host = serialize_host(host, staleness_timestamps(), staleness=staleness)
                _emit_patch_event(serialized_host, host)
    except InventoryException as ie:
        log_patch_host_failed(logger, host_id_list)
        flask.abort(400, str(ie))

    for host in hosts_to_update:
        host.patch(validated_patch_host_data)

        if db.session.is_modified(host):
            db.session.commit()
            serialized_host = serialize_host(host, staleness_timestamps(), staleness=staleness)
            _emit_patch_event(serialized_host, host)

    delete_keys(current_identity.org_id)
    log_patch_host_success(logger, host_id_list)
    return 200


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def replace_facts(host_id_list, namespace, body, rbac_filter=None):
    return update_facts_by_namespace(FactOperations.replace, host_id_list, namespace, body, rbac_filter)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def merge_facts(host_id_list, namespace, body, rbac_filter=None):
    if not body:
        error_msg = "ERROR: Invalid request.  Merging empty facts into existing facts is a no-op."
        logger.debug(error_msg)
        return error_msg, 400

    return update_facts_by_namespace(FactOperations.merge, host_id_list, namespace, body, rbac_filter)


def update_facts_by_namespace(operation, host_id_list, namespace, fact_dict, rbac_filter):
    current_identity = get_current_identity()
    filters = (
        Host.org_id == current_identity.org_id,
        Host.id.in_(host_id_list),
        Host.facts.has_key(namespace),
    )  # noqa: W601 JSONB query filter, not a dict

    query = Host.query.join(HostGroupAssoc, isouter=True).filter(*filters).group_by(Host.id)

    if rbac_filter and "groups" in rbac_filter:
        count_before_rbac_filter = find_non_culled_hosts(update_query_for_owner_id(current_identity, query)).count()
        filters += (HostGroupAssoc.group_id.in_(rbac_filter["groups"]),)
        query = Host.query.join(HostGroupAssoc, isouter=True).filter(*filters).group_by(Host.id)
        if (
            count_before_rbac_filter
            != find_non_culled_hosts(update_query_for_owner_id(current_identity, query)).count()
        ):
            flask.abort(HTTPStatus.FORBIDDEN, "You do not have access to all of the requested hosts.")

    hosts_to_update = find_non_culled_hosts(update_query_for_owner_id(current_identity, query)).all()

    logger.debug("hosts_to_update:%s", hosts_to_update)

    if len(hosts_to_update) != len(host_id_list):
        error_msg = (
            "ERROR: The number of hosts requested does not match the number of hosts found in the host database.  "
            "This could happen if the namespace does not exist or the org_id associated with the call does "
            "not match the org_id associated with one or more the hosts.  Rejecting the fact change request."
        )
        logger.debug(error_msg)
        return error_msg, 400

    staleness = get_staleness_obj(current_identity)

    for host in hosts_to_update:
        if operation is FactOperations.replace:
            host.replace_facts_in_namespace(namespace, fact_dict)
        else:
            host.merge_facts_in_namespace(namespace, fact_dict)

        if db.session.is_modified(host):
            db.session.commit()
            serialized_host = serialize_host(host, staleness_timestamps(), staleness=staleness)
            _emit_patch_event(serialized_host, host)

    logger.debug("hosts_to_update:%s", hosts_to_update)

    return 200


@api_operation
@CACHE.cached(key_prefix=make_key)
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_host_tag_count(host_id_list, page=1, per_page=100, order_by=None, order_how=None, rbac_filter=None):
    current_identity = get_current_identity()
    if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
        logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
        limit, offset = pagination_params(page, per_page)
        host_list, total = get_host_tags_list_by_id_list_postgres(
            host_id_list, limit, offset, order_by, order_how, rbac_filter
        )
    else:
        host_list, total = get_host_tags_list_by_id_list(
            host_id_list, page, per_page, order_by, order_how, rbac_filter
        )

    counts = {host_id: len(host_tags) for host_id, host_tags in host_list.items()}
    return _build_paginated_host_tags_response(total, page, per_page, counts)


@api_operation
@CACHE.cached(key_prefix=make_key)
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_host_tags(host_id_list, page=1, per_page=100, order_by=None, order_how=None, search=None, rbac_filter=None):
    current_identity = get_current_identity()
    if get_flag_value(FLAG_INVENTORY_DISABLE_XJOIN, context={"schema": current_identity.org_id}):
        logger.info(f"{FLAG_INVENTORY_DISABLE_XJOIN} is applied to {current_identity.org_id}")
        limit, offset = pagination_params(page, per_page)
        host_list, total = get_host_tags_list_by_id_list_postgres(
            host_id_list, limit, offset, order_by, order_how, rbac_filter
        )
    else:
        host_list, total = get_host_tags_list_by_id_list(
            host_id_list, page, per_page, order_by, order_how, rbac_filter
        )

    filtered_list = {host_id: Tag.filter_tags(host_tags, search) for host_id, host_tags in host_list.items()}

    return _build_paginated_host_tags_response(total, page, per_page, filtered_list)


def _build_paginated_host_tags_response(total, page, per_page, tags_list):
    json_output = build_collection_response(tags_list, page, per_page, total)
    return flask_json_response(json_output)


@api_operation
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@ensure_org_data_integrity()
@metrics.api_request_time.time()
def host_checkin(body, rbac_filter=None):
    current_identity = get_current_identity()
    canonical_facts = deserialize_canonical_facts(body)
    existing_host = find_existing_host(current_identity, canonical_facts)
    staleness = get_staleness_obj(current_identity)
    if existing_host:
        existing_host._update_modified_date()
        db.session.commit()
        serialized_host = serialize_host(existing_host, staleness_timestamps(), staleness=staleness)
        _emit_patch_event(serialized_host, existing_host)
        delete_keys(current_identity.org_id)
        return flask_json_response(serialized_host, 201)
    else:
        flask.abort(404, "No hosts match the provided canonical facts.")
