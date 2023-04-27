from flask import abort
from flask import current_app
from flask import Response
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import build_group_response
from api.group_query import build_paginated_group_list_response
from api.group_query import get_filtered_group_list_db
from api.group_query import get_group_list_by_id_list_db
from app import Permission
from app.exceptions import InventoryException
from app.instrumentation import log_create_group_failed
from app.instrumentation import log_create_group_succeeded
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_patch_group_failed
from app.instrumentation import log_patch_group_success
from app.logging import get_logger
from app.models import InputGroupSchema
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_group
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import patch_group
from lib.group_repository import remove_hosts_from_group
from lib.metrics import create_group_count
from lib.middleware import rbac

logger = get_logger(__name__)


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_group_list(
    name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        group_list, total = get_filtered_group_list_db(name, page, per_page, order_by, order_how)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def create_group(body):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    # Validate group input data
    try:
        validated_create_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating group: {body}")
        return error_json_response("Validation Error", str(e.messages))

    try:
        # Create group with validated data
        created_group = add_group(validated_create_group_data, current_app.event_producer)
        create_group_count.inc()

        log_create_group_succeeded(logger, created_group.id)
    except IntegrityError as inte:
        group_name = validated_create_group_data.get("name")
        host_id_list = validated_create_group_data.get("host_ids")

        if group_name in str(inte.params):
            error_message = f"A group with name {group_name} already exists."
        else:
            error_message = f"A group with host list {host_id_list} already exists."

        log_create_group_failed(logger, group_name)
        logger.exception(error_message)
        return error_json_response("Integrity error", error_message)

    except InventoryException as inve:
        logger.exception(inve.detail)
        return error_json_response(inve.title, inve.detail)

    return flask_json_response(build_group_response(created_group), status.HTTP_201_CREATED)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def patch_group_by_id(group_id, body):
    try:
        validated_patch_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    # First, get the group and update it
    group_to_update = get_group_by_id_from_db(group_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        abort(status.HTTP_404_NOT_FOUND)

    try:
        # Separate out the host IDs because they're not stored on the Group
        patch_group(group_to_update, validated_patch_group_data, current_app.event_producer)

    except InventoryException as ie:
        log_patch_group_failed(logger, group_id)
        abort(status.HTTP_400_BAD_REQUEST, str(ie.detail))
    except IntegrityError:
        log_patch_group_failed(logger, group_id)
        abort(
            status.HTTP_400_BAD_REQUEST,
            f"Group with name '{validated_patch_group_data.get('name')}' already exists.",
        )

    updated_group = get_group_by_id_from_db(group_id)
    log_patch_group_success(logger, group_id)
    return flask_json_response(build_group_response(updated_group), status.HTTP_200_OK)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def delete_groups(group_id_list):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    delete_count = delete_group_list(group_id_list, current_app.event_producer)

    if delete_count == 0:
        abort(status.HTTP_404_NOT_FOUND, "No groups found for deletion.")

    return Response(None, status.HTTP_204_NO_CONTENT)


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_groups_by_id(
    group_id_list,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        group_list, total = get_group_list_by_id_list_db(group_id_list, page, per_page, order_by, order_how)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def delete_hosts_from_group(group_id, host_id_list):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    delete_count = remove_hosts_from_group(group_id, host_id_list, current_app.event_producer)

    if delete_count == 0:
        abort(status.HTTP_404_NOT_FOUND, "Group or hosts not found.")

    return Response(None, status.HTTP_204_NO_CONTENT)


def error_json_response(title, detail, status=status.HTTP_400_BAD_REQUEST):
    return flask_json_response({"title": title, "detail": detail}, status)
