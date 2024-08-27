from http import HTTPStatus

from flask import abort
from flask import current_app
from flask import Response

from api import api_operation
from api import flask_json_response
from api import metrics
from api.cache import delete_cached_system_keys
from api.group_query import build_group_response
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_patch_group_failed
from app.logging import get_logger
from lib.group_repository import add_hosts_to_group
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import remove_hosts_from_group
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.middleware import rbac
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def add_host_list_to_group(group_id, body, rbac_filter=None):
    if type(body) is not list:
        return abort(HTTPStatus.BAD_REQUEST, f"Body content must be an array with system UUIDs, not {type(body)}")

    if len(body) == 0:
        return abort(HTTPStatus.BAD_REQUEST, "Body content must be an array with system UUIDs, not an empty array")

    rbac_group_id_check(rbac_filter, {group_id})

    group_to_update = get_group_by_id_from_db(group_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        return abort(HTTPStatus.NOT_FOUND)

    host_id_list = body
    if not get_host_list_by_id_list_from_db(host_id_list):
        return abort(HTTPStatus.NOT_FOUND)

    # Next, add the host-group associations
    if host_id_list is not None:
        add_hosts_to_group(group_id, body, current_app.event_producer)

    updated_group = get_group_by_id_from_db(group_id)
    current_identity = get_current_identity()
    delete_cached_system_keys(org_id=current_identity.org_id, spawn=True)
    log_host_group_add_succeeded(logger, host_id_list, group_id)
    return flask_json_response(build_group_response(updated_group), HTTPStatus.OK)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_hosts_from_group(group_id, host_id_list, rbac_filter=None):
    rbac_group_id_check(rbac_filter, {group_id})

    delete_count = remove_hosts_from_group(group_id, host_id_list, current_app.event_producer)

    if delete_count == 0:
        abort(HTTPStatus.NOT_FOUND, "Group or hosts not found.")

    current_identity = get_current_identity()
    delete_cached_system_keys(org_id=current_identity.org_id, spawn=True)
    return Response(None, HTTPStatus.NO_CONTENT)
