from http import HTTPStatus

from flask import Response
from flask import abort
from flask import current_app
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.group_query import build_group_response
from api.group_query import build_paginated_group_list_response
from api.group_query import does_group_with_name_exist
from api.group_query import get_filtered_group_list_db
from api.group_query import get_group_list_by_id_list_db
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.common import inventory_config
from app.exceptions import InventoryException
from app.instrumentation import log_create_group_failed
from app.instrumentation import log_create_group_not_allowed
from app.instrumentation import log_create_group_succeeded
from app.instrumentation import log_delete_hosts_from_group_failed
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_patch_group_failed
from app.instrumentation import log_patch_group_success
from app.logging import get_logger
from app.models import InputGroupSchema
from lib.feature_flags import FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION
from lib.feature_flags import get_flag_value
from lib.group_repository import add_hosts_to_group
from lib.group_repository import create_group_from_payload
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import get_group_using_host_id
from lib.group_repository import get_ungrouped_group
from lib.group_repository import patch_group
from lib.group_repository import remove_hosts_from_group
from lib.group_repository import validate_add_host_list_to_group_for_group_create
from lib.group_repository import wait_for_workspace_creation
from lib.metrics import create_group_count
from lib.middleware import delete_rbac_workspace
from lib.middleware import patch_rbac_workspace
from lib.middleware import post_rbac_workspace
from lib.middleware import rbac
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_group_list(
    name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter=None,
):
    try:
        group_list, total = get_filtered_group_list_db(name, page, per_page, order_by, order_how, rbac_filter)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_group(body, rbac_filter=None):
    # If there is an attribute filter on the RBAC permissions,
    # the user should not be allowed to create a group.
    if rbac_filter is not None:
        log_create_group_not_allowed(logger)
        abort(
            HTTPStatus.FORBIDDEN,
            "Unfiltered inventory:groups:write RBAC permission is required in order to create new groups.",
        )

    # Validate group input data
    try:
        validated_create_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating group: {body}")
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    try:
        # Create group with validated data
        if get_flag_value(FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION):
            group_name = validated_create_group_data.get("name")
            # Before waiting for workspace creation in RBAC, check that the name isn't already in use
            if does_group_with_name_exist(group_name, get_current_identity().org_id):
                log_create_group_failed(logger, group_name)
                return json_error_response(
                    "Integrity error", f"A group with name {group_name} already exists.", HTTPStatus.BAD_REQUEST
                )

            # Also, validate whether the hosts can be added to the group
            if len(host_id_list := validated_create_group_data.get("host_ids", [])) > 0:
                validate_add_host_list_to_group_for_group_create(
                    host_id_list,
                    group_name,
                    get_current_identity().org_id,
                )

            workspace_id = post_rbac_workspace(group_name)
            if not workspace_id and not inventory_config().bypass_rbac:
                message = f"Error while creating workspace for {group_name}"
                logger.exception(message)
                return json_error_response("Workspace creation failure", message, HTTPStatus.BAD_REQUEST)

            # Wait for the MQ to notify us of the workspace creation
            try:
                wait_for_workspace_creation(workspace_id, inventory_config().rbac_timeout)
            except TimeoutError:
                abort(HTTPStatus.SERVICE_UNAVAILABLE, "Timed out waiting for a message from RBAC v2.")

            add_hosts_to_group(
                workspace_id,
                host_id_list,
                get_current_identity(),
                current_app.event_producer,
            )
            created_group = get_group_by_id_from_db(workspace_id, get_current_identity().org_id)
        else:
            created_group = create_group_from_payload(validated_create_group_data, current_app.event_producer, None)
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
        return json_error_response("Integrity error", error_message, HTTPStatus.BAD_REQUEST)

    except InventoryException as inve:
        logger.exception(inve.detail)
        return json_error_response(inve.title, inve.detail, HTTPStatus.BAD_REQUEST)

    return flask_json_response(build_group_response(created_group), HTTPStatus.CREATED)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def patch_group_by_id(group_id, body, rbac_filter=None):
    rbac_group_id_check(rbac_filter, {group_id})

    try:
        validated_patch_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        return ({"status": 400, "title": "Bad Request", "detail": str(e.messages), "type": "unknown"}, 400)

    identity = get_current_identity()

    # First, get the group and update it
    group_to_update = get_group_by_id_from_db(group_id, identity.org_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        abort(HTTPStatus.NOT_FOUND)

    try:
        if get_flag_value(FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION):
            # Update group on Kessel
            new_group_name = validated_patch_group_data.get("name")

            if new_group_name:
                patch_rbac_workspace(group_id, name=new_group_name)

        # Separate out the host IDs because they're not stored on the Group
        patch_group(group_to_update, validated_patch_group_data, identity, current_app.event_producer)

    except InventoryException as ie:
        log_patch_group_failed(logger, group_id)
        abort(HTTPStatus.BAD_REQUEST, str(ie.detail))
    except IntegrityError:
        log_patch_group_failed(logger, group_id)
        abort(
            HTTPStatus.BAD_REQUEST,
            f"Group with name '{validated_patch_group_data.get('name')}' already exists.",
        )

    updated_group = get_group_by_id_from_db(group_id, identity.org_id)
    log_patch_group_success(logger, group_id)
    return flask_json_response(build_group_response(updated_group), HTTPStatus.OK)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_groups(group_id_list, rbac_filter=None):
    rbac_group_id_check(rbac_filter, set(group_id_list))

    if get_flag_value(FLAG_INVENTORY_KESSEL_WORKSPACE_MIGRATION):
        # Write is not allowed for the ungrouped through API requests
        ungrouped_group = get_ungrouped_group(get_current_identity())
        ungrouped_group_id = str(ungrouped_group.id) if ungrouped_group else None

        for group_id in group_id_list:
            if ungrouped_group_id and ungrouped_group_id == group_id:
                abort(HTTPStatus.BAD_REQUEST, f"Workspace {group_id} can not be deleted.")

        for group_id in group_id_list:
            delete_rbac_workspace(group_id)

        return Response(None, HTTPStatus.NO_CONTENT)
    else:
        delete_count = delete_group_list(group_id_list, get_current_identity(), current_app.event_producer)

    if delete_count == 0:
        log_get_group_list_failed(logger)
        abort(HTTPStatus.NOT_FOUND, "No groups found for deletion.")
    return Response(None, HTTPStatus.NO_CONTENT)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_groups_by_id(
    group_id_list,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter=None,
):
    rbac_group_id_check(rbac_filter, set(group_id_list))

    try:
        group_list, total = get_group_list_by_id_list_db(
            group_id_list, page, per_page, order_by, order_how, rbac_filter
        )
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_hosts_from_different_groups(host_id_list, rbac_filter=None):
    identity = get_current_identity()
    hosts_per_group = {}

    # Separate hosts per group
    for host_id in host_id_list:
        group = get_group_using_host_id(host_id, identity.org_id)

        if group:
            hosts_per_group.setdefault(str(group.id), []).append(host_id)

    requested_group_ids = set(hosts_per_group.keys())

    rbac_group_id_check(rbac_filter, requested_group_ids)

    delete_count = 0

    for group_id in requested_group_ids:
        deleted_from_group = remove_hosts_from_group(
            group_id, hosts_per_group.get(group_id), identity, current_app.event_producer
        )
        delete_count += deleted_from_group

    if delete_count == 0:
        log_delete_hosts_from_group_failed(logger)
        abort(HTTPStatus.NOT_FOUND, "The provided hosts were not found.")
    return Response(None, HTTPStatus.NO_CONTENT)
