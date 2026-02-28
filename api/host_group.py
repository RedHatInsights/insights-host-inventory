from http import HTTPStatus
from uuid import UUID

from flask import Response
from flask import abort
from flask import current_app
from marshmallow import ValidationError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.group_query import build_group_response
from api.host_query import build_paginated_host_list_response
from api.host_query_db import get_host_list
from app.auth import get_current_identity
from app.auth.rbac import KesselResourceTypes
from app.common import inventory_config
from app.exceptions import ResourceNotFoundException
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_patch_group_failed
from app.logging import get_logger
from app.models.schemas import RequiredHostIdListSchema
from lib.feature_flags import FLAG_INVENTORY_KESSEL_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_hosts_to_group
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import remove_hosts_from_group
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.middleware import access
from lib.middleware import get_rbac_workspace_by_id
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_host_list_by_group(
    group_id: UUID,
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    staleness=None,
    tags=None,
    registered_with=None,
    filter=None,
    fields=None,
    rbac_filter=None,
):
    """
    Get the list of hosts in a specific group.

    Behind feature flag: hbi.api.kessel-groups
    - If enabled: Validates group via RBAC v2 workspace API
    - If disabled: Validates group via database

    Args:
        group_id: UUID of the group/workspace (validated by OpenAPI schema)
        ... (standard host filtering parameters)

    Returns:
        Paginated list of hosts in the group

    Note:
        The group_id is automatically validated by Connexion via the OpenAPI
        schema (NonStrictUUID), so no manual validation is needed.
    """
    identity = get_current_identity()
    rbac_group_id_check(rbac_filter, {str(group_id)})

    # Validate group exists
    # Use RBAC v2 workspace validation only when bypass_kessel is False and flag is enabled
    # Otherwise, use database validation
    if not inventory_config().bypass_kessel and get_flag_value(FLAG_INVENTORY_KESSEL_GROUPS):
        # RBAC v2 path: Validate workspace exists
        try:
            get_rbac_workspace_by_id(str(group_id))
        except ResourceNotFoundException:
            abort(HTTPStatus.NOT_FOUND, f"Group {group_id} not found")
    else:
        # Database path: Validate group exists (used in tests, when Kessel is bypassed, or when flag is disabled)
        group = get_group_by_id_from_db(str(group_id), identity.org_id)
        if not group:
            abort(HTTPStatus.NOT_FOUND, f"Group {group_id} not found")

    # Get hosts from database (regardless of feature flag - host data is in DB)
    try:
        host_list, total, additional_fields, system_profile_fields = get_host_list(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=None,
            provider_id=None,
            provider_type=None,
            updated_start=None,
            updated_end=None,
            last_check_in_start=None,
            last_check_in_end=None,
            group_name=None,
            group_id=[str(group_id)],
            tags=tags,
            page=page,
            per_page=per_page,
            param_order_by=order_by,
            param_order_how=order_how,
            staleness=staleness,
            registered_with=registered_with,
            system_type=None,
            filter=filter,
            fields=fields,
            rbac_filter=rbac_filter,
        )
    except ValueError as e:
        logger.exception(f"Error getting hosts for group {group_id}")
        abort(HTTPStatus.BAD_REQUEST, str(e))

    # Build and return paginated response
    json_data = build_paginated_host_list_response(
        total, page, per_page, host_list, additional_fields, system_profile_fields
    )
    return flask_json_response(json_data)


@api_operation
@access(
    KesselResourceTypes.WORKSPACE.move_host, id_param="group_id"
)  # NOTE: this -could- use the group_id param to check the group and the body to check the hosts by id instead
# of doing a lookupresources, but it's being kept this way for now for backward comaptibility
# (V1 doesn't require any host permissions to move a host but does require write group permission on the origin
# and destination, which this preserves)
@metrics.api_request_time.time()
def add_host_list_to_group(group_id: UUID, host_id_list, rbac_filter=None):
    # Validate host ID list input data
    try:
        validated_data = RequiredHostIdListSchema().load({"host_ids": host_id_list})
        host_id_list = validated_data["host_ids"]
    except ValidationError as e:
        logger.exception(f"Input validation error while adding hosts to group: {host_id_list}")
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    rbac_group_id_check(rbac_filter, {str(group_id)})
    identity = get_current_identity()

    # Feature flag check for RBAC v2 workspace validation
    if (not inventory_config().bypass_kessel) and get_flag_value(FLAG_INVENTORY_KESSEL_GROUPS):
        # RBAC v2 path: Validate workspace via RBAC v2 API
        try:
            get_rbac_workspace_by_id(str(group_id))
        except ResourceNotFoundException:
            log_patch_group_failed(logger, str(group_id))
            return abort(HTTPStatus.NOT_FOUND, f"Group {group_id} not found")
    else:
        # RBAC v1 path: Validate group via database
        group_to_update = get_group_by_id_from_db(str(group_id), identity.org_id)

        if not group_to_update:
            log_patch_group_failed(logger, str(group_id))
            return abort(HTTPStatus.NOT_FOUND, f"Group {group_id} not found")

    if not get_host_list_by_id_list_from_db(host_id_list, identity):
        return abort(HTTPStatus.NOT_FOUND)

    # Next, add the host-group associations
    if host_id_list is not None:
        add_hosts_to_group(str(group_id), host_id_list, identity, current_app.event_producer)

    updated_group = get_group_by_id_from_db(str(group_id), identity.org_id)
    log_host_group_add_succeeded(logger, host_id_list, str(group_id))
    return flask_json_response(build_group_response(updated_group), HTTPStatus.OK)


@api_operation
@access(
    KesselResourceTypes.WORKSPACE.move_host, id_param="group_id"
)  # NOTE: this -could- use the group_id param to check the group and the body to check the hosts by id instead
# of doing a lookupresources, but it's being kept this way for now for backward comaptibility
# (V1 doesn't require any host permissions to move a host but does require write group permission on the
# origin and destination, which this preserves)
@metrics.api_request_time.time()
def delete_hosts_from_group(group_id: UUID, host_id_list, rbac_filter=None):
    # Validate host ID list input data
    try:
        validated_data = RequiredHostIdListSchema().load({"host_ids": host_id_list})
        host_id_list = validated_data["host_ids"]
    except ValidationError as e:
        logger.exception(f"Input validation error while removing hosts from group: {host_id_list}")
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    rbac_group_id_check(rbac_filter, {str(group_id)})
    identity = get_current_identity()
    if (group := get_group_by_id_from_db(str(group_id), identity.org_id)) is None:
        abort(HTTPStatus.NOT_FOUND, f"Group {group_id} not found")

    if group.ungrouped is True:
        abort(HTTPStatus.BAD_REQUEST, f"Cannot remove hosts from ungrouped workspace {group_id}")

    if remove_hosts_from_group(str(group_id), host_id_list, identity, current_app.event_producer) == 0:
        abort(HTTPStatus.NOT_FOUND, "Hosts not found")

    return Response(None, HTTPStatus.NO_CONTENT)
