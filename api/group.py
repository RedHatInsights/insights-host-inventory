from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import Response
from flask import abort
from flask import current_app
from marshmallow import ValidationError
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.group_query import build_group_response
from api.group_query import build_paginated_group_list_response
from api.group_query import get_filtered_group_list_db
from api.group_query import get_group_list_by_id_list_db
from app.auth import get_current_identity
from app.auth.rbac import RbacPermission
from app.auth.rbac import RbacResourceType
from app.common import inventory_config
from app.config import MAX_GROUPS_FOR_HOST_COUNT_SORTING
from app.exceptions import InventoryException
from app.exceptions import ResourceNotFoundException
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
from app.queue.events import EventType
from app.serialization import serialize_rbac_workspace_with_host_count
from app.utils import check_all_ids_found
from lib.feature_flags import FLAG_INVENTORY_KESSEL_PHASE_1
from lib.feature_flags import get_flag_value
from app.utils import check_all_ids_found
from lib.group_repository import add_hosts_to_group
from lib.group_repository import create_group_from_payload
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import get_group_using_host_id
from lib.group_repository import get_groups_by_id_list_from_db
from lib.group_repository import get_ungrouped_group
from lib.group_repository import patch_group
from lib.group_repository import remove_hosts_from_group
from lib.group_repository import validate_add_host_list_to_group_for_group_create
from lib.group_repository import wait_for_workspace_event
from lib.host_repository import get_group_ids_ordered_by_host_count
from lib.host_repository import get_host_counts_batch
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.metrics import create_group_count
from lib.middleware import delete_rbac_workspace
from lib.middleware import get_rbac_workspaces
from lib.middleware import get_rbac_workspaces_by_ids
from lib.middleware import patch_rbac_workspace
from lib.middleware import post_rbac_workspace
from lib.middleware import rbac
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)


