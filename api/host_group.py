from http import HTTPStatus

from flask import Response
from flask import abort
from flask import current_app
from marshmallow import ValidationError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.group_query import build_group_response
from app.auth import get_current_identity
from app.auth.rbac import KesselResourceTypes
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_patch_group_failed
from app.logging import get_logger
from app.models.schemas import RequiredHostIdListSchema
from lib.group_repository import add_hosts_to_group
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import remove_hosts_from_group
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.middleware import access
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)


@api_operation
@access(
    KesselResourceTypes.WORKSPACE.move_host, id_param="group_id"
)  # NOTE: this -could- use the group_id param to check the group and the body to check the hosts by id instead
# of doing a lookupresources, but it's being kept this way for now for backward comaptibility
# (V1 doesn't require any host permissions to move a host but does require write group permission on the origin
# and destination, which this preserves)
@metrics.api_request_time.time()
def add_host_list_to_group(group_id, host_id_list, rbac_filter=None):
    # Validate host ID list input data
    try:
        validated_data = RequiredHostIdListSchema().load({"host_ids": host_id_list})
        host_id_list = validated_data["host_ids"]
    except ValidationError as e:
        logger.exception(f"Input validation error while adding hosts to group: {host_id_list}")
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    rbac_group_id_check(rbac_filter, {group_id})
    identity = get_current_identity()

    group_to_update = get_group_by_id_from_db(group_id, identity.org_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        return abort(HTTPStatus.NOT_FOUND)

    if len(get_host_list_by_id_list_from_db(host_id_list, identity).all()) != len(host_id_list):
        abort(HTTPStatus.NOT_FOUND, "One or more hosts not found.")

    # Next, add the host-group associations
    if host_id_list is not None:
        add_hosts_to_group(group_id, host_id_list, identity, current_app.event_producer)

    updated_group = get_group_by_id_from_db(group_id, identity.org_id)
    log_host_group_add_succeeded(logger, host_id_list, group_id)
    return flask_json_response(build_group_response(updated_group), HTTPStatus.OK)


@api_operation
@access(
    KesselResourceTypes.WORKSPACE.move_host, id_param="group_id"
)  # NOTE: this -could- use the group_id param to check the group and the body to check the hosts by id instead
# of doing a lookupresources, but it's being kept this way for now for backward comaptibility
# (V1 doesn't require any host permissions to move a host but does require write group permission on the
# origin and destination, which this preserves)
@metrics.api_request_time.time()
def delete_hosts_from_group(group_id, host_id_list, rbac_filter=None):
    # Validate host ID list input data
    try:
        validated_data = RequiredHostIdListSchema().load({"host_ids": host_id_list})
        host_id_list = validated_data["host_ids"]
    except ValidationError as e:
        logger.exception(f"Input validation error while removing hosts from group: {host_id_list}")
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    rbac_group_id_check(rbac_filter, {group_id})
    identity = get_current_identity()
    if (group := get_group_by_id_from_db(group_id, identity.org_id)) is None:
        abort(HTTPStatus.NOT_FOUND, "Group not found.")

    if len(get_host_list_by_id_list_from_db(host_id_list, identity).all()) != len(host_id_list):
        abort(HTTPStatus.NOT_FOUND, "One or more hosts not found.")

    if group.ungrouped is True:
        abort(HTTPStatus.BAD_REQUEST, f"Cannot remove hosts from ungrouped workspace {group_id}")

    remove_hosts_from_group(group_id, host_id_list, identity, current_app.event_producer)

    return Response(None, HTTPStatus.NO_CONTENT)
