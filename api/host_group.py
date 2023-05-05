from flask import abort
from flask import Response
from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import build_group_response
from app import db
from app import Permission
from app.instrumentation import log_host_group_add_succeeded
from app.instrumentation import log_patch_group_failed
from app.logging import get_logger
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_host_list_for_group
from lib.group_repository import get_group_by_id_from_db
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.middleware import rbac

logger = get_logger(__name__)


@api_operation
@rbac(Permission.WRITE)
@metrics.api_request_time.time()
def add_hosts_to_group(group_id, body):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    group_to_update = get_group_by_id_from_db(group_id)

    if not group_to_update:
        log_patch_group_failed(logger, group_id)
        return abort(status.HTTP_404_NOT_FOUND)

    host_id_list = body
    if not get_host_list_by_id_list_from_db(host_id_list):
        return abort(status.HTTP_404_NOT_FOUND)

    # Next, add the host-group associations
    assoc_list = []
    if host_id_list is not None:
        assoc_list = add_host_list_for_group(group_to_update, host_id_list)

    if any(db.session.is_modified(assoc) for assoc in assoc_list):
        db.session.commit()

    updated_group = get_group_by_id_from_db(group_id)
    log_host_group_add_succeeded(logger, host_id_list, group_id)
    return flask_json_response(build_group_response(updated_group), status.HTTP_200_OK)