def _validate_patch_group_inputs(group_id: str, body: dict[str, Any], identity: Any) -> tuple[dict[str, Any], Any]:
    """
    Validate inputs for group patching:
    - Group exists
    - Request body is valid

    Note: Host validation is handled by the repository layer (lib/group_repository.py)
    to avoid duplication and ensure validation happens at the correct point in the
    transaction lifecycle.

    Args:
        group_id: The ID of the group to patch
        body: The request body containing patch data
        identity: The current user's identity object

    Returns:
        tuple: (validated_patch_group_data, group_to_update)
    """

    # First, get the group
    found_group = get_group_by_id_from_db(group_id, identity.org_id)

    if not found_group:
        log_patch_group_failed(logger, group_id)
        abort(HTTPStatus.NOT_FOUND)

    try:
        validated_patch_group_data = InputGroupSchema().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while patching group: {group_id} - {body}")
        abort(HTTPStatus.BAD_REQUEST, str(e.messages))

    return validated_patch_group_data, found_group


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_group_list(
    name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    group_type=None,
    rbac_filter=None,
):
    try:
        if get_flag_value(FLAG_INVENTORY_KESSEL_PHASE_1):
            # RBAC v2 path: Query workspaces from RBAC v2 API
            # Special handling for host_count ordering: RBAC v2 doesn't have host count data
            if order_by == "host_count":
                org_id = get_current_identity().org_id

                # Scenario 1: No filters - Most efficient approach
                # Let the database do ordering and pagination, then fetch only the workspaces we need
                if not name and not group_type:
                    # Step 1: Get group_ids ordered by host_count from DB (paginated)
                    group_ids_page, total = get_group_ids_ordered_by_host_count(org_id, per_page, page, order_how)

                    if not group_ids_page:
                        # No groups found
                        log_get_group_list_succeeded(logger, [])
                        return flask_json_response(
                            {
                                "total": total,
                                "count": 0,
                                "page": page,
                                "per_page": per_page,
                                "results": [],
                            }
                        )

                    # Step 2: Fetch workspace details for only this page of groups
                    workspaces = get_rbac_workspaces_by_ids(group_ids_page)

                    # Step 3: Get host counts for these groups in one batch query
                    host_counts = get_host_counts_batch(org_id, group_ids_page)

                    # Step 4: Serialize workspaces with pre-fetched host counts
                    serialized_groups = [
                        serialize_rbac_workspace_with_host_count(ws, org_id, host_counts.get(ws["id"], 0))
                        for ws in workspaces
                    ]

                    # Step 5: Maintain the DB ordering (workspaces may be in different order)
                    # Create a map for O(1) lookup
                    group_map = {g["id"]: g for g in serialized_groups}
                    ordered_groups = [group_map[gid] for gid in group_ids_page if gid in group_map]

                    log_get_group_list_succeeded(logger, ordered_groups)
                    return flask_json_response(
                        {
                            "total": total,
                            "count": len(ordered_groups),
                            "page": page,
                            "per_page": per_page,
                            "results": ordered_groups,
                        }
                    )

                # Scenario 2: With filters - RBAC v2 must filter, then DB orders by host_count
                else:
                    # Step 1: Fetch all filtered workspaces from RBAC v2
                    # Limit is configurable via MAX_GROUPS_FOR_HOST_COUNT_SORTING env variable
                    group_list, total = get_rbac_workspaces(
                        name, 1, MAX_GROUPS_FOR_HOST_COUNT_SORTING, rbac_filter, group_type, None, None
                    )

                    # Validate that we can sort all groups
                    if total > MAX_GROUPS_FOR_HOST_COUNT_SORTING:
                        log_get_group_list_failed(logger)
                        abort(
                            400,
                            f"Cannot sort by host_count: organization has {total} groups, which exceeds "
                            f"the maximum of {MAX_GROUPS_FOR_HOST_COUNT_SORTING} groups that can be sorted. "
                            f"Please use filters (name, group_type) to narrow your results, or use a different "
                            f"ordering field (name, updated, created, type).",
                        )

                    if not group_list:
                        # No groups found
                        log_get_group_list_succeeded(logger, [])
                        return flask_json_response(
                            {
                                "total": total,
                                "count": 0,
                                "page": page,
                                "per_page": per_page,
                                "results": [],
                            }
                        )

                    # Step 2: Extract group_ids
                    group_ids = [ws["id"] for ws in group_list]

                    # Step 3: Fetch ALL host counts in ONE batch query (not N queries!)
                    host_counts = get_host_counts_batch(org_id, group_ids)

                    # Step 4: Attach host_counts to workspaces (no DB queries!)
                    serialized_groups = [
                        serialize_rbac_workspace_with_host_count(ws, org_id, host_counts.get(ws["id"], 0))
                        for ws in group_list
                    ]

                    # Step 5: Sort by host_count with secondary sort by name for stable ordering
                    serialized_groups.sort(key=lambda g: g.get("name", ""))  # Secondary: name (ASC)
                    reverse = order_how == "DESC" if order_how else True  # Default DESC for host_count
                    serialized_groups.sort(key=lambda g: g.get("host_count", 0), reverse=reverse)

                    # Step 6: Apply pagination to sorted results
                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    paginated_groups = serialized_groups[start_idx:end_idx]

                    log_get_group_list_succeeded(logger, paginated_groups)
                    return flask_json_response(
                        {
                            "total": total,
                            "count": len(paginated_groups),
                            "page": page,
                            "per_page": per_page,
                            "results": paginated_groups,
                        }
                    )
            else:
                # Normal RBAC v2 path: RBAC v2 API can handle ordering
                group_list, total = get_rbac_workspaces(
                    name, page, per_page, rbac_filter, group_type, order_by, order_how
                )
        else:
            # RBAC v1 path: Query groups from database
            group_list, total = get_filtered_group_list_db(
                name, page, per_page, order_by, order_how, rbac_filter, group_type
            )
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))
    except (ConnectionError, Timeout) as e:
        # RBAC v2 API connection or timeout errors
        log_get_group_list_failed(logger)
        abort(503, f"RBAC service unavailable: {str(e)}")

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_group(body: dict, rbac_filter: dict | None = None) -> Response:
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
        group_name = validated_create_group_data.get("name")

        if not inventory_config().bypass_kessel:
            # Validate whether the hosts can be added to the group
            if len(host_id_list := validated_create_group_data.get("host_ids", [])) > 0:
                validate_add_host_list_to_group_for_group_create(
                    host_id_list,
                    group_name,
                    get_current_identity().org_id,
                )

            workspace_id = post_rbac_workspace(group_name)
            if workspace_id is None:
                message = f"Error while creating workspace for {group_name}"
                logger.exception(message)
                return json_error_response("Workspace creation failure", message, HTTPStatus.BAD_REQUEST)

            # Wait for the MQ to notify us of the workspace creation.
            try:
                wait_for_workspace_event(
                    str(workspace_id),
                    EventType.created,
                    org_id=get_current_identity().org_id,
                    timeout=inventory_config().rbac_timeout,
                )
            except TimeoutError:
                abort(HTTPStatus.SERVICE_UNAVAILABLE, "Timed out waiting for a message from RBAC v2.")

            add_hosts_to_group(
                str(workspace_id),
                host_id_list,
                get_current_identity(),
                current_app.event_producer,
            )
            created_group = get_group_by_id_from_db(str(workspace_id), get_current_identity().org_id)
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
def patch_group_by_id(group_id: str, body: dict[str, Any], rbac_filter: dict[str, Any] | None = None) -> Response:
    rbac_group_id_check(rbac_filter or {}, {group_id})

    identity = get_current_identity()

    # Validate all inputs
    validated_patch_group_data, group_to_update = _validate_patch_group_inputs(group_id, body, identity)

    # Extract validated data
    new_name = validated_patch_group_data.get("name")

    try:
        # never allow renaming ungrouped
        if group_to_update.ungrouped and new_name:
            log_patch_group_failed(logger, group_id)
            abort(HTTPStatus.BAD_REQUEST, "The 'ungrouped' group can not be modified.")

        if new_name and new_name != group_to_update.name and not inventory_config().bypass_kessel:
            patch_rbac_workspace(group_id, name=new_name)

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

    # Abort with 404 if any of the groups do not exist
    found_groups = get_groups_by_id_list_from_db(group_id_list, get_current_identity().org_id)
    check_all_ids_found(group_id_list, found_groups, "group")

    if not inventory_config().bypass_kessel:
        # Write is not allowed for the ungrouped through API requests
        ungrouped_group = get_ungrouped_group(get_current_identity())
        ungrouped_group_id = str(ungrouped_group.id) if ungrouped_group else None

        for group_id in group_id_list:
            if ungrouped_group_id == group_id:
                abort(HTTPStatus.BAD_REQUEST, f"Ungrouped workspace {group_id} can not be deleted.")

        group_ids_to_delete = []
        delete_count = 0

        # Attempt to delete the RBAC workspaces
        for group_id in group_id_list:
            try:
                delete_rbac_workspace(group_id)
                delete_count += 1
            except ResourceNotFoundException:
                # For workspaces that are missing from RBAC,
                # we'll attempt to delete the groups on our side
                group_ids_to_delete.append(group_id)

        # Attempt to delete the "not found" groups on our side
        delete_count += delete_group_list(group_ids_to_delete, get_current_identity(), current_app.event_producer)
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
        check_all_ids_found(group_id_list, group_list, "group", total=total)
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
        if group := get_group_using_host_id(host_id, identity.org_id):
            if group.ungrouped:
                abort(HTTPStatus.BAD_REQUEST, "The provided hosts cannot be removed from the ungrouped-hosts group.")

            hosts_per_group.setdefault(str(group.id), []).append(host_id)

    requested_group_ids = set(hosts_per_group.keys())

    rbac_group_id_check(rbac_filter, requested_group_ids)

    found_hosts = get_host_list_by_id_list_from_db(host_id_list, identity, rbac_filter).all()
    check_all_ids_found(host_id_list, found_hosts, "host")

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
